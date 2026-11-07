import { render, screen } from "@testing-library/react";
import { History } from "./History";
import { snapshot } from "../test-fixtures";
import { jsonResponse, routeFetcher } from "../test-fetcher";

function renderHistory() {
  const fetcher = routeFetcher({
    "/api/snapshot": () => jsonResponse(snapshot),
  });
  return render(<History fetcher={fetcher} pollMs={1000} />);
}

describe("History", () => {
  it("states the 500-record cap and lists runs and jobs together", async () => {
    renderHistory();
    expect(await screen.findByRole("heading", { name: "History" })).toBeInTheDocument();
    expect(
      screen.getByText("At most 500 records per list; older records are not shown."),
    ).toBeInTheDocument();
    expect(screen.getByText("10 runs · 3 jobs")).toBeInTheDocument();
    expect(
      screen.getByText("store-blink: fix the blinking store badge"),
    ).toBeInTheDocument();
    expect(screen.getByText("web build")).toBeInTheDocument();
    expect(screen.getByText("eps test matrix")).toBeInTheDocument();
  });

  it("uses the state words instead of raw display states", async () => {
    renderHistory();
    await screen.findByRole("heading", { name: "History" });
    expect(screen.getAllByText("process gone").length).toBeGreaterThan(0);
    expect(screen.getAllByText("out of date").length).toBeGreaterThan(0);
    expect(screen.queryByText("lost")).toBeNull();
    expect(screen.queryByText("stale")).toBeNull();
    expect(screen.queryByText("unknown")).toBeNull();
  });

  it("leaves out a missing role instead of a leading separator", async () => {
    renderHistory();
    await screen.findByRole("heading", { name: "History" });
    const metas = Array.from(document.querySelectorAll(".history-row .row-meta"));
    expect(metas.length).toBeGreaterThan(0);
    for (const node of metas) {
      expect(node.textContent).not.toMatch(/^·/);
    }
  });

  it("shows the unavailable banner when the record list cannot be read", async () => {
    const fetcher = routeFetcher({
      "/api/snapshot": () =>
        jsonResponse({ api: 1, error: { code: "internal", message: "boom" } }, 500),
    });
    render(<History fetcher={fetcher} pollMs={1000} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("HTTP 500");
    expect(alert).toHaveTextContent("current state cannot be verified");
  });
});

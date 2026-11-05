import { render, screen, waitFor } from "@testing-library/react";
import { App } from "./App";
import { snapshot, snapshotDemo } from "./test-fixtures";
import { jsonResponse, notModified, sequenceFetcher } from "./test-fetcher";

const TITLE = "store-blink: fix the blinking store badge";

describe("App polling", () => {
  it("shows Unavailable on a network failure and keeps old data marked old", async () => {
    const { fetcher } = sequenceFetcher([
      () => jsonResponse(snapshot),
      () => Promise.reject(new TypeError("Failed to fetch")),
      () => Promise.reject(new TypeError("Failed to fetch")),
    ]);
    render(<App fetcher={fetcher} pollMs={20} />);

    expect(await screen.findByText(TITLE)).toBeInTheDocument();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Failed to fetch");
    expect(alert).toHaveTextContent(/last good data from/);
    expect(screen.getByText(TITLE)).toBeInTheDocument();
    expect(document.querySelector("[data-stale='true']")).toBeTruthy();
  });

  it("shows Unavailable on HTTP 500 and does not present old data as current", async () => {
    const { fetcher } = sequenceFetcher([
      () => jsonResponse(snapshot),
      () => jsonResponse({ api: 1, error: { code: "internal", message: "boom" } }, 500),
    ]);
    render(<App fetcher={fetcher} pollMs={20} />);

    expect(await screen.findByText(TITLE)).toBeInTheDocument();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("HTTP 500");
    expect(screen.getByText(/not current/)).toBeInTheDocument();
    expect(document.querySelector("[data-stale='true']")).toBeTruthy();
  });

  it("recovers automatically on the next good poll", async () => {
    const { fetcher } = sequenceFetcher([
      () => jsonResponse(snapshot),
      () => Promise.reject(new TypeError("Failed to fetch")),
      () => jsonResponse(snapshot),
    ]);
    render(<App fetcher={fetcher} pollMs={20} />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(document.querySelector("[data-stale='true']")).toBeNull();
    expect(screen.getByText(TITLE)).toBeInTheDocument();
  });

  it("keeps data on 304 and sends If-None-Match", async () => {
    const tag = 'W/"7-1234"';
    const { fetcher, calls } = sequenceFetcher([
      () => jsonResponse(snapshot, 200, { ETag: tag }),
      () => notModified(tag),
    ]);
    render(<App fetcher={fetcher} pollMs={20} />);

    expect(await screen.findByText(TITLE)).toBeInTheDocument();
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(2));

    const headers = calls[1].init?.headers as unknown as Record<string, string>;
    expect(headers["If-None-Match"]).toBe(tag);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText(TITLE)).toBeInTheDocument();
  });

  it("shows a permanent DEMO DATA banner for a demo snapshot", async () => {
    const { fetcher, calls } = sequenceFetcher([() => jsonResponse(snapshotDemo)]);
    render(<App fetcher={fetcher} pollMs={20} />);

    expect(await screen.findByText("DEMO DATA")).toBeInTheDocument();
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(2));
    expect(screen.getByText("DEMO DATA")).toBeInTheDocument();
  });
});

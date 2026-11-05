import { render, screen, waitFor } from "@testing-library/react";
import { RunDetail } from "./RunDetail";
import {
  fileNotReadable,
  fileReadable,
  recordJob,
  recordRun,
} from "../test-fixtures";
import { jsonResponse, routeFetcher } from "../test-fetcher";

const runParams = {
  source_id: "tachiko-harness@mbp",
  type: "run",
  id: "old-worker-88",
};

const jobParams = {
  source_id: "my-workflow@mbp",
  type: "job",
  id: "build-fg-1",
};

describe("RunDetail", () => {
  it("shows both states, marks redacted spans, and shows unresolved refs", async () => {
    const fetcher = routeFetcher({
      "/api/record": () => jsonResponse(recordRun),
      "/api/file": () => jsonResponse(fileReadable),
    });
    render(<RunDetail params={runParams} fetcher={fetcher} />);

    expect(
      await screen.findByText("migration replay: checkpoint rebuild"),
    ).toBeInTheDocument();
    expect(document.querySelector(".transition-from")?.textContent).toBe("running");
    expect(document.querySelector('.badge[data-state="stale"]')).toBeTruthy();
    expect(screen.getByText("not seen")).toBeInTheDocument();
    expect(screen.getByText(/token basis: measured/)).toBeInTheDocument();
    expect(screen.getByText(/cost basis: api_equivalent/)).toBeInTheDocument();

    await waitFor(() => expect(document.querySelectorAll(".redacted")).toHaveLength(2));
    expect(document.querySelectorAll('.redacted')[0].textContent).toBe("[redacted]");

    const pr = screen.getByText(
      "https://github.com/nurockplayer/tachiko-harness/pull/412",
    );
    expect(pr).toHaveAttribute("target", "_blank");
    expect(pr).toHaveAttribute("rel", "noreferrer noopener");
    expect(document.querySelector('a[href^="file:"]')).toBeNull();
  });

  it("shows the not readable variant with its reason", async () => {
    const fetcher = routeFetcher({
      "/api/record": () => jsonResponse(recordJob),
      "/api/file": () => jsonResponse(fileNotReadable),
    });
    render(<RunDetail params={jobParams} fetcher={fetcher} />);

    expect(await screen.findByText("pnpm build --filter web")).toBeInTheDocument();
    expect(await screen.findByText("not readable")).toBeInTheDocument();
    expect(screen.getByText("outside the allowed roots")).toBeInTheDocument();
  });

  it("shows done when the record changes between polls", async () => {
    const done = structuredClone(recordRun);
    done.record.state = "done";
    done.record.display_state = "done";
    done.record.updated_at = "2026-11-06T03:25:00+09:00";
    let recordCalls = 0;
    const fetcher = routeFetcher({
      "/api/record": () => {
        recordCalls += 1;
        return jsonResponse(recordCalls === 1 ? recordRun : done);
      },
      "/api/file": () => jsonResponse(fileReadable),
    });
    render(<RunDetail params={runParams} fetcher={fetcher} pollMs={100} />);

    expect(
      await screen.findByText("migration replay: checkpoint rebuild"),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        document.querySelector('header.detail-head .badge[data-state="done"]'),
      ).toBeTruthy(),
    );
  });

  it("hides sections that do not apply to a job", async () => {
    const fetcher = routeFetcher({
      "/api/record": () => jsonResponse(recordJob),
      "/api/file": () => jsonResponse(fileReadable),
    });
    render(<RunDetail params={jobParams} fetcher={fetcher} />);

    expect(await screen.findByText("pnpm build --filter web")).toBeInTheDocument();
    expect(screen.queryByText("Usage")).toBeNull();
    expect(screen.queryByText("Owned jobs")).toBeNull();
    expect(screen.queryByText("parent")).toBeNull();
    expect(screen.queryByText("spawned")).toBeNull();
    expect(screen.queryByText("continues")).toBeNull();
    expect(screen.getByText("inbox")).toBeInTheDocument();
    expect(screen.getByText("Version history")).toBeInTheDocument();
  });
});

import { act, render, screen, waitFor } from "@testing-library/react";
import { RunDetail } from "./RunDetail";
import type { Fetcher } from "../api/client";
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

async function until(predicate: () => boolean) {
  for (let i = 0; i < 100; i += 1) {
    if (predicate()) return;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
  }
  throw new Error("condition not reached");
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

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

  it("keeps one poll in flight across a visibility change", async () => {
    vi.useFakeTimers();
    try {
      let recordCalls = 0;
      let resolveFirst!: (response: Response) => void;
      const first = new Promise<Response>((resolve) => {
        resolveFirst = resolve;
      });
      const fetcher: Fetcher = async (url) => {
        if (url.startsWith("/api/record")) {
          recordCalls += 1;
          return recordCalls === 1 ? first : jsonResponse(recordRun);
        }
        return jsonResponse(fileReadable);
      };
      render(<RunDetail params={runParams} fetcher={fetcher} pollMs={1000} />);
      await flush();
      expect(recordCalls).toBe(1);

      // The page becomes visible while the first request is still pending.
      document.dispatchEvent(new Event("visibilitychange"));
      await flush();
      expect(recordCalls).toBe(1);
      expect(vi.getTimerCount()).toBe(0);

      resolveFirst(jsonResponse(recordRun));
      await flush();
      expect(recordCalls).toBe(1);
      expect(vi.getTimerCount()).toBe(1);

      // One interval later the single loop makes exactly one more call.
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });
      await flush();
      expect(recordCalls).toBe(2);
      expect(vi.getTimerCount()).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("refreshes a live log while updated_at stays the same", async () => {
    const running = structuredClone(recordRun);
    running.record.display_state = "running";
    const grown = structuredClone(fileReadable);
    grown.text += "12:50:00 still running\n";
    let fileCalls = 0;
    const fetcher = routeFetcher({
      "/api/record": () => jsonResponse(running),
      "/api/file": () => {
        fileCalls += 1;
        return jsonResponse(fileCalls === 1 ? fileReadable : grown);
      },
    });
    render(<RunDetail params={runParams} fetcher={fetcher} pollMs={50} />);

    expect(await screen.findByText(/worker started/)).toBeInTheDocument();
    await until(() => screen.queryByText(/still running/) !== null);
    expect(fileCalls).toBeGreaterThan(1);
  });

  it("does not refetch the log once the record is terminal", async () => {
    const done = structuredClone(recordRun);
    done.record.state = "done";
    done.record.display_state = "done";
    let fileCalls = 0;
    const fetcher = routeFetcher({
      "/api/record": () => jsonResponse(done),
      "/api/file": () => {
        fileCalls += 1;
        return jsonResponse(fileReadable);
      },
    });
    render(<RunDetail params={runParams} fetcher={fetcher} pollMs={20} />);

    expect(await screen.findByText(/worker started/)).toBeInTheDocument();
    await until(() => fileCalls > 0);
    const afterFirst = fileCalls;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 100));
    });
    expect(fileCalls).toBe(afterFirst);
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

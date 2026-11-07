import { act, render, screen, waitFor } from "@testing-library/react";
import { RunDetail } from "./RunDetail";
import type { Fetcher } from "../api/client";
import type { RunSummary } from "../api/types";
import { fileNotReadable, fileReadable, recordJob, recordRun } from "../test-fixtures";
import { jsonResponse, routeFetcher } from "../test-fetcher";

// jsdom is slow when the host is loaded; give the first render 3 s.
const SLOW = { timeout: 3000 };

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
  it("follows the §6 order with words for the state, waits and evidence", async () => {
    const fetcher = routeFetcher({
      "/api/record": () => jsonResponse(recordRun),
      "/api/file": () => jsonResponse(fileReadable),
    });
    render(<RunDetail params={runParams} fetcher={fetcher} />);

    expect(
      await screen.findByRole("heading", { name: "migration replay: checkpoint rebuild" }, SLOW),
    ).toBeInTheDocument();
    expect(document.querySelector('.detail-head .state-badge[data-state="stale"]')).toBeTruthy();
    expect(screen.getByText("out of date")).toBeInTheDocument();
    expect(screen.getByText(/Out of date: the last update was 42m/)).toBeInTheDocument();
    expect(
      screen.getByText(/No recent process check; the last check was 42m/),
    ).toBeInTheDocument();

    const headings = screen
      .getAllByRole("heading", { level: 2 })
      .map((node) => node.textContent);
    expect(headings).toEqual(["What is happening", "Relationships", "Evidence", "Log"]);

    for (const summary of ["Usage", "Version history", "Links", "Raw fields (redacted)"]) {
      expect(screen.getByText(summary)).toBeInTheDocument();
    }
    expect(document.querySelectorAll("details[open]")).toHaveLength(0);
  });

  it("shows unresolved refs as not found and redacts log spans", async () => {
    const fetcher = routeFetcher({
      "/api/record": () => jsonResponse(recordRun),
      "/api/file": () => jsonResponse(fileReadable),
    });
    render(<RunDetail params={runParams} fetcher={fetcher} />);

    await screen.findByRole("heading", { name: "migration replay: checkpoint rebuild" }, SLOW);
    expect(screen.getByText("not found")).toBeInTheDocument();

    await waitFor(() => expect(document.querySelectorAll(".redacted")).toHaveLength(2));
    expect(document.querySelectorAll(".redacted")[0].textContent).toBe("[redacted]");

    const pr = screen.getByText(
      "https://github.com/nurockplayer/tachiko-harness/pull/412",
    );
    expect(pr).toHaveAttribute("target", "_blank");
    expect(pr).toHaveAttribute("rel", "noreferrer noopener");
    expect(document.querySelector('a[href^="file:"]')).toBeNull();
  });

  it("says a waiting run's job status was not found", async () => {
    const waiting = structuredClone(recordRun);
    const waitingRecord = waiting.record as RunSummary;
    waitingRecord.state = "waiting";
    waitingRecord.display_state = "waiting";
    waitingRecord.waits_on = [
      {
        type: "job",
        id: "job-x",
        source_id: "tachiko-harness@mbp",
        resolved: false,
      },
    ];
    const fetcher = routeFetcher({
      "/api/record": () => jsonResponse(waiting),
      "/api/file": () => jsonResponse(fileReadable),
    });
    render(<RunDetail params={runParams} fetcher={fetcher} />);

    expect(await screen.findByText(/Waiting on job job-x\./, undefined, SLOW)).toBeInTheDocument();
    expect(screen.getByText(/Job status not found\./)).toBeInTheDocument();
  });

  it("explains that a running job resumes the waiting worker", async () => {
    const waiting = structuredClone(recordRun);
    const waitingRecord = waiting.record as RunSummary;
    waitingRecord.state = "waiting";
    waitingRecord.display_state = "waiting";
    waitingRecord.waits_on = [
      {
        type: "job",
        id: "scan-1",
        source_id: "tachiko-harness@mbp",
        resolved: true,
        display_state: "running",
        title: "pnpm test",
      },
    ];
    const fetcher = routeFetcher({
      "/api/record": () => jsonResponse(waiting),
      "/api/file": () => jsonResponse(fileReadable),
    });
    render(<RunDetail params={runParams} fetcher={fetcher} />);

    expect(
      await screen.findByText(/The worker has handed off and resumes when the job ends\./, undefined, SLOW),
    ).toBeInTheDocument();
  });

  it("shows the not readable log variant with its reason", async () => {
    const fetcher = routeFetcher({
      "/api/record": () => jsonResponse(recordJob),
      "/api/file": () => jsonResponse(fileNotReadable),
    });
    render(<RunDetail params={jobParams} fetcher={fetcher} />);

    expect(await screen.findByRole("heading", { name: "web build" }, SLOW)).toBeInTheDocument();
    expect(await screen.findByText("Log unavailable", undefined, SLOW)).toBeInTheDocument();
    expect(screen.getByText("outside the allowed roots")).toBeInTheDocument();
    expect(screen.getByText(/Failed with exit 1\./)).toBeInTheDocument();
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
      await screen.findByRole("heading", { name: "migration replay: checkpoint rebuild" }, SLOW),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(document.querySelector('.detail-head .state-badge[data-state="done"]')).toBeTruthy(),
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

    expect(
      await screen.findByText(/worker started/, undefined, SLOW),
    ).toBeInTheDocument();
    await until(() => screen.queryByText(/still running/) !== null);
    expect(fileCalls).toBeGreaterThan(1);
  });

  it("keeps refreshing the log of a running record that shows out of date", async () => {
    const stale = structuredClone(recordRun);
    stale.record.state = "running";
    stale.record.display_state = "stale";
    const grown = structuredClone(fileReadable);
    grown.text += "12:50:00 still running\n";
    let fileCalls = 0;
    const fetcher = routeFetcher({
      "/api/record": () => jsonResponse(stale),
      "/api/file": () => {
        fileCalls += 1;
        return jsonResponse(fileCalls === 1 ? fileReadable : grown);
      },
    });
    render(<RunDetail params={runParams} fetcher={fetcher} pollMs={50} />);
    await until(() => screen.queryByText(/still running/) !== null);
  });

  it("lets a slow log response finish instead of restarting it on every poll", async () => {
    const running = structuredClone(recordRun);
    running.record.state = "running";
    running.record.display_state = "running";
    let release: (response: Response) => void = () => {};
    let fileCalls = 0;
    let recordCalls = 0;
    const fetcher = routeFetcher({
      "/api/record": () => {
        recordCalls += 1;
        return jsonResponse(running);
      },
      "/api/file": () => {
        fileCalls += 1;
        return new Promise<Response>((resolve) => {
          release = resolve;
        });
      },
    });
    render(<RunDetail params={runParams} fetcher={fetcher} pollMs={20} />);
    await until(() => recordCalls >= 4);
    expect(fileCalls).toBe(1);
    await act(async () => {
      release(jsonResponse(fileReadable));
    });
    expect(await screen.findByText(/worker started/, undefined, SLOW)).toBeInTheDocument();
  });

  it("fetches the final log when the record ends during a slow request", async () => {
    const running = structuredClone(recordRun);
    running.record.state = "running";
    running.record.display_state = "running";
    const done = structuredClone(running);
    done.record.state = "done";
    done.record.display_state = "done";
    done.record.updated_at = "2026-11-06T00:00:00+09:00";
    const final = structuredClone(fileReadable);
    final.text += "12:59:00 final line\n";
    let release: (response: Response) => void = () => {};
    let ended = false;
    let fileCalls = 0;
    const fetcher = routeFetcher({
      "/api/record": () => jsonResponse(ended ? done : running),
      "/api/file": () => {
        fileCalls += 1;
        if (fileCalls > 1) return jsonResponse(final);
        return new Promise<Response>((resolve) => {
          release = resolve;
        });
      },
    });
    render(<RunDetail params={runParams} fetcher={fetcher} pollMs={20} />);
    await until(() => fileCalls === 1);
    ended = true;
    await until(
      () => document.querySelector('.detail-head .state-badge[data-state="done"]') !== null,
    );
    await act(async () => {
      release(jsonResponse(fileReadable));
    });
    await until(() => screen.queryByText(/final line/) !== null);
    expect(fileCalls).toBe(2);
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

    expect(await screen.findByText(/worker started/, undefined, SLOW)).toBeInTheDocument();
    await until(() => fileCalls > 0);
    const afterFirst = fileCalls;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 100));
    });
    expect(fileCalls).toBe(afterFirst);
  });

  it("hides the sections that do not apply to a job", async () => {
    const fetcher = routeFetcher({
      "/api/record": () => jsonResponse(recordJob),
      "/api/file": () => jsonResponse(fileReadable),
    });
    render(<RunDetail params={jobParams} fetcher={fetcher} />);

    expect(await screen.findByRole("heading", { name: "web build" }, SLOW)).toBeInTheDocument();
    expect(screen.queryByText("Usage")).toBeNull();
    expect(screen.queryByText("parent")).toBeNull();
    expect(screen.queryByText("spawned")).toBeNull();
    expect(screen.queryByText("continues")).toBeNull();
    expect(screen.getByText("inbox item")).toBeInTheDocument();
    expect(screen.getByText("Version history")).toBeInTheDocument();
  });
});

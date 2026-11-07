import { useEffect, useRef, useState } from "react";
import type { Board, Snapshot } from "./types";
import { boardUrl, snapshotUrl, type Fetcher } from "./client";

export interface PollState<T> {
  status: "loading" | "ok" | "unavailable";
  data: T | null;
  receivedAt: number | null;
  error: string | null;
}

function initial<T>(): PollState<T> {
  return { status: "loading", data: null, receivedAt: null, error: null };
}

/**
 * Polls one JSON endpoint with If-None-Match, one request in flight at a time.
 * It pauses while the document is hidden and refreshes once on return. Any
 * failure leaves the last good data on screen, marked old, and never claims it
 * is current.
 */
export function usePolling<T extends { api: 1 }>(
  fetcher: Fetcher,
  url: string,
  pollMs: number,
): PollState<T> {
  const [state, setState] = useState<PollState<T>>(initial);
  const etag = useRef<string | null>(null);
  const lastGood = useRef<{ data: T; receivedAt: number } | null>(null);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inFlight = false;

    const schedule = () => {
      if (!stopped && !document.hidden) timer = setTimeout(tick, pollMs);
    };

    async function tick() {
      if (stopped || inFlight) return;
      if (document.hidden) return; // paused; visibilitychange resumes
      inFlight = true;
      try {
        const headers: Record<string, string> = {};
        if (etag.current) headers["If-None-Match"] = etag.current;
        const response = await fetcher(url, { headers, cache: "no-store" });

        if (response.status === 304) {
          if (!lastGood.current) throw new Error("HTTP 304 without cached data");
          // 304 is a successful validation: the data is still current, so the
          // last-refresh time moves to the 304's time.
          const receivedAt = Date.now();
          const current = { data: lastGood.current.data, receivedAt };
          lastGood.current = current;
          if (!stopped) {
            setState({ status: "ok", data: current.data, receivedAt, error: null });
          }
        } else if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        } else {
          const body = (await response.json()) as T;
          if (body.api !== 1) throw new Error(`unsupported API version ${String(body.api)}`);
          const tag = response.headers.get("ETag");
          if (tag) etag.current = tag;
          const receivedAt = Date.now();
          lastGood.current = { data: body, receivedAt };
          if (!stopped) {
            setState({ status: "ok", data: body, receivedAt, error: null });
          }
        }
      } catch (error) {
        if (!stopped) {
          setState({
            status: "unavailable",
            data: lastGood.current?.data ?? null,
            receivedAt: lastGood.current?.receivedAt ?? null,
            error: error instanceof Error ? error.message : String(error),
          });
        }
      } finally {
        inFlight = false;
        schedule();
      }
    }

    const onVisibilityChange = () => {
      if (!document.hidden) {
        clearTimeout(timer);
        void tick();
      }
    };

    void tick();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      stopped = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [fetcher, url, pollMs]);

  return state;
}

export function useBoard(fetcher: Fetcher, pollMs: number): PollState<Board> {
  return usePolling<Board>(fetcher, boardUrl(), pollMs);
}

export function useSnapshot(fetcher: Fetcher, pollMs: number): PollState<Snapshot> {
  return usePolling<Snapshot>(fetcher, snapshotUrl(), pollMs);
}

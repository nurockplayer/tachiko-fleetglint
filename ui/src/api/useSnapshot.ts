import { useEffect, useRef, useState } from "react";
import type { Snapshot } from "./types";
import { snapshotUrl, type Fetcher } from "./client";

export interface SnapshotState {
  status: "loading" | "ok" | "unavailable";
  snapshot: Snapshot | null;
  receivedAt: number | null;
  error: string | null;
}

interface LastGood {
  snapshot: Snapshot;
  receivedAt: number;
}

/**
 * Polls /api/snapshot with If-None-Match and pauses while the document is
 * hidden. Any failure leaves the last good snapshot on screen, marked old, and
 * never claims it is current.
 */
export function useSnapshot(fetcher: Fetcher, pollMs: number): SnapshotState {
  const [state, setState] = useState<SnapshotState>({
    status: "loading",
    snapshot: null,
    receivedAt: null,
    error: null,
  });
  const etag = useRef<string | null>(null);
  const lastGood = useRef<LastGood | null>(null);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const schedule = () => {
      if (!stopped) timer = setTimeout(tick, pollMs);
    };

    async function tick() {
      if (document.hidden) {
        schedule();
        return;
      }
      try {
        const headers: Record<string, string> = {};
        if (etag.current) headers["If-None-Match"] = etag.current;
        const response = await fetcher(snapshotUrl(), { headers, cache: "no-store" });

        if (response.status === 304) {
          if (!lastGood.current) throw new Error("HTTP 304 without cached data");
          if (!stopped) {
            setState({
              status: "ok",
              snapshot: lastGood.current.snapshot,
              receivedAt: lastGood.current.receivedAt,
              error: null,
            });
          }
        } else if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        } else {
          const body = (await response.json()) as Snapshot;
          if (body.api !== 1) throw new Error(`unsupported API version ${String(body.api)}`);
          const tag = response.headers.get("ETag");
          if (tag) etag.current = tag;
          const receivedAt = Date.now();
          lastGood.current = { snapshot: body, receivedAt };
          if (!stopped) {
            setState({ status: "ok", snapshot: body, receivedAt, error: null });
          }
        }
      } catch (error) {
        if (!stopped) {
          setState({
            status: "unavailable",
            snapshot: lastGood.current?.snapshot ?? null,
            receivedAt: lastGood.current?.receivedAt ?? null,
            error: error instanceof Error ? error.message : String(error),
          });
        }
      }
      schedule();
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
  }, [fetcher, pollMs]);

  return state;
}

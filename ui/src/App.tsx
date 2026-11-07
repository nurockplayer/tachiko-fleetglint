import { useEffect, type ReactNode } from "react";
import { defaultFetcher, type Fetcher } from "./api/client";
import { useBoard } from "./api/useSnapshot";
import { useRoute } from "./router";
import { formatTimeOfDay } from "./format";
import { TopBar } from "./components/TopBar";
import { Banner } from "./components/Banner";
import { OverviewSkeleton } from "./components/Skeleton";
import { Overview } from "./screens/Overview";
import { History } from "./screens/History";
import { RunDetail } from "./screens/RunDetail";

export interface AppProps {
  fetcher?: Fetcher;
  pollMs?: number;
}

export function App({ fetcher = defaultFetcher, pollMs = 15000 }: AppProps) {
  const route = useRoute();
  const state = useBoard(fetcher, pollMs);
  const board = state.data;
  const unavailable = state.status === "unavailable";
  const firstLoad = state.status === "loading";

  // `/attention` is retired; keep old bookmarks working without a page load.
  useEffect(() => {
    if (window.location.pathname === "/attention") {
      window.history.replaceState(null, "", "/");
    }
  }, []);

  const lastSuccess =
    state.receivedAt != null
      ? formatTimeOfDay(new Date(state.receivedAt).toISOString())
      : "";

  let content: ReactNode;
  if (route.kind === "history") {
    content = <History fetcher={fetcher} pollMs={pollMs} />;
  } else if (route.kind === "detail") {
    content = <RunDetail params={route.params} fetcher={fetcher} pollMs={pollMs} />;
  } else if (firstLoad && !board) {
    content = (
      <main className="screen">
        <OverviewSkeleton />
      </main>
    );
  } else if (board) {
    content = (
      <div className={`stale-data${unavailable ? " is-stale" : ""}`}>
        <Overview board={board} />
      </div>
    );
  } else {
    content = (
      <main className="screen">
        <p className="quiet">
          No data available. Fleetglint cannot reach the local API.
        </p>
      </main>
    );
  }

  return (
    <div className="app">
      <TopBar board={board} receivedAt={state.receivedAt} />
      <div className="banner-stack">
        {unavailable ? (
          <Banner kind="unavailable">
            {state.error ?? "the API could not be read"}
            {lastSuccess ? ` · last successful refresh ${lastSuccess}` : ""} · current
            state cannot be verified
          </Banner>
        ) : null}
        {board?.demo && !unavailable ? (
          <Banner kind="demo">Sample records from fleetglint demo · not real work</Banner>
        ) : null}
      </div>
      {content}
    </div>
  );
}

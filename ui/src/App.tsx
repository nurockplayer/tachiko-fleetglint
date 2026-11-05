import type { ReactNode } from "react";
import type { Snapshot } from "./api/types";
import { defaultFetcher, type Fetcher } from "./api/client";
import { useSnapshot } from "./api/useSnapshot";
import { useRoute, type Route } from "./router";
import { formatClock } from "./format";
import { Banner, TopBar } from "./components/Panels";
import { Overview } from "./screens/Overview";
import { Attention } from "./screens/Attention";
import { RunDetail } from "./screens/RunDetail";

export interface AppProps {
  fetcher?: Fetcher;
  pollMs?: number;
}

function routeView(route: Route, snapshot: Snapshot, fetcher: Fetcher) {
  if (route.kind === "attention") return <Attention snapshot={snapshot} />;
  if (route.kind === "detail") {
    return <RunDetail params={route.params} fetcher={fetcher} />;
  }
  return <Overview snapshot={snapshot} />;
}

function sourceBanners(snapshot: Snapshot) {
  return (
    <>
      {snapshot.sources
        .filter((source) => source.status === "discontinuity")
        .map((source) => (
          <Banner kind="discontinuity" key={`disc-${source.source_id}`}>
            {source.source_id}: {source.detail ?? "the source has a discontinuity"}
          </Banner>
        ))}
      {snapshot.sources
        .filter((source) => source.status === "unavailable")
        .map((source) => (
          <Banner kind="unavailable" key={`unavail-${source.source_id}`}>
            {source.source_id}: {source.detail ?? "the source cannot be read"}
          </Banner>
        ))}
      {snapshot.sources
        .filter((source) => source.quarantine_count > 0)
        .map((source) => (
          <Banner kind="quarantine" key={`quar-${source.source_id}`}>
            {source.source_id}: {source.quarantine_count} bad line
            {source.quarantine_count === 1 ? "" : "s"} quarantined and not shown
          </Banner>
        ))}
    </>
  );
}

export function App({ fetcher = defaultFetcher, pollMs = 3000 }: AppProps) {
  const state = useSnapshot(fetcher, pollMs);
  const route = useRoute();
  const snapshot = state.snapshot;
  const unavailable = state.status === "unavailable";
  const lastGoodClock =
    state.receivedAt != null
      ? formatClock(new Date(state.receivedAt).toISOString())
      : null;

  let content: ReactNode = null;
  if (state.status === "loading") {
    content = (
      <main className="screen">
        <p className="muted">connecting to fleetglint…</p>
      </main>
    );
  } else if (snapshot) {
    if (unavailable) {
      content = (
        <>
          <p className="stale-note">
            Showing last good data from {lastGoodClock ?? "an earlier poll"} — not
            current.
          </p>
          <div className="stale-data" data-stale="true">
            {routeView(route, snapshot, fetcher)}
          </div>
        </>
      );
    } else {
      content = routeView(route, snapshot, fetcher);
    }
  }

  return (
    <div className="app">
      <TopBar snapshot={snapshot} lastRefreshAt={state.receivedAt} />
      <div className="banner-stack">
        {unavailable ? (
          <Banner kind="unavailable">
            {state.error}
            {lastGoodClock
              ? ` — last good data from ${lastGoodClock}`
              : " — no data available"}
          </Banner>
        ) : null}
        {snapshot?.demo ? (
          <Banner kind="demo">sample records from fleetglint demo — not real work</Banner>
        ) : null}
        {!unavailable && snapshot ? sourceBanners(snapshot) : null}
      </div>
      {content}
    </div>
  );
}

import type { Fetcher } from "../api/client";
import { useSnapshot } from "../api/useSnapshot";
import type { JobSummary, RunSummary } from "../api/types";
import { ageSince, countNoun, formatAgo } from "../format";
import { detailHref } from "../router";
import { StateBadge } from "../components/StateBadge";
import { Banner } from "../components/Banner";

type HistoryItem = RunSummary | JobSummary;

const CAP = 500;

function itemTitle(item: HistoryItem): string {
  if (item.ref.type === "job") {
    return item.title ?? (item as JobSummary).command_summary;
  }
  return item.title ?? item.ref.id;
}

function itemRole(item: HistoryItem): string | null {
  return item.ref.type === "job"
    ? (item as JobSummary).role_id
    : (item as RunSummary).role_id;
}

function HistoryRow({ item, now }: { item: HistoryItem; now: number }) {
  const role = itemRole(item);
  const started = formatAgo(ageSince(item.started_at, now));
  const updated = formatAgo(ageSince(item.updated_at, now));
  const meta = [role, item.project, started ? `started ${started}` : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <a
      className="work-row history-row"
      href={detailHref(item.ref)}
      data-state={item.display_state}
      data-record-id={item.ref.id}
    >
      <span className="row-badge">
        <StateBadge state={item.display_state} />
      </span>
      <span className="row-main">
        <span className="row-title">{itemTitle(item)}</span>
        <span className="row-meta">{meta}</span>
      </span>
      {updated ? <span className="row-age">updated {updated}</span> : null}
    </a>
  );
}

/**
 * The plain record list behind the board's aggregates: every run and job in
 * the window, including the old unverified records the board never renders
 * one by one.
 */
export function History({ fetcher, pollMs = 15000 }: { fetcher: Fetcher; pollMs?: number }) {
  const state = useSnapshot(fetcher, pollMs);

  if (state.status === "loading") {
    return (
      <main className="screen history">
        <p className="quiet">Loading history…</p>
      </main>
    );
  }

  if (!state.data) {
    return (
      <main className="screen history">
        <Banner kind="unavailable">
          {state.error ?? "the record list could not be read"} · current state cannot be
          verified
        </Banner>
      </main>
    );
  }

  const snapshot = state.data;
  const now = Date.parse(snapshot.generated_at);
  const items: HistoryItem[] = [...snapshot.runs, ...snapshot.jobs].sort(
    (a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at),
  );

  return (
    <main className="screen history">
      {state.status === "unavailable" ? (
        <Banner kind="unavailable">
          {state.error ?? "the record list could not be read"} · current state cannot be
          verified
        </Banner>
      ) : null}
      <header className="history-head">
        <h1>History</h1>
        <p className="history-note">
          At most {CAP} records per list; older records are not shown.
        </p>
        {snapshot.truncated.runs ? (
          <p className="truncation-note">
            showing the newest {snapshot.runs.length} runs; more exist
          </p>
        ) : null}
        {snapshot.truncated.jobs ? (
          <p className="truncation-note">
            showing the newest {snapshot.jobs.length} jobs; more exist
          </p>
        ) : null}
        <p className="history-note">
          {countNoun(snapshot.runs.length, "run")} · {countNoun(snapshot.jobs.length, "job")}
        </p>
      </header>
      <div className={`stale-data${state.status === "unavailable" ? " is-stale" : ""}`}>
        <div className="row-list">
          {items.map((item) => (
            <HistoryRow
              key={`${item.ref.source_id}/${item.ref.type}/${item.ref.id}`}
              item={item}
              now={now}
            />
          ))}
        </div>
        {items.length === 0 ? <p className="quiet">No records in the window.</p> : null}
      </div>
    </main>
  );
}

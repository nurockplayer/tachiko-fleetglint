import type { Snapshot } from "../api/types";
import { RefLink } from "../components/Refs";

export function Attention({ snapshot }: { snapshot: Snapshot }) {
  const entries = snapshot.attention;
  return (
    <main className="screen">
      <div className="screen-head">
        <h1>Needs attention</h1>
        <p className="summary-line">
          who must act, about what · {entries.length} item{entries.length === 1 ? "" : "s"}
        </p>
        {snapshot.counts.attention > entries.length ? (
          <p className="truncation-note">
            Showing {entries.length} of {snapshot.counts.attention}
          </p>
        ) : null}
        {snapshot.truncated.inbox ? (
          <p className="truncation-note">
            the inbox list is cut at {snapshot.inbox.length} items; more exist, so
            some entries here may be missing
          </p>
        ) : null}
      </div>
      {entries.length === 0 ? (
        <p className="muted">Nothing needs attention.</p>
      ) : (
        <ol className="attention-list">
          {entries.map((entry, index) => (
            <li
              className={`attention-row reason-${entry.reason}`}
              key={`${entry.reason}/${entry.source_id}/${index}`}
              data-reason={entry.reason}
            >
              <span className="attention-reason">{entry.reason}</span>
              <span className="attention-text">{entry.text}</span>
              <span className="attention-subject">
                <span className="attention-who">{entry.who ?? "unassigned"}</span>
                {entry.subject ? (
                  <RefLink ref={entry.subject} />
                ) : (
                  <span className="mono muted">{entry.source_id}</span>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}

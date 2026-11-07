import type { Board, Source } from "../api/types";
import { formatAgo, sourceName } from "../format";

function sourceProblem(source: Source): string | null {
  if (source.status === "discontinuity") return "Data gap";
  if (source.status === "unavailable") return "Unavailable";
  if (source.status === "quarantine") return "Quarantined";
  return null;
}

function SourceChip({ source }: { source: Source }) {
  const problem = sourceProblem(source);
  return (
    <span
      className="source-chip"
      data-status={source.status}
      data-source-id={source.source_id}
      title={source.source_id}
    >
      <span className="source-dot" aria-hidden="true" />
      <span className="source-name">{sourceName(source.source_id)}</span>
      {problem ? <span className="source-problem">{problem}</span> : null}
      {source.quarantine_count > 0 ? (
        <span className="source-problem">{source.quarantine_count} quarantined</span>
      ) : null}
    </span>
  );
}

export interface TopBarProps {
  board: Board | null;
  receivedAt: number | null;
}

/** The 56 px chrome bar; the machine id stays in each chip's tooltip. */
export function TopBar({ board, receivedAt }: TopBarProps) {
  const updated = receivedAt
    ? formatAgo((Date.now() - receivedAt) / 1000)
    : "";
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <a className="mark" href="/">
          Fleetglint
        </a>
        <div className="source-strip" aria-label="sources">
          {board?.sources.map((source) => (
            <SourceChip key={source.source_id} source={source} />
          ))}
        </div>
        <div className="topbar-meta">
          {updated ? <span>updated {updated}</span> : null}
          <span className="read-only">Read only</span>
        </div>
      </div>
    </header>
  );
}

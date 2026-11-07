import type { Board, BoardWork } from "../api/types";
import { StateBadge } from "./StateBadge";
import { CollapsibleSection } from "./Section";
import { WorkRow, updatedAgo, workRole, workTitle } from "./Rows";

function RecentRow({ work, now }: { work: BoardWork; now: number }) {
  const role = workRole(work);
  const age = updatedAgo(work, now);
  return (
    <WorkRow
      work={work}
      className="recent-row"
      glyph={<StateBadge state={work.display_state} variant="glyph" />}
    >
      <span className="row-title">{workTitle(work)}</span>
      {role ? <span className="row-role">{role}</span> : null}
      {age ? <span className="row-age">{age}</span> : null}
    </WorkRow>
  );
}

function RecentGroup({
  state,
  heading,
  rows,
  now,
}: {
  state: BoardWork["display_state"];
  heading: string;
  rows: BoardWork[];
  now: number;
}) {
  if (rows.length === 0) return null;
  return (
    <div className="recent-group">
      <h3 className="group-heading">
        <StateBadge state={state} variant="glyph" />
        {heading}
        <span className="group-count">{rows.length}</span>
      </h3>
      {rows.map((work) => (
        <RecentRow key={`${work.ref.source_id}/${work.ref.id}`} work={work} now={now} />
      ))}
    </div>
  );
}

export interface RecentProps {
  board: Board;
  open: boolean;
  onToggle: () => void;
}

/** Collapsed line; expanding lists failures first, then the newest done. */
export function Recent({ board, open, onToggle }: RecentProps) {
  const now = Date.parse(board.generated_at);
  const failed = board.recent.filter((work) => work.display_state === "failed");
  const done = board.recent.filter((work) => work.display_state === "done");
  const cancelled = board.recent.filter((work) => work.display_state === "cancelled");

  return (
    <CollapsibleSection
      id="recent"
      heading="Recent"
      summary={`${board.counts.failed_recent} failed · ${done.length} done`}
      open={open}
      onToggle={onToggle}
      ariaLabel="Recent"
    >
      {board.recent.length === 0 ? (
        <p className="quiet">Nothing finished in the last {board.window_hours} hours.</p>
      ) : null}
      <RecentGroup state="failed" heading="Failed" rows={failed} now={now} />
      <RecentGroup state="done" heading="Done" rows={done} now={now} />
      <RecentGroup state="cancelled" heading="Cancelled" rows={cancelled} now={now} />
      {board.truncated.recent ? (
        <p className="truncation-note">
          showing the newest {board.recent.length}; more exist
        </p>
      ) : null}
    </CollapsibleSection>
  );
}

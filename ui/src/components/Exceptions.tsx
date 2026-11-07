import type { Board, BoardWork } from "../api/types";
import { StateBadge, type StateBadgeProps } from "./StateBadge";
import { CollapsibleSection } from "./Section";
import { WorkRow, updatedAgo, workRole, workTitle } from "./Rows";

function ExceptionRow({ work, now }: { work: BoardWork; now: number }) {
  const role = workRole(work);
  const age = updatedAgo(work, now);
  return (
    <WorkRow
      work={work}
      className="exception-row"
      glyph={<StateBadge state={work.display_state} variant="glyph" />}
    >
      <span className="row-title">{workTitle(work)}</span>
      {role ? <span className="row-role">{role}</span> : null}
      {age ? <span className="row-age">{age}</span> : null}
    </WorkRow>
  );
}

function ExceptionGroup({
  state,
  heading,
  rows,
  now,
}: {
  state: StateBadgeProps["state"];
  heading: string;
  rows: BoardWork[];
  now: number;
}) {
  if (rows.length === 0) return null;
  return (
    <div className="exception-group">
      <h3 className="group-heading">
        <StateBadge state={state} variant="glyph" />
        {heading}
        <span className="group-count">{rows.length}</span>
      </h3>
      {rows.map((work) => (
        <ExceptionRow key={`${work.ref.source_id}/${work.ref.id}`} work={work} now={now} />
      ))}
    </div>
  );
}

export interface ExceptionsProps {
  board: Board;
  open: boolean;
  onToggle: () => void;
}

/** Separate counters, never one combined number; old unverified records stay an aggregate. */
export function Exceptions({ board, open, onToggle }: ExceptionsProps) {
  const { counts, exceptions } = board;
  const total = counts.process_gone + counts.out_of_date + counts.unverified_recent;
  const now = Date.parse(board.generated_at);

  const subline = (
    <>
      <span>{counts.process_gone} process gone</span>
      <span className="summary-dot"> · </span>
      <span>{counts.out_of_date} out of date</span>
      <span className="summary-dot"> · </span>
      <span>{counts.unverified_recent} unverified</span>
      {counts.older_unverified > 0 ? (
        <>
          <span className="summary-dot"> · </span>
          <a href="/history">
            {counts.older_unverified} older records unverified, in history
          </a>
        </>
      ) : null}
      {board.truncated.exceptions ? (
        <span className="truncation-note"> · showing the newest of each</span>
      ) : null}
    </>
  );

  return (
    <CollapsibleSection
      id="exceptions"
      heading={`${total} exceptions`}
      open={open}
      onToggle={onToggle}
      ariaLabel="Exceptions"
      subline={subline}
    >
      <ExceptionGroup
        state="lost"
        heading="Process gone"
        rows={exceptions.process_gone}
        now={now}
      />
      <ExceptionGroup
        state="stale"
        heading="Out of date"
        rows={exceptions.out_of_date}
        now={now}
      />
      <ExceptionGroup
        state="unknown"
        heading="Unverified"
        rows={exceptions.unverified_recent}
        now={now}
      />
    </CollapsibleSection>
  );
}

import type { Board, BoardWork } from "../api/types";
import { StateBadge } from "./StateBadge";
import { Section } from "./Section";
import { WorkRow, waitWords, workDuration, workRole, workTitle } from "./Rows";

function WaitingRow({ work }: { work: BoardWork }) {
  const role = workRole(work);
  const duration = workDuration(work);
  return (
    <WorkRow
      work={work}
      className="waiting-row"
      glyph={<StateBadge state="waiting" variant="glyph" />}
    >
      <span className="row-main">
        <span className="row-title">{workTitle(work)}</span>
        {role ? <span className="row-role">{role}</span> : null}
      </span>
      <span className="row-detail">
        <span className="row-what">{waitWords(work)}</span>
        {duration ? <span className="row-age">{duration}</span> : null}
      </span>
    </WorkRow>
  );
}

/** Waiting work, longest first. The heading carries the state, so rows show only its glyph. */
export function Waiting({ board }: { board: Board }) {
  const rows = [...board.waiting].sort(
    (a, b) => (b.started_age_s ?? -1) - (a.started_age_s ?? -1),
  );
  return (
    <Section
      id="waiting"
      heading={`Waiting ${board.counts.waiting}`}
      aside={
        board.truncated.waiting ? (
          <span className="truncation-note">showing the newest {rows.length}</span>
        ) : null
      }
      ariaLabel="Waiting"
    >
      {rows.length === 0 ? (
        <p className="quiet">Nothing waiting.</p>
      ) : (
        <div className="row-list">
          {rows.map((work) => (
            <WaitingRow key={`${work.ref.source_id}/${work.ref.id}`} work={work} />
          ))}
        </div>
      )}
    </Section>
  );
}

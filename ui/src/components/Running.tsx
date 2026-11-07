import type { Board, BoardWork } from "../api/types";
import { formatAgo } from "../format";
import { StateBadge } from "./StateBadge";
import { Section } from "./Section";
import {
  WorkRow,
  checkText,
  freshestProcessCheck,
  workCommand,
  workDuration,
  workModel,
  workRole,
  workTitle,
} from "./Rows";

function projectOf(work: BoardWork): string {
  return work.project ?? "no project";
}

function groupRunning(
  rows: BoardWork[],
  order: string[],
): Array<{ project: string; rows: BoardWork[] }> {
  const groups = new Map<string, BoardWork[]>();
  for (const row of rows) {
    const project = projectOf(row);
    const existing = groups.get(project);
    if (existing) existing.push(row);
    else groups.set(project, [row]);
  }
  const listed = order.filter((project) => groups.has(project));
  for (const project of [...groups.keys()].sort()) {
    if (!listed.includes(project)) listed.push(project);
  }
  return listed.map((project) => ({ project, rows: groups.get(project) ?? [] }));
}

function RunningRow({ work, referenceAge }: { work: BoardWork; referenceAge: number | null }) {
  const role = workRole(work);
  const model = workModel(work);
  const check = checkText(work, referenceAge);
  const duration = workDuration(work);
  return (
    <WorkRow
      work={work}
      className="running-row"
      glyph={<StateBadge state="running" variant="glyph" />}
    >
      <span className="row-title mono">{workTitle(work)}</span>
      {role ? <span className="row-role">{role}</span> : null}
      {model ? <span className="row-model">{model}</span> : null}
      {check ? <span className="row-check">{check}</span> : null}
      {duration ? <span className="row-age">{duration}</span> : null}
    </WorkRow>
  );
}

function QueuedRow({ work }: { work: BoardWork }) {
  const command = workCommand(work);
  return (
    <WorkRow
      work={work}
      className="queued-row"
      glyph={<StateBadge state="queued" variant="glyph" />}
    >
      <span className="row-main">
        <span className="row-title mono">{workTitle(work)}</span>
        {command ? <span className="row-command mono">{command}</span> : null}
      </span>
    </WorkRow>
  );
}

export interface RunningProps {
  board: Board;
  /** Project order from the first sighting; a refresh never reorders groups. */
  projectOrder: string[];
}

/** Running work grouped by project, with a small Queued group at the end. */
export function Running({ board, projectOrder }: RunningProps) {
  const groups = groupRunning(board.running, projectOrder);
  const freshest = freshestProcessCheck(board.running);
  const checkSummary = freshest == null ? "process checks not observable" : `process checks ${formatAgo(freshest)}`;
  const queued = board.queued;

  return (
    <Section
      id="running"
      heading={`Running ${board.counts.running}`}
      aside={
        <span className="section-check">
          {checkSummary}
          {board.truncated.running ? (
            <span className="truncation-note"> · showing the newest {board.running.length}</span>
          ) : null}
        </span>
      }
      ariaLabel="Running"
    >
      <div className="column-head" aria-hidden="true">
        <span />
        <span>worker</span>
        <span>role</span>
        <span>model</span>
        <span>checked</span>
        <span className="column-age">running</span>
      </div>
      {groups.length === 0 ? <p className="quiet">Nothing running.</p> : null}
      {groups.map((group) => (
        <div className="running-group" key={group.project}>
          <h3 className="group-heading">
            {group.project}
            <span className="group-count">{group.rows.length}</span>
          </h3>
          {group.rows.map((work) => (
            <RunningRow
              key={`${work.ref.source_id}/${work.ref.id}`}
              work={work}
              referenceAge={freshest}
            />
          ))}
        </div>
      ))}
      {board.counts.queued > 0 ? (
        <div className="running-group queued-group" id="queued">
          <h3 className="group-heading">
            Queued {board.counts.queued}
            {board.truncated.queued ? (
              <span className="truncation-note">showing the newest {queued.length}</span>
            ) : null}
          </h3>
          {queued.map((work) => (
            <QueuedRow key={`${work.ref.source_id}/${work.ref.id}`} work={work} />
          ))}
        </div>
      ) : null}
    </Section>
  );
}

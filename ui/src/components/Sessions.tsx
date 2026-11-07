import type { Board, SessionSummary } from "../api/types";
import { ageSince, formatAgo } from "../format";
import { StateBadge } from "./StateBadge";
import { CollapsibleSection, Section } from "./Section";

const SESSION_EXPLAIN =
  "Session history shows recent activity, not whether a process is running. Connect a source with process evidence to see running work.";

function SessionRow({ session, now }: { session: SessionSummary; now: number }) {
  const age = formatAgo(session.evidence.age_s ?? ageSince(session.last_activity_at, now));
  return (
    <div
      className="work-row session-row"
      data-state={session.display_state}
      data-record-id={session.ref.id}
    >
      <span className="row-glyph">
        <StateBadge state={session.display_state} variant="glyph" />
      </span>
      <span className="row-main">
        <span className="row-title">{session.title ?? session.ref.id}</span>
        <span className="row-meta">
          <span>{session.agent}</span>
          {session.model ? <span> · {session.model}</span> : null}
          {session.project ? <span> · {session.project}</span> : null}
        </span>
      </span>
      {age ? <span className="row-age">last activity {age}</span> : null}
    </div>
  );
}

function SessionGroups({ sessions, now }: { sessions: SessionSummary[]; now: number }) {
  const groups = [
    { state: "recent" as const, heading: "Recent sessions" },
    { state: "idle" as const, heading: "Idle" },
    { state: "ended" as const, heading: "Ended" },
  ];
  return (
    <>
      {groups.map(({ state, heading }) => {
        const rows = sessions.filter((session) => session.display_state === state);
        if (rows.length === 0) return null;
        return (
          <div className="session-group" key={state}>
            <h3 className="group-heading">
              <StateBadge state={state} variant="glyph" />
              {heading}
              <span className="group-count">{rows.length}</span>
            </h3>
            {rows.map((session) => (
              <SessionRow
                key={`${session.ref.source_id}/${session.ref.id}`}
                session={session}
                now={now}
              />
            ))}
          </div>
        );
      })}
    </>
  );
}

export interface SessionsProps {
  board: Board;
  open: boolean;
  onToggle: () => void;
}

/** A collapsed line at the bottom when execution is observable (visual spec §5). */
export function Sessions({ board, open, onToggle }: SessionsProps) {
  const now = Date.parse(board.generated_at);
  return (
    <CollapsibleSection
      id="sessions"
      heading={`Sessions ${board.sessions_total}`}
      open={open}
      onToggle={onToggle}
      ariaLabel="Sessions"
    >
      <SessionGroups sessions={board.sessions} now={now} />
    </CollapsibleSection>
  );
}

/**
 * The sessions-only first run: activity is all the store has, so the page says
 * what is not observable instead of showing a zero.
 */
export function SessionsOnly({ board }: { board: Board }) {
  const now = Date.parse(board.generated_at);
  return (
    <Section id="sessions" heading="Recent sessions" ariaLabel="Recent sessions">
      <p className="session-explain">{SESSION_EXPLAIN}</p>
      <SessionGroups sessions={board.sessions} now={now} />
    </Section>
  );
}

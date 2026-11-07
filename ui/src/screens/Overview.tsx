import { useRef, useState } from "react";
import type { Board } from "../api/types";
import { SummaryLine } from "../components/SummaryLine";
import { Notified } from "../components/Notified";
import { Waiting } from "../components/Waiting";
import { Running } from "../components/Running";
import { LeadInbox } from "../components/LeadInbox";
import { Exceptions } from "../components/Exceptions";
import { Recent } from "../components/Recent";
import { Sessions, SessionsOnly } from "../components/Sessions";
import { EmptyState } from "../components/EmptyState";

type SectionKey = "lead_inbox" | "exceptions" | "recent" | "sessions";

const INITIAL_OPEN: Record<SectionKey, boolean> = {
  lead_inbox: false,
  exceptions: false,
  recent: false,
  sessions: false,
};

/** First-seen project order, kept in a ref so a refresh never reorders groups. */
function useProjectOrder(board: Board): string[] {
  const order = useRef<string[]>([]);
  const seen = new Set(order.current);
  const fresh = Array.from(
    new Set(board.running.map((work) => work.project ?? "no project")),
  ).filter((project) => !seen.has(project));
  if (fresh.length > 0) order.current = [...order.current, ...fresh];
  return order.current;
}

/**
 * The viewer's first screen (visual spec §5), top to bottom and nothing else:
 * notification, waiting and running work at a glance, then quiet aggregates.
 */
export function Overview({ board }: { board: Board }) {
  const [open, setOpen] = useState<Record<SectionKey, boolean>>(INITIAL_OPEN);
  const projectOrder = useProjectOrder(board);
  const toggle = (key: SectionKey) => () =>
    setOpen((previous) => ({ ...previous, [key]: !previous[key] }));

  if (board.sources.length === 0) {
    return (
      <main className="screen">
        <EmptyState />
      </main>
    );
  }

  const exceptions =
    board.counts.process_gone +
    board.counts.out_of_date +
    board.counts.unverified_recent;

  if (!board.capabilities.execution) {
    return (
      <main className="screen">
        <SummaryLine board={board} />
        {board.needs_you.length > 0 ? <Notified board={board} /> : null}
        <SessionsOnly board={board} />
      </main>
    );
  }

  return (
    <main className="screen">
      <SummaryLine board={board} />
      <Notified board={board} />
      <div className="columns">
        <Waiting board={board} />
        <Running board={board} projectOrder={projectOrder} />
      </div>
      {board.counts.lead_inbox_open > 0 ? (
        <LeadInbox board={board} open={open.lead_inbox} onToggle={toggle("lead_inbox")} />
      ) : null}
      {exceptions > 0 || board.counts.older_unverified > 0 ? (
        <Exceptions board={board} open={open.exceptions} onToggle={toggle("exceptions")} />
      ) : null}
      {board.counts.failed_recent > 0 || board.recent.length > 0 ? (
        <Recent board={board} open={open.recent} onToggle={toggle("recent")} />
      ) : null}
      {board.sessions.length > 0 ? (
        <Sessions board={board} open={open.sessions} onToggle={toggle("sessions")} />
      ) : null}
    </main>
  );
}

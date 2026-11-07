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

/** Summary-line links whose section collapses; following one expands it. */
const SUMMARY_SECTIONS: Record<string, SectionKey> = {
  "#lead-inbox": "lead_inbox",
  "#exceptions": "exceptions",
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
  const openSection = (href: string) => {
    const key = SUMMARY_SECTIONS[href];
    if (key) setOpen((previous) => ({ ...previous, [key]: true }));
  };

  if (board.sources.length === 0) {
    return (
      <main className="screen">
        <EmptyState />
      </main>
    );
  }

  if (!board.capabilities.execution) {
    return (
      <main className="screen">
        <SummaryLine board={board} onOpenSection={openSection} />
        {board.needs_you.length > 0 ? <Notified board={board} /> : null}
        {board.capabilities.requests ? (
          <LeadInbox board={board} open={open.lead_inbox} onToggle={toggle("lead_inbox")} />
        ) : null}
        <SessionsOnly board={board} />
      </main>
    );
  }

  return (
    <main className="screen">
      <SummaryLine board={board} onOpenSection={openSection} />
      <Notified board={board} />
      <div className="columns">
        <Waiting board={board} />
        <Running board={board} projectOrder={projectOrder} />
      </div>
      <LeadInbox board={board} open={open.lead_inbox} onToggle={toggle("lead_inbox")} />
      <Exceptions board={board} open={open.exceptions} onToggle={toggle("exceptions")} />
      {board.counts.failed_recent > 0 || board.recent.length > 0 ? (
        <Recent board={board} open={open.recent} onToggle={toggle("recent")} />
      ) : null}
      {board.sessions.length > 0 ? (
        <Sessions board={board} open={open.sessions} onToggle={toggle("sessions")} />
      ) : null}
    </main>
  );
}

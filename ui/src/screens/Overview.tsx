import { ProjectCard } from "../components/ProjectCard";
import { useState } from "react";
import type { Board } from "../api/types";
import { SummaryLine } from "../components/SummaryLine";
import { Notified } from "../components/Notified";
import { LeadInbox } from "../components/LeadInbox";
import { SessionsOnly } from "../components/Sessions";
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

export function Overview({ board }: { board: Board }) {
  const [open, setOpen] = useState<Record<SectionKey, boolean>>(INITIAL_OPEN);
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
      <SummaryLine board={board} />
      <div className="project-grid">
        {[...board.projects.filter(p => p.project !== null), ...board.projects.filter(p => p.project === null)].map(project => <ProjectCard key={project.project ?? "__global"} project={project} now={Date.parse(board.generated_at)} />)}
      </div>
    </main>
  );
}

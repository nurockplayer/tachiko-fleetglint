import { useState } from "react";
import type { Board, BoardInboxRole } from "../api/types";
import { ProjectCard } from "../components/ProjectCard";
import { LeadInbox } from "../components/LeadInbox";
import { Sessions } from "../components/Sessions";
import type { Mark } from "../seen";

export function Project({ board, name, mark }: { board: Board; name: string | null; mark?: Mark }) {
  const [inboxOpen, setInboxOpen] = useState(true);
  const [sessionsOpen, setSessionsOpen] = useState(true);
  const project = board.projects.find(p => p.project === name);
  if (!project) return <main className="screen"><p>No activity for {name ?? "Global"} in the window</p><a href="/">Back to overview</a></main>;
  const roles: BoardInboxRole[] = board.lead_inbox.flatMap(role => {
    const totals = role.by_project.find(entry => entry.project === name);
    if (!totals) return [];
    const items = project.lead_inbox.filter(item => item.role_id === role.role_id);
    return [{ ...role, items, ...totals }];
  });
  for (const item of project.lead_inbox) {
    if (!roles.some(role => role.role_id === item.role_id)) {
      const items = project.lead_inbox.filter(entry => entry.role_id === item.role_id);
      roles.push({ role_id: item.role_id, items, by_project: [], open: items.length,
        old: items.filter(entry => entry.age_s != null && entry.age_s > board.inbox_old_after_s).length,
        oldest_age_s: null, action_required: items.filter(entry => entry.action_required).length });
    }
  }
  const sessions = board.sessions.filter(session => session.project === name);
  const filtered = { ...board, lead_inbox: roles, sessions, sessions_total: sessions.length, truncated: { ...board.truncated, lead_inbox: false }, counts: { ...board.counts, lead_inbox_open: project.lead_inbox_open, lead_inbox_old: roles.reduce((n, role) => n + role.old, 0) } };
  const hiddenInbox = project.lead_inbox_open - project.lead_inbox.length;
  return <main className="screen"><p><a href="/">Back to overview</a></p><ProjectCard project={project} now={Date.parse(board.generated_at)} full mark={mark} /><LeadInbox board={filtered} open={inboxOpen} onToggle={() => setInboxOpen(!inboxOpen)} />{hiddenInbox > 0 && <p className="quiet">{hiddenInbox} lead inbox {hiddenInbox === 1 ? "message" : "messages"} not shown.</p>}<Sessions board={filtered} open={sessionsOpen} onToggle={() => setSessionsOpen(!sessionsOpen)} /></main>;
}

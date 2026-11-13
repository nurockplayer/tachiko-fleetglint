import { useState } from "react";
import type { Board } from "../api/types";
import { ProjectCard } from "../components/ProjectCard";
import { LeadInbox } from "../components/LeadInbox";
import { Sessions } from "../components/Sessions";

export function Project({ board, name }: { board: Board; name: string | null }) {
  const [inboxOpen, setInboxOpen] = useState(true);
  const [sessionsOpen, setSessionsOpen] = useState(true);
  const project = board.projects.find(p => p.project === name);
  if (!project) return <main className="screen"><p>No activity for {name ?? "Global"} in the window</p><a href="/">Back to overview</a></main>;
  const roles = board.lead_inbox.map(role => {
    const items = role.items.filter(item => item.project === name);
    const old = items.filter(item => item.age_s != null && item.age_s > board.inbox_old_after_s).length;
    return { ...role, items, open: items.length, old, action_required: items.filter(item => item.action_required).length };
  }).filter(role => role.items.length);
  const sessions = board.sessions.filter(session => session.project === name);
  const filtered = { ...board, lead_inbox: roles, sessions, sessions_total: sessions.length, counts: { ...board.counts, lead_inbox_open: roles.reduce((n, role) => n + role.open, 0), lead_inbox_old: roles.reduce((n, role) => n + role.old, 0) } };
  return <main className="screen"><p><a href="/">Back to overview</a></p><ProjectCard project={project} now={Date.parse(board.generated_at)} full /><LeadInbox board={filtered} open={inboxOpen} onToggle={() => setInboxOpen(!inboxOpen)} /><Sessions board={filtered} open={sessionsOpen} onToggle={() => setSessionsOpen(!sessionsOpen)} /></main>;
}

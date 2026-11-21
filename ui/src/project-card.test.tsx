import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { board } from "./fixtures/board";
import { Overview } from "./screens/Overview";
import { Project } from "./screens/Project";
import { ProjectCard } from "./components/ProjectCard";
import { Recent } from "./components/Recent";
import { parseRoute } from "./router";
import type { BoardInboxItem } from "./api/types";
import { formatAbsolute } from "./format";
import { App } from "./App";
import { jsonResponse, sequenceFetcher } from "./test-fetcher";

const project = { ...board.projects[1], lead_inbox: [] };
const sevenNeedsProject = {
  ...project,
  needs_you: Array.from({ length: 7 }, (_, i) => ({
    ...project.in_progress[0],
    ref: { ...project.in_progress[0].ref, id: `needs-${i + 1}` },
    title: `Needs item ${i + 1}`,
    display_state: "waiting" as const,
  })),
  needs_you_total: 7,
};
describe("project board", () => {
  it("hides session-only overview cards, Global included, and keeps its session on the project page", async () => {
    const name = "tokyo-mogu-mogu";
    const onlySession = { ...project, project: name, needs_you: [], needs_you_total: 0,
      in_progress: [], decisions: [], recent: { done: [], failed: [] },
      lead_inbox: [], lead_inbox_open: 0, sessions_recent: 1 };
    const sessionBoard = { ...board, projects: [onlySession, { ...onlySession, project: null }],
      sessions: [{ ...board.sessions[0], project: name, title: "Session-only activity" }], sessions_total: 1 };
    const { fetcher } = sequenceFetcher([() => jsonResponse(sessionBoard)]);
    window.history.replaceState(null, "", "/");
    const overview = render(<App fetcher={fetcher} />);
    await screen.findByText(`${board.counts.running} running`);
    expect(overview.container.querySelector(".project-card")).toBeNull();
    overview.unmount();

    window.history.replaceState(null, "", `/project?name=${name}`);
    render(<App fetcher={fetcher} />);
    expect(await screen.findByText("Session-only activity")).toBeInTheDocument();
    window.history.replaceState(null, "", "/");
  });

  it.each([true, false, undefined])("marks recent failures only when unresolved is %s", unresolved => {
    const failed = { ...project.recent.failed[0], unresolved };
    const { rerender } = render(<ProjectCard project={{ ...project, needs_you: [],
      recent: { done: project.recent.done, failed: [failed] } }} now={0} />);
    if (unresolved) {
      const tag = screen.getByText("unresolved");
      expect(tag).toHaveClass("row-tag");
      expect(tag.previousElementSibling).toBe(screen.getByRole("link", { name: failed.title! }));
    } else {
      expect(screen.queryByText("unresolved")).toBeNull();
    }
    rerender(<Recent board={{ ...board, recent: [failed, ...project.recent.done] }} open onToggle={() => {}} />);
    expect(screen.queryAllByText("unresolved")).toHaveLength(unresolved ? 1 : 0);
    if (unresolved) {
      expect(screen.getByText("unresolved")).toHaveClass("row-tag");
      expect(screen.getByText("unresolved").parentElement).toHaveClass("row-title");
    }
  });

  const inbox = { ...board.lead_inbox[0].items[0], role_id: "fleetglint-lead", age_s: 3840 };
  it.each([true, false])("shows an inbox-only overview card with execution observable = %s", execution => {
    const onlyInbox = { ...project, needs_you: [], needs_you_total: 0, in_progress: [],
      decisions: [], recent: { done: [], failed: [] }, lead_inbox: [{ ...inbox, detail: null, title: "Review proposal" }], lead_inbox_open: 1 };
    const acked = { ...inbox, state: "acked", display_state: "acked" as const, title: "Already acknowledged", detail: "Already acknowledged" };
    const { container } = render(<Overview board={{ ...board, projects: [onlyInbox],
      capabilities: { ...board.capabilities, execution },
      lead_inbox: [{ ...board.lead_inbox[0], items: [inbox, acked] }] }} />);
    const card = within(container.querySelector(".project-card")!);
    expect(card.getByText("Review proposal")).toBeInTheDocument();
    expect(card.getByText("fleetglint-lead · 1h 4m ago")).toBeInTheDocument();
    expect(card.queryByText("Already acknowledged")).toBeNull();
  });
  it("caps open lead inbox items at five and links the remaining count", () => {
    const items = Array.from({ length: 7 }, (_, i) => ({ ...inbox,
      ref: { ...inbox.ref, id: `lead-${i}` }, detail: `Lead message ${i}`, role_id: `lead-${i}` }));
    render(<ProjectCard project={{ ...project, needs_you: [], in_progress: [], decisions: [],
      recent: { done: [], failed: [] }, lead_inbox: items, lead_inbox_open: 7 }} now={0} />);
    for (let i = 0; i < 5; i++) {
      expect(screen.getByText(`Lead message ${i}`)).toBeInTheDocument();
      expect(screen.getByText(`lead-${i} · 1h 4m ago`)).toBeInTheDocument();
    }
    expect(screen.queryByText("Lead message 5")).toBeNull();
    expect(screen.queryByText("Lead message 6")).toBeNull();
    expect(screen.getByRole("link", { name: "2 more on the project page" })).toHaveAttribute("href", "/project?name=fleetglint");
  });
  it("omits the lead inbox section when the project has no open items", () => {
    render(<ProjectCard project={{ ...project, lead_inbox: [], lead_inbox_open: 0 }} now={0} />);
    expect(screen.queryByRole("heading", { name: "Lead inbox" })).toBeNull();
  });
  it("shows the inbox ask, recipient and waiting duration with a zoned tooltip", () => {
    render(<ProjectCard project={{ ...project, needs_you: [inbox] }} now={0} />);
    expect(screen.getByText(inbox.detail!)).toBeTruthy();
    expect(screen.getByText(/→ fleetglint-lead/)).toHaveClass("quiet");
    expect(screen.getByText("waiting 1h 4m")).toHaveAttribute("title", formatAbsolute(inbox.created_at));
  });
  it("omits null metadata parts independently", () => {
    const row = { ...inbox, role_id: null, age_s: null } as unknown as BoardInboxItem;
    const { rerender } = render(<ProjectCard project={{ ...project, needs_you: [row] }} now={0} />);
    expect(screen.queryByText(/→|waiting \d/)).toBeNull();
    rerender(<ProjectCard project={{ ...project, needs_you: [{ ...row, age_s: 0 }] }} now={0} />);
    expect(screen.getByText("waiting 0s")).toBeTruthy();
    expect(screen.queryByText(/→|· waiting/)).toBeNull();
    rerender(<ProjectCard project={{ ...project, needs_you: [{ ...inbox, age_s: null }] }} now={0} />);
    expect(screen.getByText("→ fleetglint-lead")).toBeTruthy();
    expect(screen.queryByText(/waiting \d/)).toBeNull();
  });
  it("does not label run or job started ages as waiting", () => {
    render(<ProjectCard project={{ ...project, needs_you: [
      { ...project.in_progress[0], started_age_s: 3840 },
      { ...project.in_progress[0].jobs![0], started_age_s: 3840 },
    ] }} now={0} />);
    expect(screen.queryByText(/waiting \d|→/)).toBeNull();
  });
  it.each(["new", "changed"] as const)("renders a %s pill before the title", marker => {
    render(<ProjectCard project={{ ...project, needs_you: [inbox] }} now={0} mark={() => marker} />);
    const pill = screen.getByText(marker);
    expect(pill).toHaveClass("seen-marker");
    expect(pill.nextElementSibling).toBe(screen.getByRole("link", { name: inbox.title ?? inbox.ref.id }));
  });
  it("caps needs-you items at five and links to the remaining total", () => {
    render(<ProjectCard project={sevenNeedsProject} now={0} />);
    expect(screen.getAllByRole("link", { name: /^Needs item / })).toHaveLength(5);
    expect(screen.queryByRole("link", { name: "Needs item 6" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Needs item 7" })).toBeNull();
    expect(screen.getByRole("link", { name: "2 more on the project page" })).toHaveAttribute("href", "/project?name=fleetglint");
  });
  it("shows all seven needs-you items on full cards without a more link", () => {
    render(<ProjectCard project={sevenNeedsProject} now={0} full />);
    expect(screen.getAllByRole("link", { name: /^Needs item / })).toHaveLength(7);
    expect(screen.queryByRole("link", { name: /on the project page/i })).toBeNull();
  });
  it("shows all three needs-you items without a more link", () => {
    render(<ProjectCard project={{ ...sevenNeedsProject, needs_you: sevenNeedsProject.needs_you.slice(0, 3), needs_you_total: 3 }} now={0} />);
    expect(screen.getAllByRole("link", { name: /^Needs item / })).toHaveLength(3);
    expect(screen.queryByRole("link", { name: /on the project page/i })).toBeNull();
  });
  it("uses a failed seventh needs-you item for the card band", () => {
    const needs_you = sevenNeedsProject.needs_you.map((item, i) => i === 6 ? { ...item, display_state: "failed" as const } : item);
    const { container } = render(<ProjectCard project={{ ...sevenNeedsProject, needs_you }} now={0} />);
    expect(screen.queryByRole("link", { name: "Needs item 7" })).toBeNull();
    expect(container.querySelector("article")).toHaveAttribute("data-band", "failed");
  });
  it("orders global last and nests jobs", () => {
    const { container } = render(<Overview board={board} />);
    const cards = container.querySelectorAll(".project-card");
    expect(cards).toHaveLength(3);
    expect(cards[2].textContent).toContain("Global");
    const run = cards[0].querySelector('[data-record-id="run-901"]')!;
    expect(within(run as HTMLElement).getByRole("link", { name: "job-317" })).toBeTruthy();
    expect(screen.getByText("Ship the board").closest("a")?.href).toContain("github.com");
    expect(screen.getByText("Keep it read-only").closest("a")).toBeNull();
  });
  it("uses the worst state and links to more", () => {
    const base = { ...project, needs_you: [], in_progress: [], recent: { done: [], failed: [] } };
    const { container, rerender } = render(<ProjectCard project={project} now={Date.parse(board.generated_at)} />);
    const check = (value: string) => expect(container.querySelector("article")?.getAttribute("data-band")).toBe(value);
    check("failed");
    rerender(<ProjectCard project={{ ...base, in_progress: project.in_progress }} now={0} />); check("running");
    rerender(<ProjectCard project={{ ...base, in_progress: [{ ...project.in_progress[0], display_state: "queued" }] }} now={0} />); check("waiting");
    rerender(<ProjectCard project={{ ...base, recent: project.recent }} now={0} />); check("done");
    rerender(<ProjectCard project={{ ...project, truncated: { ...project.truncated, needs_you: true } }} now={0} />);
    expect(screen.getByText(/more on the project page/i).closest("a")?.getAttribute("href")).toBe("/project?name=fleetglint");
  });
  it("shows states for in-progress runs and nested jobs", () => {
    const run = project.in_progress[0];
    const waiting = { ...run, ref: { ...run.ref, id: "waiting-run" }, display_state: "waiting" as const };
    const { container } = render(<ProjectCard project={{ ...project, in_progress: [run, waiting] }} now={0} />);
    expect(container.querySelector('[data-record-id="' + run.ref.id + '"] > .state-badge')).toHaveTextContent("running");
    expect(container.querySelector('[data-record-id="waiting-run"] > .state-badge')).toHaveTextContent("waiting");
    expect(container.querySelector('.project-job > .state-badge')).toHaveTextContent(run.jobs![0].display_state);
  });
  it("filters project pages and handles missing projects", () => {
    expect(parseRoute({ pathname: "/project", search: "?name=fleetglint" })).toEqual({ kind: "project", name: "fleetglint" });
    const { rerender } = render(<Project board={board} name="fleetglint" />);
    expect(screen.getByText("Review request sent to oracle.")).toBeTruthy();
    expect(screen.queryByText("Cover draft is ready for a look.")).toBeNull();
    expect(screen.getByText("Fleetglint lead session")).toBeTruthy();
    expect(screen.queryByText("Cover drawing session")).toBeNull();
    rerender(<Project board={board} name={null} />); expect(screen.getByText("Global")).toBeTruthy();
    rerender(<Project board={board} name="missing" />); expect(screen.getByText("No activity for missing in the window")).toBeTruthy();
  });
  it("uses distinct record IDs for untitled jobs and keeps their commands visible", () => {
    const job = project.in_progress[0].jobs![0];
    const jobs = ["same-command-1", "same-command-2"].map(id => ({
      ...job, ref: { ...job.ref, id }, title: null, command_summary: "pnpm test --run",
    }));
    const base = { ...project, needs_you: jobs, in_progress: [], recent: { done: [], failed: [] } };
    const { rerender } = render(<ProjectCard project={base} now={0} />);
    for (const id of ["same-command-1", "same-command-2"]) {
      expect(screen.getByRole("link", { name: id })).toBeTruthy();
    }
    expect(screen.getAllByText("· pnpm test --run")).toHaveLength(2);
    rerender(<ProjectCard project={{ ...base, needs_you: [], recent: { done: jobs, failed: [] } }} now={0} />);
    for (const id of ["same-command-1", "same-command-2"]) {
      expect(screen.getByRole("link", { name: id })).toBeTruthy();
    }
    expect(screen.getAllByText("· pnpm test --run")).toHaveLength(2);
  });
  it("shows all seven project inbox items even when the role list is capped at five", () => {
    const role = board.lead_inbox[0];
    const items = Array.from({ length: 7 }, (_, i) => ({
      ...role.items[0], project: "alpha", detail: `Alpha message ${i}`, ref: { ...role.items[0].ref, id: `alpha-${i}` },
    }));
    const pageBoard = { ...board, projects: [{ ...project, project: "alpha", lead_inbox: items, lead_inbox_open: 7 }], lead_inbox: [{
      ...role, open: 7, old: 4, action_required: 1, items: items.slice(0, 5),
      by_project: [{ project: "alpha", open: 7, old: 4, action_required: 1 }],
    }] };
    const { container } = render(<Project board={pageBoard} name="alpha" />);
    expect(screen.getByRole("region", { name: "Lead inbox" })).toHaveTextContent("7 open · 4 waiting");
    expect(container.querySelectorAll(".inbox-line")).toHaveLength(7);
    items.forEach(item => expect(screen.getByText(item.detail)).toBeInTheDocument());
  });
  it("shows project messages displaced by newer messages from another project and reports the cap", () => {
    const role = board.lead_inbox[0];
    const items = Array.from({ length: 2 }, (_, i) => ({ ...role.items[0], project: "alpha",
      detail: `Alpha displaced ${i}`, ref: { ...role.items[0].ref, id: `alpha-${i}` } }));
    const other = Array.from({ length: 5 }, (_, i) => ({ ...role.items[0], project: "beta",
      detail: `Beta newer ${i}`, ref: { ...role.items[0].ref, id: `beta-${i}` } }));
    const pageBoard = { ...board, projects: [{ ...project, project: "alpha", lead_inbox: items, lead_inbox_open: 3 }], lead_inbox: [{
      ...role, open: 8, items: other, by_project: [{ project: "alpha", open: 3, old: 0, action_required: 0 },
        { project: "beta", open: 5, old: 0, action_required: 0 }],
    }] };
    render(<Project board={pageBoard} name="alpha" />);
    items.forEach(item => expect(screen.getByText(item.detail)).toBeInTheDocument());
    expect(screen.queryByText("Beta newer 0")).toBeNull();
    expect(screen.getByText("1 lead inbox message not shown.")).toBeInTheDocument();
  });
  it("shows a quiet repeat count after the title only for repeated work", () => {
    const job = project.in_progress[0].jobs![0];
    const base = { ...project, needs_you: [{ ...job, repeat_count: 3 }], in_progress: [], recent: { done: [], failed: [] } };
    const { rerender } = render(<ProjectCard project={base} now={0} />);
    const count = screen.getByText("×3");
    expect(count).toHaveClass("quiet");
    expect(count.previousElementSibling).toHaveAttribute("href", screen.getByRole("link", { name: job.ref.id }).getAttribute("href"));
    rerender(<ProjectCard project={{ ...base, needs_you: [job] }} now={0} />);
    expect(screen.queryByText(/×\d+/)).toBeNull();
    rerender(<ProjectCard project={{ ...base, needs_you: [{ ...job, repeat_count: 1 }] }} now={0} />);
    expect(screen.queryByText(/×\d+/)).toBeNull();
  });
  it("omits roles without a matching project even for prototype names", () => {
    const pageBoard = { ...board, projects: [{ ...project, project: "constructor" }] };
    const { container } = render(<Project board={pageBoard} name="constructor" />);
    expect(container.querySelector(".group-count")).toBeNull();
  });
  it("omits more links on full cards even when all sections are truncated", () => {
    const truncated = { needs_you: true, in_progress: true, decisions: true, recent: { done: true, failed: true } };
    render(<ProjectCard project={{ ...project, truncated }} now={0} full />);
    expect(screen.queryByRole("link", { name: /on the project page/i })).toBeNull();
  });
});

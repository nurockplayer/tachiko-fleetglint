import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { board } from "./fixtures/board";
import { Overview } from "./screens/Overview";
import { Project } from "./screens/Project";
import { ProjectCard } from "./components/ProjectCard";
import { parseRoute } from "./router";

const project = board.projects[1];
describe("project board", () => {
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
  it("uses backend project inbox totals with only five returned items", () => {
    const role = board.lead_inbox[0];
    const items = Array.from({ length: 5 }, (_, i) => ({
      ...role.items[0], project: "alpha", ref: { ...role.items[0].ref, id: `alpha-${i}` },
    }));
    const pageBoard = { ...board, projects: [{ ...project, project: "alpha" }], lead_inbox: [{
      ...role, open: 10, old: 6, action_required: 2, items,
      by_project: { alpha: { open: 8, old: 4, action_required: 1 }, beta: { open: 2, old: 2, action_required: 1 } },
    }] };
    const { container, rerender } = render(<Project board={pageBoard} name="alpha" />);
    expect(screen.getByRole("button", { name: /Lead inbox/ })).toHaveTextContent("8 open · 4 waiting");
    expect(container.querySelector(".group-count")).toHaveTextContent("8");
    expect(container.querySelectorAll(".inbox-line")).toHaveLength(5);
    rerender(<Project board={{ ...pageBoard, lead_inbox: [{ ...pageBoard.lead_inbox[0], items: [] }] }} name="alpha" />);
    expect(screen.getByRole("button", { name: /Lead inbox/ })).toHaveTextContent("8 open");
    expect(container.querySelector(".group-count")).toHaveTextContent("8");
  });
  it("omits more links on full cards even when all sections are truncated", () => {
    const truncated = { needs_you: true, in_progress: true, decisions: true, recent: { done: true, failed: true } };
    render(<ProjectCard project={{ ...project, truncated }} now={0} full />);
    expect(screen.queryByRole("link", { name: /on the project page/i })).toBeNull();
  });
});

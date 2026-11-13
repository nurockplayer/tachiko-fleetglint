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
    expect(within(run as HTMLElement).getByText(/pnpm test --run/)).toBeTruthy();
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
});

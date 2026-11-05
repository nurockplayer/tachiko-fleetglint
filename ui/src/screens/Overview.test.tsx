import { render, screen, within } from "@testing-library/react";
import { Overview } from "./Overview";
import { snapshot, snapshotEmpty } from "../test-fixtures";

describe("Overview", () => {
  it("renders the empty state when there are no sources and no records", () => {
    render(<Overview snapshot={snapshotEmpty} />);
    expect(screen.getByText("No sources yet")).toBeInTheDocument();
    expect(screen.getByText(/Claude Code transcripts/)).toBeInTheDocument();
    expect(screen.getByText(/Codex rollouts/)).toBeInTheDocument();
    expect(screen.getByText(/tachiko-harness state/)).toBeInTheDocument();
    expect(screen.getByText(/NDJSON root/)).toBeInTheDocument();
    expect(screen.getByText("fleetglint doctor")).toBeInTheDocument();
    expect(screen.getByText("fleetglint demo")).toBeInTheDocument();
    expect(screen.getByText(/fleetglint emit <<'EOF'/)).toBeInTheDocument();
  });

  it("lists sessions with a neutral explanation and activity ages", () => {
    render(<Overview snapshot={snapshot} />);
    const sessions = screen.getByLabelText("Sessions");
    expect(
      within(sessions).getByText(
        "found in local history; activity, not proof of execution",
      ),
    ).toBeInTheDocument();
    const activities = Array.from(sessions.querySelectorAll(".session-activity")).map(
      (node) => node.textContent,
    );
    expect(activities[0]).toMatch(/^recent \d/);
    expect(activities[1]).toMatch(/^idle \d/);
    expect(activities[2]).toBe("ended");
    expect(within(sessions).getAllByText(/claude-opus-5-5/).length).toBeGreaterThan(0);
  });

  it("shows the waits-on reference for a waiting run", () => {
    render(<Overview snapshot={snapshot} />);
    expect(
      screen.getByText(/waits on → github_pr · nurockplayer\/eddington-1919#176/),
    ).toBeInTheDocument();
  });

  it("says a cut list is not the whole list", () => {
    const cut = structuredClone(snapshot);
    cut.truncated.runs = true;
    cut.truncated.sessions = true;
    render(<Overview snapshot={cut} />);

    const runs = screen.getByLabelText("Runs");
    expect(
      within(runs).getByText(/showing the newest 10 runs; more exist/),
    ).toBeInTheDocument();
    expect(within(runs).queryByText(/\d+ active/)).toBeNull();

    const sessions = screen.getByLabelText("Sessions");
    expect(
      within(sessions).getByText(/showing the newest 3 sessions; more exist/),
    ).toBeInTheDocument();
  });

  it("uses singular nouns for a single run and job", () => {
    const one = structuredClone(snapshot);
    one.runs = one.runs.filter((run) => run.display_state === "running");
    one.jobs = one.jobs.slice(0, 1);
    const { container } = render(<Overview snapshot={one} />);
    expect(screen.getByText(/1 run · 1 job · read-only/)).toBeInTheDocument();
    const heads = Array.from(
      container.querySelectorAll(".row-group-head .count"),
    ).map((node) => node.textContent);
    expect(heads).toEqual(["1 run"]);
  });

  it("says how many attention items are shown when the count exceeds the list", () => {
    const cut = structuredClone(snapshot);
    cut.counts.attention = 9;
    render(<Overview snapshot={cut} />);
    expect(screen.getByText(`Showing ${cut.attention.length} of 9`)).toBeInTheDocument();
  });

  it("groups non-terminal runs by project and keeps terminal runs collapsed", () => {
    const { container } = render(<Overview snapshot={snapshot} />);
    const groups = Array.from(container.querySelectorAll(".row-group-head strong")).map(
      (node) => node.textContent,
    );
    expect(groups).toEqual(["eddington-1919", "tachiko-harness", "fleetglint"]);
    const terminal = container.querySelector("details.terminal-runs");
    expect(terminal).toBeTruthy();
    expect(terminal?.hasAttribute("open")).toBe(false);
  });
});

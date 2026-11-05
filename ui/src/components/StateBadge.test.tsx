import { render, screen } from "@testing-library/react";
import { StateBadge, StateTransition } from "./StateBadge";
import type { BadgeState } from "../states";

const CASES: Array<[BadgeState, string, string]> = [
  ["queued", "queued", "ring"],
  ["running", "running", "dot"],
  ["waiting", "waiting", "arrow"],
  ["done", "done", "check"],
  ["failed", "failed", "cross"],
  ["cancelled", "cancelled", "slash"],
  ["stale", "stale", "dashed-ring"],
  ["lost", "lost", "broken-link"],
  ["unknown", "unknown", "question"],
  ["attention", "action", "bang"],
  ["open", "open", "open-dot"],
  ["acked", "acked", "acked-dot"],
  ["recent", "recent", "clock"],
  ["idle", "idle", "crescent"],
  ["ended", "ended", "square"],
];

describe("StateBadge", () => {
  it.each(CASES)("renders %s with its label and glyph", (state, label, glyph) => {
    const { container } = render(<StateBadge state={state} />);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(container.querySelector(`[data-glyph="${glyph}"]`)).toBeTruthy();
  });

  it("shows the age suffix on a stale badge", () => {
    render(<StateBadge state="stale" age="42m" />);
    expect(screen.getByText("stale")).toBeInTheDocument();
    expect(screen.getByText("42m")).toBeInTheDocument();
  });
});

describe("StateTransition", () => {
  it("shows both the writer state and the stale display state", () => {
    render(<StateTransition writerState="running" displayState="stale" age="42m" />);
    expect(screen.getByText("running")).toBeInTheDocument();
    expect(screen.getByText("stale")).toBeInTheDocument();
    expect(screen.getByText("42m")).toBeInTheDocument();
    expect(screen.getByText("→")).toBeInTheDocument();
  });

  it("shows one badge when the writer state is the display state", () => {
    render(<StateTransition writerState="done" displayState="done" />);
    expect(screen.getByText("done")).toBeInTheDocument();
    expect(screen.queryByText("→")).toBeNull();
  });
});

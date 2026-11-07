import { render, screen } from "@testing-library/react";
import { StateBadge } from "./StateBadge";
import type { BadgeState } from "../states";

const CASES: Array<[BadgeState, string, string]> = [
  ["queued", "queued", "ring"],
  ["running", "running", "dot"],
  ["waiting", "waiting", "hourglass"],
  ["done", "done", "check"],
  ["failed", "failed", "cross"],
  ["cancelled", "cancelled", "slash"],
  ["stale", "out of date", "dashed-circle"],
  ["lost", "process gone", "broken-link"],
  ["unknown", "unverified", "question"],
  ["open", "notified", "open-dot"],
  ["acked", "seen", "acked-dot"],
  ["needs", "notified", "bang"],
  ["recent", "recent", "clock"],
  ["idle", "idle", "crescent"],
  ["ended", "ended", "square"],
];

describe("StateBadge", () => {
  it.each(CASES)("renders %s with its words and glyph", (state, label, glyph) => {
    const { container } = render(<StateBadge state={state} />);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(container.querySelector(`[data-glyph="${glyph}"]`)).toBeTruthy();
  });

  it("never prints a raw state name that the vocabulary replaced", () => {
    const { container } = render(
      <>
        <StateBadge state="lost" />
        <StateBadge state="stale" />
        <StateBadge state="unknown" />
      </>,
    );
    expect(container.textContent).not.toMatch(/\blost\b|\bstale\b|\bunknown\b/);
  });

  it("shows the age suffix beside the words", () => {
    render(<StateBadge state="stale" age="42m" />);
    expect(screen.getByText("out of date")).toBeInTheDocument();
    expect(screen.getByText("42m")).toBeInTheDocument();
  });

  it("keeps the words in the accessible name of the glyph-only variant", () => {
    const { container } = render(<StateBadge state="lost" variant="glyph" />);
    const glyph = screen.getByRole("img", { name: "process gone" });
    expect(glyph).toHaveAttribute("data-glyph", "broken-link");
    expect(container.textContent).toBe("");
  });
});

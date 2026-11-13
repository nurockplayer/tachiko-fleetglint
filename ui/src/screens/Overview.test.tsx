import { render, screen, within } from "@testing-library/react";
import { Overview } from "./Overview";
import { board, boardEmpty, boardSessions } from "../test-fixtures";

function summary(): HTMLElement {
  const node = document.querySelector(".summary-line");
  if (!(node instanceof HTMLElement)) throw new Error("no summary line");
  return node;
}

function groupHeadings(selector: string): string[] {
  return Array.from(
    document.querySelectorAll<HTMLElement>(`${selector} .group-heading`),
  ).map((node) =>
    Array.from(node.childNodes)
      .filter(
        (child) =>
          !(child instanceof Element && child.classList.contains("state-badge")),
      )
      .map((child) => child.textContent?.trim() ?? "")
      .filter(Boolean)
      .join(" "),
  );
}

describe("Overview", () => {
  it("renders the empty state when the store has no sources", () => {
    render(<Overview board={boardEmpty} />);
    expect(screen.getByText("No sources yet")).toBeInTheDocument();
    expect(screen.getByText(/Claude Code transcripts/)).toBeInTheDocument();
    expect(screen.getByText(/Codex rollouts/)).toBeInTheDocument();
    expect(screen.getByText(/tachiko-harness state/)).toBeInTheDocument();
    expect(screen.getByText(/NDJSON root/)).toBeInTheDocument();
    expect(screen.getByText("fleetglint doctor")).toBeInTheDocument();
    expect(screen.getByText("fleetglint demo")).toBeInTheDocument();
    expect(screen.getByText(/fleetglint emit <<'EOF'/)).toBeInTheDocument();
  });

  it("renders one summary line whose counts link to their sections", () => {
    render(<Overview board={board} />);
    expect(summary()).toHaveTextContent(
      "2 notified · 3 waiting · 4 running · 2 queued · 3 lead inbox · 3 exceptions",
    );
    expect(within(summary()).getByRole("link", { name: "2 notified" })).toHaveAttribute(
      "href",
      "#notified",
    );
    expect(within(summary()).getByRole("link", { name: "3 waiting" })).toHaveAttribute(
      "href",
      "#waiting",
    );
    expect(within(summary()).getByRole("link", { name: "4 running" })).toHaveAttribute(
      "href",
      "#running",
    );
    expect(within(summary()).getByRole("link", { name: "2 queued" })).toHaveAttribute(
      "href",
      "#queued",
    );
    expect(within(summary()).getByRole("link", { name: "3 lead inbox" })).toHaveAttribute(
      "href",
      "#lead-inbox",
    );
    expect(within(summary()).getByRole("link", { name: "3 exceptions" })).toHaveAttribute(
      "href",
      "#exceptions",
    );
  });

  it("gives session rows no link, because a session has no detail page", () => {
    render(<Overview board={boardSessions} />);
    const rows = document.querySelectorAll(".session-row");
    expect(rows.length).toBeGreaterThan(0);
    rows.forEach((row) => expect(row.tagName).toBe("DIV"));
  });

  it("keeps the lead inbox when requests are observable but execution is not", () => {
    render(
      <Overview
        board={{
          ...boardSessions,
          capabilities: { execution: false, requests: true },
          counts: { ...boardSessions.counts, lead_inbox_open: board.counts.lead_inbox_open },
          lead_inbox: board.lead_inbox,
        }}
      />,
    );
    expect(summary()).toHaveTextContent(`${board.counts.lead_inbox_open} lead inbox`);
    expect(screen.getByLabelText("Lead inbox")).toBeInTheDocument();
  });

  it("says execution is not observable instead of showing zeros", () => {
    render(<Overview board={boardSessions} />);
    expect(summary()).toHaveTextContent(
      "1 notified · waiting: not observable · running: not observable",
    );
    expect(
      screen.getByText(
        "Session history shows recent activity, not whether a process is running. Connect a source with process evidence to see running work.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Waiting 0/)).toBeNull();
    expect(screen.queryByText(/Running 0/)).toBeNull();
    expect(screen.getByRole("heading", { name: "Recent sessions" })).toBeInTheDocument();
    expect(groupHeadings("#sessions")).toEqual([
      "Recent sessions 1",
      "Idle 1",
      "Ended 1",
    ]);
  });

  it("never uses the old vocabulary or a bare dash", () => {
    const { container } = render(<Overview board={board} />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/Needs attention/);
    expect(text).not.toMatch(/lead-wait/);
    expect(text).not.toMatch(/\blost\b/);
    expect(text).not.toMatch(/\bstale\b/);
    expect(text).not.toMatch(/\bunknown\b/);
    expect(text).not.toContain("—");
  });
});

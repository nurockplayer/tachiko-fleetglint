import { fireEvent, render, screen, within } from "@testing-library/react";
import { Overview } from "./Overview";
import { board, boardEmpty, boardRealShapes, boardSessions } from "../test-fixtures";

function summary(): HTMLElement {
  const node = document.querySelector(".summary-line");
  if (!(node instanceof HTMLElement)) throw new Error("no summary line");
  return node;
}

function ids(selector: string): string[] {
  return Array.from(document.querySelectorAll<HTMLElement>(selector)).map(
    (node) => node.dataset.recordId ?? "",
  );
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

  it("keeps the spec §5 order from top to bottom", () => {
    render(<Overview board={board} />);
    const headings = screen
      .getAllByRole("heading", { level: 2 })
      .map((node) => node.textContent?.replace(/\s+/g, " ").trim());
    expect(headings).toEqual([
      "You were notified",
      "Waiting 3",
      "Running 4",
      "Lead inbox",
      "3 exceptions",
      "Recent",
      "Sessions 8",
    ]);
  });

  it("lists what the viewer was notified about, with sender, key and age", () => {
    render(<Overview board={board} />);
    const items = document.querySelectorAll(".notified-item");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Should the board call the retry an exception?");
    expect(items[0]).toHaveTextContent("some-lead · some-key · 30m ago");
    expect(items[1]).toHaveTextContent("Review finished: two blockers fixed in PR #43.");
    expect(items[1]).toHaveTextContent("1h ago");
  });

  it("shows waiting work longest first, with what each row waits on", () => {
    render(<Overview board={board} />);
    expect(within(screen.getByLabelText("Waiting")).getByText("Waiting 3")).toBeInTheDocument();
    expect(ids("#waiting .work-row")).toEqual(["review-pr-43", "run-909", "run-910"]);
    expect(screen.getByText("PR #43 review")).toBeInTheDocument();
    expect(screen.getByText("waits on review")).toBeInTheDocument();
    expect(screen.getByText("waits on job job-317")).toBeInTheDocument();
    expect(screen.getByText("waits on FG-1180")).toBeInTheDocument();
    expect(screen.getByText("2h 30m")).toBeInTheDocument();
    expect(screen.getByText("2h")).toBeInTheDocument();
    expect(screen.getByText("40m")).toBeInTheDocument();
  });

  it("groups running work by project, in first-seen order, with the freshest check time", () => {
    render(<Overview board={board} />);
    const running = screen.getByLabelText("Running");
    expect(within(running).getByText("process checks 3s ago")).toBeInTheDocument();
    expect(groupHeadings("#running .running-group:not(.queued-group)")).toEqual([
      "fleetglint 3",
      "edd 1",
    ]);
    expect(screen.getByText("pnpm test --run")).toBeInTheDocument();
    expect(screen.getByText(/checked 2m ago/)).toBeInTheDocument();
    expect(within(running).getByText("worker")).toBeInTheDocument();
    expect(within(running).getByText("role")).toBeInTheDocument();
    expect(within(running).getByText("model")).toBeInTheDocument();
    expect(within(running).getByText("running")).toBeInTheDocument();
  });

  it("titles two jobs with one command by their ids, never the command", () => {
    render(<Overview board={boardRealShapes} />);
    const first = document.querySelector('.running-row[data-record-id="job-701"]');
    const second = document.querySelector('.running-row[data-record-id="job-702"]');
    expect(first?.querySelector(".row-title")?.textContent).toBe("job-701");
    expect(second?.querySelector(".row-title")?.textContent).toBe("job-702");
    expect(first?.querySelector(".row-model-command")?.textContent).toBe(
      "orb-test --heavy --host",
    );
    expect(second?.querySelector(".row-model-command")?.textContent).toBe(
      "orb-test --heavy --host",
    );
  });

  it("says what a wait row waits on and never a bare waiting word", () => {
    render(<Overview board={boardRealShapes} />);
    for (const row of Array.from(document.querySelectorAll(".work-row"))) {
      expect(row.textContent ?? "").not.toMatch(/\bwaiting\b/i);
    }
    expect(screen.getByText("waits on review")).toBeInTheDocument();
    expect(screen.getByText("waits on worker")).toBeInTheDocument();
    expect(screen.getByText("waits on zsh /private/tmp/x/y.sh")).toBeInTheDocument();

    const quiet = document.querySelector('.waiting-row[data-record-id="wait-t220"]');
    expect(quiet).toHaveClass("is-single-line");
    expect(quiet?.querySelector(".row-what")).toBeNull();
    expect(quiet?.querySelector(".row-title")?.textContent).toBe("t220");
  });

  it("shows a notification's sender and key, never owner or a from: prefix", () => {
    render(<Overview board={boardRealShapes} />);
    const items = Array.from(document.querySelectorAll(".notified-item"));
    for (const item of items) {
      expect(item.textContent ?? "").not.toMatch(/\bowner\b/);
      expect(item.textContent ?? "").not.toContain("from:");
    }
    expect(items[0]).toHaveTextContent("some-lead · some-key · 30m ago");
    expect(items[1]).toHaveTextContent("delivery failed");
  });

  it("adds a small Queued group at the end only when something is queued", () => {
    const { rerender } = render(<Overview board={board} />);
    expect(within(screen.getByLabelText("Running")).getByText("Queued 2")).toBeInTheDocument();
    expect(ids("#queued .work-row")).toEqual(["job-401", "run-904"]);
    expect(screen.getByText("pnpm build")).toBeInTheDocument();

    const none = structuredClone(board);
    none.queued = [];
    none.counts.queued = 0;
    rerender(<Overview board={none} />);
    expect(screen.queryByText(/^Queued \d/)).toBeNull();
    expect(summary()).not.toHaveTextContent("queued");
  });

  it("opens the lead inbox with per-role counts and marks items over the threshold", () => {
    render(<Overview board={board} />);
    const inbox = screen.getByLabelText("Lead inbox");
    const toggle = within(inbox).getByRole("button");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(inbox.querySelector(".section-summary")?.textContent).toBe(
      "3 open · 1 waiting over 4 h",
    );
    expect(inbox.querySelector(".role-counts")?.textContent?.replace(/\s+/g, " ").trim()).toBe(
      "fleetglint-lead 2 · edd-art 1",
    );

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const old = Array.from(document.querySelectorAll(".inbox-line")).find((line) =>
      line.textContent?.includes("One worker is waiting on a decision."),
    );
    expect(old).toBeTruthy();
    expect(old).toHaveClass("is-old");
    expect(old).toHaveTextContent("over 4 h");
    expect(screen.getByText("Cover draft is ready for a look.")).toBeInTheDocument();
  });

  it("keeps an opened section open across a refresh", () => {
    const { rerender } = render(<Overview board={board} />);
    const inbox = screen.getByLabelText("Lead inbox");
    fireEvent.click(within(inbox).getByRole("button"));
    expect(document.querySelector("#lead-inbox-body")).toBeTruthy();

    rerender(<Overview board={structuredClone(board)} />);
    expect(
      within(screen.getByLabelText("Lead inbox")).getByRole("button"),
    ).toHaveAttribute("aria-expanded", "true");
    expect(document.querySelector("#lead-inbox-body")).toBeTruthy();
  });

  it("keeps the project order stable when a refresh adds a project", () => {
    const { rerender } = render(<Overview board={board} />);
    expect(groupHeadings("#running .running-group:not(.queued-group)")).toEqual([
      "fleetglint 3",
      "edd 1",
    ]);

    const next = structuredClone(board);
    const extra = structuredClone(board.running[2]);
    extra.ref.id = "run-999";
    extra.project = "alpha";
    next.running = [extra, ...next.running.slice().reverse()];
    rerender(<Overview board={next} />);
    expect(groupHeadings("#running .running-group:not(.queued-group)")).toEqual([
      "fleetglint 3",
      "edd 1",
      "alpha 1",
    ]);
  });

  it("keeps the three exception counts separate and links old unverified records to history", () => {
    render(<Overview board={board} />);
    const exceptions = screen.getByLabelText("Exceptions");
    expect(within(exceptions).getByRole("button")).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(exceptions.querySelector(".section-subline")?.textContent).toContain(
      "1 process gone · 1 out of date · 1 unverified",
    );
    expect(
      within(exceptions).getByRole("link", {
        name: "4 older records unverified, in history",
      }),
    ).toHaveAttribute("href", "/history");

    fireEvent.click(within(exceptions).getByRole("button"));
    expect(groupHeadings("#exceptions")).toEqual([
      "Process gone 1",
      "Out of date 1",
      "Unverified 1",
    ]);
    expect(screen.getByText("job-388")).toBeInTheDocument();
    expect(screen.getByText("Refresh the screenshots")).toBeInTheDocument();
  });

  it("collapses recent work and lists failures first when opened", () => {
    render(<Overview board={board} />);
    const recent = screen.getByLabelText("Recent");
    expect(recent.querySelector(".section-summary")?.textContent).toBe("2 failed · 1 done");
    fireEvent.click(within(recent).getByRole("button"));
    expect(groupHeadings("#recent")).toEqual(["Failed 2", "Done 1", "Cancelled 1"]);
  });

  it("collapses sessions and shows activity ages without counting them as execution", () => {
    render(<Overview board={board} />);
    const sessions = screen.getByLabelText("Sessions");
    expect(within(sessions).getByText("Sessions 8")).toBeInTheDocument();
    fireEvent.click(within(sessions).getByRole("button"));
    expect(groupHeadings("#sessions")).toEqual([
      "Recent sessions 1",
      "Idle 1",
      "Ended 1",
    ]);
    expect(screen.getByText("last activity 2m ago")).toBeInTheDocument();
    expect(screen.queryByText(/Session history shows recent activity/)).toBeNull();
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

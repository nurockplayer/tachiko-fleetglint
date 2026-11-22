import { fireEvent, render, screen } from "@testing-library/react";
import { App } from "../App";
import { Plans } from "./Plans";
import type { PlanResult } from "../api/plans";
import { jsonResponse, routeFetcher } from "../test-fetcher";
import { formatAbsolute } from "../format";
import { board } from "../test-fixtures";

const plan: PlanResult = {
  path: "/repo/plan.yaml", state: "ok", project: "Example", plan_state: "ACTIVE",
  checked_at: "2026-11-22T05:00:00+09:00", file_modified_at: "2026-11-21T04:00:00+09:00",
  refreshing: false, counts: { total: 2, PASS: 1, STALE: 1 }, text_available: true,
  workstreams: [{ id: "W", title: "Deliverable", outcome: "Owner can read plans", lead: "Lead",
    phases: [{ id: "build", title: "Build" }, { id: "accept", title: "Accept" }], current_phase: "build",
    next_step: "Ask the judge", criteria: [
      { id: "C", requirement: "Observable invariant", status: "STALE", reason: "Watched files changed",
        changed_files: ["src/main.py"], judge: "Independent judge", verified_at: "2026-11-20 JST", verified_sha: "abc1234",
        evidence: [{ label: "Judgement", url: "https://example.org/evidence" }] },
      { id: "P", requirement: "Passing requirement", status: "PASS", judge: "Owner" },
    ] }],
  owner_decisions: [
    { id: "D", question: "Ship?", options: ["yes", "no"], recommendation: "yes", deadline: "2026-12-01 JST", state: "OPEN" },
    { id: "A", question: "Which scope?", options: ["small", "large"], recommendation: "small", deadline: "2026-11-20 JST", state: "ANSWERED", answer: "small", answer_ref: "https://example.org/answer" },
  ],
};
const fetcherFor = (plans: PlanResult[]) => routeFetcher({
  "/api/plans": () => jsonResponse({ api: 1, refresh_s: 15, plans }),
  "/api/board": () => jsonResponse(board),
});

it("routes /plans and shows the enable hint when disabled", async () => {
  window.history.replaceState(null, "", "/plans");
  render(<App fetcher={fetcherFor([])} />);
  expect(await screen.findByText(/Enable Plans by adding/)).toHaveTextContent('[plans]');
  expect(screen.getByRole("link", { name: "Plans" })).toHaveAttribute("href", "/plans");
  window.history.replaceState(null, "", "/");
});

it("shows summary, decisions, STALE reason and expandable workstream detail", async () => {
  render(<Plans fetcher={fetcherFor([plan])} />);
  expect(await screen.findByRole("heading", { name: /Example.*ACTIVE/ })).toBeInTheDocument();
  expect(screen.getByText("total: 2").parentElement).toHaveTextContent("total: 2");
  expect(screen.getByText(/File modified:/)).toHaveTextContent(formatAbsolute(plan.file_modified_at));
  expect(screen.getByText(/Checked at:/)).toHaveTextContent(formatAbsolute(plan.checked_at));
  expect(screen.getByText("Ship?")).toBeVisible();
  expect(screen.getByText("Options: yes · no")).toBeVisible();
  expect(screen.getByText("Recommendation: yes")).toBeVisible();
  expect(screen.getAllByText("C")[0]).toBeVisible();
  expect(screen.getAllByText("Watched files changed")[0]).toBeVisible();
  expect(screen.getAllByText("Changed files: src/main.py")[0]).toBeVisible();
  const summary = screen.getByText(/Deliverable/);
  expect(summary.closest("details")).not.toHaveAttribute("open");
  fireEvent.click(summary);
  expect(summary.closest("details")).toHaveAttribute("open");
  expect(screen.getByText("Outcome: Owner can read plans")).toBeVisible();
  expect(screen.getByText("Phases: Build (current) → Accept")).toBeVisible();
  expect(screen.getByText("Next step: Ask the judge")).toBeVisible();
  expect(screen.getByText("Judge: Independent judge")).toBeVisible();
  expect(screen.getByText("Verified at: 2026-11-20 JST")).toBeVisible();
  expect(screen.getByText("Verified SHA: abc1234")).toBeVisible();
  expect(screen.getByRole("link", { name: "Judgement" })).toHaveAttribute("href", "https://example.org/evidence");
  fireEvent.click(screen.getByText("Answered Owner decisions"));
  expect(screen.getByRole("link", { name: "Recorded answer" })).toHaveAttribute("href", "https://example.org/answer");
});

it("shows old reports with ids and counts and a newer plan-check note", async () => {
  render(<Plans fetcher={fetcherFor([{ ...plan, text_available: false, workstreams: [{ id: "W", criteria: [{ id: "C", status: "PENDING" }] }], owner_decisions: [] }])} />);
  expect(await screen.findByText("Plan text needs a newer plan-check.")).toBeVisible();
  expect(screen.getAllByText("C")[0]).toBeVisible();
  expect(screen.getByText("total: 2")).toBeVisible();
});

it("shows invalid errors without passing counts", async () => {
  render(<Plans fetcher={fetcherFor([{ path: "/repo", state: "invalid", checked_at: null, file_modified_at: null, refreshing: false, errors: ["bad plan"] }])} />);
  expect(await screen.findByText("bad plan")).toBeVisible();
  expect(screen.queryByText(/PASS:/)).toBeNull();
});

 it("renders plan statuses and inline code without other markdown", async () => {
  const criteria = ["PASS", "FAIL", "BLOCKED", "PENDING", "STALE"].map((status) => ({ id: status + "-id", status, requirement: "Use `/health` and **literal**" }));
  render(<Plans fetcher={fetcherFor([{ ...plan, workstreams: [{ id: "W", title: "Stream", criteria }] }])} />);
  await screen.findByText("Stream");
  const summary = screen.getByText("Stream").closest("summary")!;
  for (const status of ["PASS", "FAIL", "BLOCKED", "PENDING", "STALE"]) {
    expect(summary.querySelector(`[title]`) ?? summary.querySelector('.state-badge')).toBeTruthy();
    expect(summary).toHaveTextContent(status);
  }
  expect(screen.getAllByText("/health")[0].tagName).toBe("CODE");
  expect(screen.getAllByText(/and \*\*literal\*\*/)[0]).toBeVisible();
  expect(screen.getByText("OPEN").closest(".state-badge")).toBeTruthy();
  expect(summary.closest("details")).not.toHaveAttribute("open");
  expect(summary).toHaveTextContent("PASS: 1");
});

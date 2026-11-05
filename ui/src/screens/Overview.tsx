import { useState } from "react";
import type { RunSummary, Snapshot } from "../api/types";
import { isTerminal } from "../states";
import { CountTile, JobRow, RunRow, SessionRow } from "../components/Rows";
import { EmptyState, TruncationNote } from "../components/Panels";

type Grouping = "project" | "role";

function groupRuns(
  runs: RunSummary[],
  grouping: Grouping,
): Array<{ key: string; runs: RunSummary[] }> {
  const groups = new Map<string, RunSummary[]>();
  for (const run of runs) {
    const key =
      grouping === "project" ? (run.project ?? "no project") : (run.role_id ?? "no role");
    const existing = groups.get(key);
    if (existing) existing.push(run);
    else groups.set(key, [run]);
  }
  return Array.from(groups, ([key, grouped]) => ({ key, runs: grouped }));
}

export function Overview({ snapshot }: { snapshot: Snapshot }) {
  const [grouping, setGrouping] = useState<Grouping>("project");

  const isEmpty =
    snapshot.sources.length === 0 &&
    snapshot.runs.length === 0 &&
    snapshot.jobs.length === 0 &&
    snapshot.inbox.length === 0 &&
    snapshot.sessions.length === 0;

  if (isEmpty) {
    return (
      <main className="screen">
        <EmptyState />
      </main>
    );
  }

  const active = snapshot.runs.filter((run) => !isTerminal(run.display_state));
  const terminal = snapshot.runs.filter((run) => isTerminal(run.display_state));
  const groups = groupRuns(active, grouping);
  const projects = new Set(snapshot.runs.map((run) => run.project ?? "no project"));

  return (
    <main className="screen">
      <div className="screen-head">
        <h1>Overview</h1>
        <p className="summary-line">
          {projects.size} projects · {snapshot.runs.length}
          {snapshot.truncated.runs ? "+" : ""} runs · {snapshot.jobs.length}
          {snapshot.truncated.jobs ? "+" : ""} jobs · read-only
        </p>
      </div>

      <div className="tiles">
        <CountTile
          label="Running"
          value={snapshot.counts.running}
          states={["running"]}
          href="/"
        />
        <CountTile
          label="Waiting"
          value={snapshot.counts.waiting}
          states={["waiting"]}
          href="/"
        />
        <CountTile
          label="Needs attention"
          value={snapshot.counts.attention}
          states={["attention"]}
          href="/attention"
        />
        <CountTile
          label="Stale / lost / unknown"
          value={snapshot.counts.stale_lost_unknown}
          states={["stale", "lost", "unknown"]}
          href="/attention"
        />
      </div>

      <section className="section" aria-label="Runs">
        <div className="section-head">
          <h2>Runs</h2>
          {snapshot.truncated.runs ? (
            <TruncationNote truncated shown={snapshot.runs.length} noun="runs" />
          ) : (
            <span className="count">{active.length} active</span>
          )}
          <div className="grouping">
            <span className="label">group by</span>
            <button
              type="button"
              aria-pressed={grouping === "project"}
              onClick={() => setGrouping("project")}
            >
              project
            </button>
            <button
              type="button"
              aria-pressed={grouping === "role"}
              onClick={() => setGrouping("role")}
            >
              role
            </button>
          </div>
        </div>
        {groups.map((group) => (
          <div className="row-group" key={group.key}>
            <div className="row-group-head">
              <strong>{group.key}</strong>
              <span className="count">{group.runs.length} runs</span>
            </div>
            {group.runs.map((run) => (
              <RunRow key={`${run.ref.source_id}/${run.ref.id}`} run={run} />
            ))}
          </div>
        ))}
      </section>

      <section className="section" aria-label="Jobs">
        <div className="section-head">
          <h2>Jobs</h2>
          {snapshot.truncated.jobs ? (
            <TruncationNote truncated shown={snapshot.jobs.length} noun="jobs" />
          ) : (
            <span className="count">{snapshot.jobs.length}</span>
          )}
        </div>
        {snapshot.jobs.map((job) => (
          <JobRow key={`${job.ref.source_id}/${job.ref.id}`} job={job} />
        ))}
      </section>

      <section className="section" aria-label="Sessions">
        <div className="section-head">
          <h2>Sessions</h2>
          {snapshot.truncated.sessions ? (
            <TruncationNote truncated shown={snapshot.sessions.length} noun="sessions" />
          ) : (
            <span className="count">{snapshot.sessions.length}</span>
          )}
        </div>
        <p className="hint">
          found in local history; activity, not proof of execution
        </p>
        <div className="session-list">
          {snapshot.sessions.map((session) => (
            <SessionRow key={`${session.ref.source_id}/${session.ref.id}`} session={session} />
          ))}
        </div>
      </section>

      {terminal.length > 0 ? (
        <details className="terminal-runs">
          <summary>
            Recent terminal runs ({terminal.length}
            {snapshot.truncated.runs ? "+" : ""}) — done work recedes
          </summary>
          {terminal.map((run) => (
            <RunRow key={`${run.ref.source_id}/${run.ref.id}`} run={run} />
          ))}
        </details>
      ) : null}
    </main>
  );
}

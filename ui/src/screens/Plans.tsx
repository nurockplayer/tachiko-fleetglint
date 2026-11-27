import type { Fetcher } from "../api/client";
import type { Criterion, OwnerDecision, PlanLink, PlanResult, PlansResponse } from "../api/plans";
import { usePolling } from "../api/useSnapshot";
import { Section } from "../components/Section";
import { StateBadge } from "../components/StateBadge";
import type { BadgeState } from "../states";
import { formatAbsolute } from "../format";
import { Banner } from "../components/Banner";

const statusStates: Record<string, BadgeState> = {
  PASS: "done", FAIL: "failed", BLOCKED: "waiting", PENDING: "queued", STALE: "stale",
  OPEN: "needs", ANSWERED: "done", ACTIVE: "running",
  pending: "queued", invalid: "failed", unavailable: "lost", failed: "failed",
};

function Status({ status }: { status: string }) {
  return <StateBadge state={statusStates[status] ?? "unknown"} label={status} />;
}

function InlineText({ text }: { text: string }) {
  return <>{text.split(/(`[^`]+`)/g).map((part, index) =>
    part.startsWith("`") && part.endsWith("`") ? <code key={index}>{part.slice(1, -1)}</code> : part
  )}</>;
}

function Counts({ counts }: { counts: Record<string, number> }) {
  return <span className="plan-counts">{Object.entries(counts).map(([status, count]) =>
    <span key={status}>{status === "total" ? "total" : <Status status={status} />}: {count} </span>
  )}</span>;
}

function Links({ links = [] }: { links?: PlanLink[] }) {
  return <ul className="plan-links">{links.map((link, index) => <li key={index}>
    {link.url.startsWith("https://") ? <a href={link.url} target="_blank" rel="noreferrer noopener">{link.label}</a> : link.label}
  </li>)}</ul>;
}

function CriterionRow({ row, detail = false }: { row: Criterion; detail?: boolean }) {
  return <li className="plan-row">
    <p><strong>{row.id}</strong> · <Status status={row.status} />{row.requirement ? <> · <InlineText text={row.requirement} /></> : null}</p>
    {row.reason ? <p><InlineText text={row.reason} /></p> : null}
    {row.changed_files?.length ? <p className="mono">Changed files: {row.changed_files.join(", ")}</p> : null}
    {detail ? <>
      {row.status_detail ? <p><InlineText text={row.status_detail} /></p> : null}
      {row.context ? <p><InlineText text={row.context} /></p> : null}
      <p>Judge: {row.judge ? <InlineText text={row.judge} /> : "not recorded"}</p>
      <p>Verified at: {row.verified_at ? formatAbsolute(row.verified_at) : "not recorded"}</p>
      {row.verified_sha ? <p className="mono">Verified SHA: {row.verified_sha}</p> : null}
      <Links links={row.evidence} /><Links links={row.references} />
    </> : null}
  </li>;
}

function Decision({ decision }: { decision: OwnerDecision }) {
  return <li className="plan-row">
    <p><strong><InlineText text={decision.question} /></strong> · <Status status={decision.state} /></p>
    <p>Options: <InlineText text={decision.options.join(" · ")} /></p>
    <p>Recommendation: <InlineText text={decision.recommendation} /></p>
    <p>Deadline: {decision.deadline}</p>
    {decision.answer ? <p>Answer: <InlineText text={decision.answer} /></p> : null}
    {decision.answer_ref ? <Links links={[{ label: "Recorded answer", url: decision.answer_ref }]} /> : null}
  </li>;
}

function Plan({ plan }: { plan: PlanResult }) {
  const streams = plan.workstreams ?? [];
  const decisions = plan.owner_decisions ?? [];
  const outstanding = streams.flatMap((stream) => stream.criteria).filter((row) => row.status !== "PASS");
  return <article className="panel plan-panel">
    <h2>{plan.project ?? plan.path} {plan.plan_state ? <Status status={plan.plan_state} /> : null}</h2>
    {plan.counts ? <p><Counts counts={plan.counts} /></p> : null}
    {plan.state !== "ok" ? <p><Status status={plan.state} /></p> : null}
    {plan.refreshing ? <p>Refresh in progress; showing cached result</p> : null}
    <p className="quiet">Checked at: {plan.checked_at ? formatAbsolute(plan.checked_at) : "not checked yet"}</p>
    <p className="quiet">File modified: {plan.file_modified_at ? formatAbsolute(plan.file_modified_at) : "not available"}</p>
    <p className="quiet mono">{plan.path}</p>
    {plan.errors?.map((error, index) => <p key={index}>{error}</p>)}
    {plan.state === "ok" ? <>
      {!plan.text_available ? <p>Plan text needs a newer plan-check.</p> : null}
      <Section id={`decisions-${plan.path}`} heading="Open Owner decisions">
        {!plan.text_available ? <p>Owner decisions are unavailable.</p>
          : decisions.some((d) => d.state === "OPEN") ? <ul>{decisions.filter((d) => d.state === "OPEN").map((d) => <Decision key={d.id} decision={d} />)}</ul>
          : <p>No open Owner decisions.</p>}
      </Section>
      {decisions.some((d) => d.state === "ANSWERED") ? <details className="detail-details">
        <summary>Answered Owner decisions</summary>
        <ul>{decisions.filter((d) => d.state === "ANSWERED").map((d) => <Decision key={d.id} decision={d} />)}</ul>
      </details> : null}
      <Section id={`criteria-${plan.path}`} heading="Criteria needing acceptance">
        {outstanding.length ? <ul>{outstanding.map((row) => <CriterionRow key={row.id} row={row} />)}</ul> : <p>No criteria reported outside PASS.</p>}
      </Section>
      {streams.map((stream) => <details key={stream.id} className="detail-details">
        <summary><span className="plan-chevron" aria-hidden="true">▸</span> {stream.title ?? stream.id} <Counts counts={stream.criteria.reduce<Record<string, number>>((counts, row) => { counts[row.status] = (counts[row.status] ?? 0) + 1; return counts; }, {})} /></summary>
        {stream.outcome ? <p>Outcome: <InlineText text={stream.outcome} /></p> : null}
        {stream.lead ? <p>Lead: {stream.lead}</p> : null}
        {stream.phases ? <p>Phases: {stream.phases.map((phase) => `${phase.title}${phase.id === stream.current_phase ? " (current)" : ""}`).join(" → ")}</p> : null}
        {stream.next_step ? <p>Next step: <InlineText text={stream.next_step} /></p> : null}
        {stream.context?.map((text, index) => <p key={index}><InlineText text={text} /></p>)}
        <Links links={stream.references} />
        <ul>{stream.criteria.map((row) => <CriterionRow key={row.id} row={row} detail />)}</ul>
      </details>)}
    </> : null}
  </article>;
}

export function Plans({ fetcher }: { fetcher: Fetcher }) {
  const state = usePolling<PlansResponse>(fetcher, "/api/plans", 15000);
  return <main className="screen detail-screen">
    <h1>Plans</h1>
    {state.status === "unavailable" ? <Banner kind="unavailable">{state.error} · cached plans below; current state cannot be verified</Banner> : null}
    {state.status === "loading" ? <p>Loading plans…</p> : null}
    {state.data?.plans.length === 0 ? <p>Enable Plans by adding <code>[plans]</code> and <code>paths = ["~/Developer/project"]</code> to your Fleetglint config.toml. List repository directories or explicit plan files.</p> : null}
    <div className={state.status === "unavailable" ? "detail-body is-stale" : "detail-body"}>
      {state.data?.plans.map((plan, index) => <Plan key={`${index}-${plan.path}`} plan={plan} />)}
    </div>
  </main>;
}

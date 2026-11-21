import type { Fetcher } from "../api/client";
import type { Criterion, OwnerDecision, PlanLink, PlanResult, PlansResponse } from "../api/plans";
import { usePolling } from "../api/useSnapshot";
import { Section } from "../components/Section";
import { Banner } from "../components/Banner";

function Links({ links = [] }: { links?: PlanLink[] }) {
  return <ul className="plan-links">{links.map((link, index) => <li key={index}>
    {link.url.startsWith("https://") ? <a href={link.url} target="_blank" rel="noreferrer noopener">{link.label}</a> : link.label}
  </li>)}</ul>;
}

function CriterionRow({ row, detail = false }: { row: Criterion; detail?: boolean }) {
  return <li className="plan-row">
    <p><strong>{row.id} · {row.status}</strong>{row.requirement ? ` · ${row.requirement}` : ""}</p>
    {row.reason ? <p>{row.reason}</p> : null}
    {row.changed_files?.length ? <p className="mono">Changed files: {row.changed_files.join(", ")}</p> : null}
    {detail ? <>
      {row.status_detail ? <p>{row.status_detail}</p> : null}
      {row.context ? <p>{row.context}</p> : null}
      <p>Judge: {row.judge ?? "not recorded"}</p>
      <p>Verified at: {row.verified_at ?? "not recorded"}</p>
      {row.verified_sha ? <p className="mono">Verified SHA: {row.verified_sha}</p> : null}
      <Links links={row.evidence} /><Links links={row.references} />
    </> : null}
  </li>;
}

function Decision({ decision }: { decision: OwnerDecision }) {
  return <li className="plan-row">
    <p><strong>{decision.question}</strong> · {decision.state}</p>
    <p>Options: {decision.options.join(" · ")}</p>
    <p>Recommendation: {decision.recommendation}</p>
    <p>Deadline: {decision.deadline}</p>
    {decision.answer ? <p>Answer: {decision.answer}</p> : null}
    {decision.answer_ref ? <Links links={[{ label: "Recorded answer", url: decision.answer_ref }]} /> : null}
  </li>;
}

function Plan({ plan }: { plan: PlanResult }) {
  const streams = plan.workstreams ?? [];
  const decisions = plan.owner_decisions ?? [];
  const outstanding = streams.flatMap((stream) => stream.criteria).filter((row) => row.status !== "PASS");
  return <article className="panel plan-panel">
    <h2>{plan.project ?? plan.path}{plan.plan_state ? ` · ${plan.plan_state}` : ""}</h2>
    <p>{plan.state}{plan.refreshing ? " · refresh in progress; showing cached result" : ""}</p>
    {plan.state === "ok" && plan.counts ? <p className="plan-counts">{Object.entries(plan.counts).map(([status, count]) => `${status}: ${count}`).join(" · ")}</p> : null}
    <p className="quiet">Checked at: {plan.checked_at ?? "not checked yet"}</p>
    <p className="quiet">File modified: {plan.file_modified_at ?? "not available"}</p>
    <p className="quiet mono">{plan.path}</p>
    {plan.errors?.map((error, index) => <p key={index}>{error}</p>)}
    {plan.state === "ok" ? <>
      {!plan.text_available ? <p>Plan text needs a newer plan-check.</p> : null}
      <Section id={`decisions-${plan.path}`} heading="Open Owner decisions">
        {decisions.some((d) => d.state === "OPEN") ? <ul>{decisions.filter((d) => d.state === "OPEN").map((d) => <Decision key={d.id} decision={d} />)}</ul> : <p>No open Owner decisions.</p>}
      </Section>
      {decisions.some((d) => d.state === "ANSWERED") ? <details className="detail-details">
        <summary>Answered Owner decisions</summary>
        <ul>{decisions.filter((d) => d.state === "ANSWERED").map((d) => <Decision key={d.id} decision={d} />)}</ul>
      </details> : null}
      <Section id={`criteria-${plan.path}`} heading="Criteria needing acceptance">
        {outstanding.length ? <ul>{outstanding.map((row) => <CriterionRow key={row.id} row={row} />)}</ul> : <p>No criteria reported outside PASS.</p>}
      </Section>
      {streams.map((stream) => <details key={stream.id} className="detail-details">
        <summary>{stream.title ?? stream.id}</summary>
        {stream.outcome ? <p>Outcome: {stream.outcome}</p> : null}
        {stream.lead ? <p>Lead: {stream.lead}</p> : null}
        {stream.phases ? <p>Phases: {stream.phases.map((phase) => `${phase.title}${phase.id === stream.current_phase ? " (current)" : ""}`).join(" → ")}</p> : null}
        {stream.next_step ? <p>Next step: {stream.next_step}</p> : null}
        {stream.context?.map((text, index) => <p key={index}>{text}</p>)}
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

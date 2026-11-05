import type { Evidence, ExtendedRef, Ref, Source } from "../api/types";
import { detailHref } from "../router";
import { formatAge } from "../format";

export function SourceChip({ source }: { source: Source }) {
  const status = source.quarantine_count > 0 && source.status === "ok" ? "quarantine" : source.status;
  return (
    <span
      className="source-chip"
      data-status={status}
      data-source-id={source.source_id}
      title={source.detail ?? `${source.records} records from this source`}
    >
      <span className="dot" aria-hidden="true" />
      {source.source_id}
      {status !== "ok" ? <span className="chip-status">{status}</span> : null}
      {source.quarantine_count > 0 ? (
        <span className="chip-status">q{source.quarantine_count}</span>
      ) : null}
    </span>
  );
}

const EVIDENCE_LABEL: Record<Evidence["kind"], string> = {
  process: "pid ok",
  process_gone: "pid gone",
  observed: "refresh",
  expired: "no evidence",
  terminal: "terminal",
  writer_unknown: "writer unknown",
  source_problem: "source problem",
  activity: "activity",
};

/** How old the evidence is and what kind it is: `pid ok 12s`, `no evidence 42m`. */
export function EvidenceLabel({ evidence }: { evidence: Evidence }) {
  const age = evidence.age_s == null ? null : formatAge(evidence.age_s);
  const label = EVIDENCE_LABEL[evidence.kind] ?? evidence.kind;
  return (
    <span className="evidence-label mono" data-evidence-kind={evidence.kind}>
      {label}
      {age ? ` ${age}` : ""}
      {evidence.detail ? ` · ${evidence.detail}` : ""}
    </span>
  );
}

export function refText(ref: Ref): string {
  if (ref.type === "external") return `${ref.kind} · ${ref.key ?? ref.url ?? "—"}`;
  return `${ref.type} · ${ref.id}`;
}

export interface RefLinkProps {
  ref: Ref;
  unresolved?: boolean;
}

/**
 * A record ref links to its detail route. An unresolved ref is shown with a
 * dashed underline and "not seen"; an external ref opens its url in a new tab.
 */
export function RefLink({ ref, unresolved }: RefLinkProps) {
  if (ref.type === "external") {
    const label = (
      <>
        <span className="ref-kind">{ref.kind}</span>
        <span className="ref-id">{ref.key ?? ref.url ?? "—"}</span>
      </>
    );
    if (!ref.url) {
      return <span className="ref-link external">{label}</span>;
    }
    return (
      <a
        className="ref-link external"
        href={ref.url}
        target="_blank"
        rel="noreferrer noopener"
      >
        {label}
      </a>
    );
  }

  const record = ref as ExtendedRef;
  const isUnresolved = unresolved ?? record.resolved === false;
  const label = (
    <>
      <span className="ref-type">{record.type}</span>
      <span className="ref-id">{record.id}</span>
    </>
  );

  if (isUnresolved) {
    return (
      <span className="ref-link unresolved" title="referenced record has not been seen">
        {label}
        <span className="ref-notseen">not seen</span>
      </span>
    );
  }

  return (
    <a className="ref-link" href={detailHref(record)}>
      {label}
    </a>
  );
}

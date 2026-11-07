import type { ExtendedRef, Ref } from "../api/types";
import { detailHref } from "../router";

/** The short key of a ref: an external ref's key, or a record's id. */
export function refKey(ref: Ref): string {
  if (ref.type === "external") return ref.key ?? ref.url ?? ref.kind;
  return ref.id;
}

/** Words for an external ref: `job scan-3`, `github_pr owner/repo#3`. */
export function externalRefWords(ref: Ref): string {
  if (ref.type !== "external") return `${ref.type} ${ref.id}`;
  return `${ref.kind} ${ref.key ?? ref.url ?? ""}`.trim();
}

export interface RefLinkProps {
  ref: Ref;
  unresolved?: boolean;
}

/**
 * A record ref links to its detail route. An unresolved ref is shown with the
 * unresolved line treatment and "not found"; an external ref opens its url in
 * a new tab.
 */
export function RefLink({ ref, unresolved }: RefLinkProps) {
  if (ref.type === "external") {
    const label = (
      <>
        <span className="ref-kind">{ref.kind}</span>
        <span className="ref-id">{ref.key ?? ref.url ?? ""}</span>
      </>
    );
    if (!ref.url) {
      return <span className="ref-link external">{label}</span>;
    }
    return (
      <a className="ref-link external" href={ref.url} target="_blank" rel="noreferrer noopener">
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
      <span className="ref-link is-unresolved" title="the referenced record has not been seen">
        {label}
        <span className="ref-not-found">not found</span>
      </span>
    );
  }

  return (
    <a className="ref-link" href={detailHref(record)}>
      {label}
    </a>
  );
}

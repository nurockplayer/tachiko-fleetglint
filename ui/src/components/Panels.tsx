import { Fragment, type ReactNode } from "react";
import type {
  ExtendedRef,
  FileResponse,
  Ref,
  Relations,
  Snapshot,
} from "../api/types";
import { formatAbsolute, formatAge, formatBytes } from "../format";
import { StateBadge } from "./StateBadge";
import { RefLink, SourceChip } from "./Refs";

export function TopBar({
  snapshot,
  lastRefreshAt,
}: {
  snapshot: Snapshot | null;
  lastRefreshAt: number | null;
}) {
  return (
    <header className="topbar">
      <a className="mark" href="/">
        Fleetglint
      </a>
      <div className="source-strip" aria-label="source health">
        {snapshot
          ? snapshot.sources.map((source) => (
              <SourceChip key={source.source_id} source={source} />
            ))
          : null}
      </div>
      <div className="topbar-meta">
        <span
          title={
            lastRefreshAt
              ? formatAbsolute(new Date(lastRefreshAt).toISOString())
              : "no successful refresh yet"
          }
        >
          last refresh{" "}
          {lastRefreshAt
            ? `${formatAge((Date.now() - lastRefreshAt) / 1000)} ago`
            : "never"}
        </span>
        <span className="read-only">read-only</span>
      </div>
    </header>
  );
}

export type BannerKind = "unavailable" | "discontinuity" | "quarantine" | "demo";

const BANNER_LABEL: Record<BannerKind, string> = {
  unavailable: "Unavailable",
  discontinuity: "Discontinuity",
  quarantine: "Quarantine",
  demo: "DEMO DATA",
};

export function Banner({ kind, children }: { kind: BannerKind; children: ReactNode }) {
  return (
    <div
      className={`banner banner-${kind}`}
      role={kind === "unavailable" ? "alert" : "status"}
      data-banner={kind}
    >
      <strong>{BANNER_LABEL[kind]}</strong>
      <span>{children}</span>
    </div>
  );
}

function RelationGroup({
  label,
  refs,
}: {
  label: string;
  refs: ExtendedRef[];
}) {
  if (refs.length === 0) return null;
  return (
    <div className="rel-group">
      <span className="label">{label}</span>
      {refs.map((ref) => (
        <span className="rel-item" key={`${ref.source_id}/${ref.type}/${ref.id}`}>
          <RefLink ref={ref} />
          {ref.display_state ? <StateBadge state={ref.display_state} /> : null}
          {ref.title ? <span className="muted">{ref.title}</span> : null}
        </span>
      ))}
    </div>
  );
}

export function RelationshipTree({
  relations,
  waitsOn,
}: {
  relations: Relations;
  waitsOn?: Ref[];
}) {
  const hasRunRelations =
    relations.parent !== null ||
    relations.resume_of !== null ||
    relations.children.length > 0 ||
    relations.resumed_by.length > 0 ||
    relations.inbox.length > 0 ||
    relations.waited_on_by.length > 0 ||
    (waitsOn?.length ?? 0) > 0;
  if (!hasRunRelations) return null;

  return (
    <section className="panel" aria-label="Relationships">
      <h2>Relationships</h2>
      {relations.parent ? <RelationGroup label="parent" refs={[relations.parent]} /> : null}
      <RelationGroup label="spawned" refs={relations.children} />
      {relations.resume_of ? (
        <RelationGroup label="continues" refs={[relations.resume_of]} />
      ) : null}
      <RelationGroup label="resumed by" refs={relations.resumed_by} />
      <RelationGroup label="inbox" refs={relations.inbox} />
      <RelationGroup label="waited on by" refs={relations.waited_on_by} />
      {waitsOn && waitsOn.length > 0 ? (
        <div className="rel-group">
          <span className="label">waits on</span>
          {waitsOn.map((ref, index) => (
            <span className="rel-item" key={index}>
              <RefLink ref={ref} />
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

const NOT_READABLE_REASON: Record<string, string> = {
  outside_allowed_roots: "outside the allowed roots",
  not_regular_file: "not a regular file",
  missing: "missing",
  not_utf8: "not UTF-8 text",
  no_path: "no path on the record",
};

export function LogTail({
  file,
  loading,
  error,
}: {
  file: FileResponse | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) return <p className="muted">loading log…</p>;
  if (error) return <p className="muted">log unavailable — {error}</p>;
  if (!file) return <p className="muted">no log attached to this record</p>;
  if (!file.readable) {
    return (
      <div className="log not-readable" data-log="not-readable">
        <p>not readable</p>
        <p className="muted">{NOT_READABLE_REASON[file.reason] ?? file.reason}</p>
      </div>
    );
  }

  const parts = file.text.split("[redacted]");
  return (
    <div className="log" data-log="readable">
      {file.truncated ? (
        <p className="log-note">
          showing the last part of {formatBytes(file.size)} · {file.redactions} redacted
          span{file.redactions === 1 ? "" : "s"}
        </p>
      ) : null}
      <pre>
        {parts.map((part, index) => (
          <Fragment key={index}>
            {part}
            {index < parts.length - 1 ? (
              <span className="redacted" title="removed before display">
                [redacted]
              </span>
            ) : null}
          </Fragment>
        ))}
      </pre>
    </div>
  );
}

const EMIT_EXAMPLE = `fleetglint emit <<'EOF'
{"v":1,"type":"run","id":"hello-1","source_id":"me@mbp","updated_at":"2026-11-06T04:00:00+09:00","state":"running","agent":"human","started_at":"2026-11-06T04:00:00+09:00"}
EOF`;

export function EmptyState() {
  return (
    <div className="empty">
      <h1>No sources yet</h1>
      <p>
        Fleetglint found no records and no readable sources. It only reads local
        files; nothing is sent anywhere.
      </p>
      <h2>It looked for</h2>
      <ul>
        <li>Claude Code transcripts — ~/.claude/projects</li>
        <li>Codex rollouts — ~/.codex/sessions</li>
        <li>tachiko-harness state — ~/.local/state</li>
        <li>NDJSON root — ~/.local/state/fleetglint/sources</li>
      </ul>
      <h2>Check what it sees</h2>
      <pre>fleetglint doctor</pre>
      <h2>Try labelled sample data</h2>
      <pre>fleetglint demo</pre>
      <h2>Write one record</h2>
      <pre>{EMIT_EXAMPLE}</pre>
    </div>
  );
}

import { useEffect, useState, type ReactNode } from "react";
import type {
  FileResponse,
  InboxSummary,
  JobSummary,
  RecordResponse,
  RunSummary,
  SessionSummary,
  Summary,
  Usage,
} from "../api/types";
import { fileUrl, recordUrl, type Fetcher } from "../api/client";
import type { DetailParams } from "../router";
import {
  ageSince,
  formatAbsolute,
  formatAge,
  formatCost,
  formatNumber,
} from "../format";
import { StateBadge, StateTransition } from "../components/StateBadge";
import { EvidenceLabel, RefLink } from "../components/Refs";
import { Banner, LogTail, RelationshipTree } from "../components/Panels";

interface LogTarget {
  source_id: string;
  type: string;
  id: string;
  field: "log_path" | "result_path" | "link";
  index?: number;
}

function logTarget(record: Summary): LogTarget | null {
  const base = {
    source_id: record.ref.source_id,
    type: record.ref.type,
    id: record.ref.id,
  };
  if (record.ref.type === "job") {
    const job = record as JobSummary;
    return job.log ? { ...base, field: "log_path" } : null;
  }
  if (record.ref.type === "run") {
    const run = record as RunSummary;
    const index = run.links.findIndex((link) => typeof link.path === "string");
    return index >= 0 ? { ...base, field: "link", index } : null;
  }
  return null;
}

function roleOf(record: Summary): string | null {
  if (record.ref.type === "inbox_item") return (record as InboxSummary).role_id;
  if (record.ref.type === "session") return (record as SessionSummary).role_id;
  if (record.ref.type === "job") return (record as JobSummary).role_id;
  return (record as RunSummary).role_id;
}

function transitionAge(record: Summary): string | null {
  const showsAge = ["stale", "lost", "unknown", "recent", "idle"].includes(
    record.display_state,
  );
  if (!showsAge) return null;
  return formatAge(record.evidence.age_s ?? ageSince(record.updated_at));
}

function Header({ record }: { record: Summary }) {
  let title: ReactNode = record.title ?? record.ref.id;
  let titleMono = false;
  let primary: ReactNode = null;

  if (record.ref.type === "run") {
    const run = record as RunSummary;
    title = run.title ?? run.ref.id;
    primary = (
      <span className="mono">
        {run.agent}
        {run.model ? ` · ${run.model}` : ""}
        {run.effort ? ` · effort ${run.effort}` : ""}
      </span>
    );
  } else if (record.ref.type === "job") {
    const job = record as JobSummary;
    title = job.command_summary;
    titleMono = true;
    primary = (
      <span className="mono">
        {job.kind ?? "job"}
        {job.exit_code != null ? ` · exit ${job.exit_code}` : ""}
        {job.signal ? ` · signal ${job.signal}` : ""}
      </span>
    );
  } else if (record.ref.type === "inbox_item") {
    const item = record as InboxSummary;
    title = `${item.kind}${item.outcome ? ` · ${item.outcome}` : ""}`;
    titleMono = true;
    primary = (
      <span className="detail-line">
        <span>
          subject <RefLink ref={item.subject} />
        </span>
        {item.action_required ? <StateBadge state="attention" /> : null}
        <span className="muted">{formatAge(ageSince(item.created_at))} old</span>
      </span>
    );
  } else {
    const session = record as SessionSummary;
    title = session.title ?? session.ref.id;
    primary = (
      <span className="mono">
        {session.agent}
        {session.model ? ` · ${session.model}` : ""}
        {session.project ? ` · ${session.project}` : ""}
        {session.entries != null ? ` · ${session.entries} entries` : ""}
      </span>
    );
  }

  const startedLike =
    record.ref.type === "run"
      ? (record as RunSummary).started_at
      : record.ref.type === "job"
        ? (record as JobSummary).started_at
        : record.ref.type === "session"
          ? (record as SessionSummary).last_activity_at
          : null;

  return (
    <header className="detail-head">
      <div className="breadcrumb">
        Overview / {record.project ?? "—"} / {record.ref.type} · {record.ref.id}
      </div>
      <h1 className={`detail-title${titleMono ? " is-mono" : ""}`}>{title}</h1>
      <div className="detail-line">
        <StateTransition
          writerState={record.state}
          displayState={record.display_state}
          age={transitionAge(record)}
        />
        {primary}
      </div>
      <div className="detail-line">
        <span>
          role <span className="mono">{roleOf(record) ?? "—"}</span>
        </span>
        <span>
          source <span className="mono">{record.ref.source_id}</span>
        </span>
        {startedLike ? (
          <span>
            started{" "}
            <span className="mono" title={formatAbsolute(startedLike)}>
              {formatAbsolute(startedLike)}
            </span>
          </span>
        ) : null}
        <EvidenceLabel evidence={record.evidence} />
      </div>
      {record.ref.type === "inbox_item" && (record as InboxSummary).detail ? (
        <p className="inbox-detail">{(record as InboxSummary).detail}</p>
      ) : null}
    </header>
  );
}

function UsagePanel({ usage }: { usage: Usage }) {
  return (
    <section className="panel" aria-label="Usage">
      <h2>Usage</h2>
      <dl className="usage-grid">
        {usage.input_tokens != null ? (
          <div>
            <dt>input tokens</dt>
            <dd>
              {formatNumber(usage.input_tokens)}
              {usage.cached_input_tokens != null
                ? ` (cached ${formatNumber(usage.cached_input_tokens)})`
                : ""}
            </dd>
          </div>
        ) : null}
        {usage.output_tokens != null ? (
          <div>
            <dt>output tokens</dt>
            <dd>{formatNumber(usage.output_tokens)}</dd>
          </div>
        ) : null}
        {usage.cost ? (
          <div>
            <dt>cost</dt>
            <dd>
              {formatCost(usage.cost)} · {usage.cost.basis}
            </dd>
          </div>
        ) : null}
      </dl>
      <p className="basis-note">
        token basis: {usage.basis}
        {usage.cost ? ` · cost basis: ${usage.cost.basis}` : ""} · cost bases are never
        added together
      </p>
    </section>
  );
}

function LinksPanel({ record }: { record: Summary }) {
  if (record.links.length === 0) return null;
  return (
    <section className="panel" aria-label="Links">
      <h2>Links</h2>
      <ul className="link-list">
        {record.links.map((link, index) => (
          <li key={`${link.label}/${index}`}>
            <span className="label">{link.label}</span>
            {link.url ? (
              <a href={link.url} target="_blank" rel="noreferrer noopener">
                {link.url}
              </a>
            ) : (
              <span className="path">{link.path}</span>
            )}
            {link.path && link.readable === false ? (
              <span className="not-readable">not readable</span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

type DetailState =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ok"; data: RecordResponse };

interface FileState {
  loading: boolean;
  data: FileResponse | null;
  error: string | null;
}

export function RunDetail({ params, fetcher }: { params: DetailParams; fetcher: Fetcher }) {
  const [detail, setDetail] = useState<DetailState>({ status: "loading" });
  const [file, setFile] = useState<FileState>({ loading: false, data: null, error: null });

  useEffect(() => {
    let cancelled = false;
    setDetail({ status: "loading" });
    (async () => {
      try {
        const response = await fetcher(recordUrl(params), { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const body = (await response.json()) as RecordResponse;
        if (body.api !== 1) throw new Error("unsupported API version");
        if (!cancelled) setDetail({ status: "ok", data: body });
      } catch (error) {
        if (!cancelled) {
          setDetail({
            status: "error",
            error: error instanceof Error ? error.message : String(error),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fetcher, params.source_id, params.type, params.id]);

  const record = detail.status === "ok" ? detail.data.record : null;
  const target = record ? logTarget(record) : null;
  const targetKey = target
    ? `${target.source_id}/${target.type}/${target.id}/${target.field}/${target.index ?? ""}`
    : "";

  useEffect(() => {
    if (!target) {
      setFile({ loading: false, data: null, error: null });
      return;
    }
    let cancelled = false;
    setFile({ loading: true, data: null, error: null });
    (async () => {
      try {
        const response = await fetcher(fileUrl(target), { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const body = (await response.json()) as FileResponse;
        if (body.api !== 1) throw new Error("unsupported API version");
        if (!cancelled) setFile({ loading: false, data: body, error: null });
      } catch (error) {
        if (!cancelled) {
          setFile({
            loading: false,
            data: null,
            error: error instanceof Error ? error.message : String(error),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetcher, targetKey]);

  if (detail.status === "loading") {
    return (
      <main className="screen detail">
        <p className="muted">loading record…</p>
      </main>
    );
  }

  if (detail.status === "error") {
    return (
      <main className="screen detail">
        <Banner kind="unavailable">{detail.error}</Banner>
        <p className="muted" style={{ marginTop: "16px" }}>
          The record could not be read. Reload to try again.
        </p>
      </main>
    );
  }

  const { data } = detail;
  const current = data.record;
  const usage = data.usage ?? (current.ref.type === "session" ? (current as SessionSummary).usage : null);
  const ownedJobs = current.ref.type === "run" ? data.relations.jobs : [];
  const waitsOn = current.ref.type === "run" ? (current as RunSummary).waits_on : [];

  return (
    <main className="screen detail">
      <Header record={current} />

      {ownedJobs.length > 0 ? (
        <section className="panel" aria-label="Owned jobs">
          <h2>Owned jobs</h2>
          {ownedJobs.map((ref) => (
            <div className="rel-item" key={`${ref.source_id}/${ref.id}`}>
              <RefLink ref={ref} />
              {ref.display_state ? <StateBadge state={ref.display_state} /> : null}
              {ref.title ? <span className="muted">{ref.title}</span> : null}
            </div>
          ))}
        </section>
      ) : null}

      <RelationshipTree relations={data.relations} waitsOn={waitsOn} />

      {data.history.length > 0 ? (
        <section className="panel" aria-label="Version history">
          <h2>Version history</h2>
          <ul className="history-list">
            {data.history.map((entry) => (
              <li key={`${entry.seq}/${entry.byte_offset}`}>
                <span>#{entry.seq}</span>
                <span title={formatAbsolute(entry.updated_at)}>
                  {formatAbsolute(entry.updated_at)}
                </span>
                <span>{entry.state}</span>
                <span className="muted">position {entry.byte_offset}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {usage ? <UsagePanel usage={usage} /> : null}

      <LinksPanel record={current} />

      {target ? (
        <section className="panel" aria-label="Log">
          <h2>Log</h2>
          <LogTail file={file.data} loading={file.loading} error={file.error} />
        </section>
      ) : null}

      <details className="raw">
        <summary>Raw fields (redacted)</summary>
        <pre>{JSON.stringify(data.full, null, 2)}</pre>
      </details>
    </main>
  );
}

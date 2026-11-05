import { useEffect, useRef, useState, type ReactNode } from "react";
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
  formatClock,
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

interface DetailState {
  data: RecordResponse | null;
  receivedAt: number | null;
  error: string | null;
  loading: boolean;
}

interface FileState {
  loading: boolean;
  data: FileResponse | null;
  error: string | null;
}

export function RunDetail({
  params,
  fetcher,
  pollMs = 3000,
}: {
  params: DetailParams;
  fetcher: Fetcher;
  pollMs?: number;
}) {
  const [detail, setDetail] = useState<DetailState>({
    data: null,
    receivedAt: null,
    error: null,
    loading: true,
  });
  const [file, setFile] = useState<FileState>({ loading: false, data: null, error: null });

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let etag: string | null = null;
    let last: { data: RecordResponse; receivedAt: number } | null = null;
    let inFlight = false;
    setDetail({ data: null, receivedAt: null, error: null, loading: true });

    const schedule = () => {
      if (!stopped) timer = setTimeout(tick, pollMs);
    };

    // The detail page polls like the board: a 304 keeps the record, a failure
    // keeps it on screen greyed and labelled with its time, and recovery is
    // automatic. One request is in flight at a time, so a visibility change
    // cannot start a second loop or let an older response win.
    async function tick() {
      if (inFlight) return;
      if (document.hidden) {
        schedule();
        return;
      }
      inFlight = true;
      try {
        const headers: Record<string, string> = {};
        if (etag) headers["If-None-Match"] = etag;
        const response = await fetcher(recordUrl(params), {
          headers,
          cache: "no-store",
        });
        let next: { data: RecordResponse; receivedAt: number } | null = null;
        if (response.status === 304) {
          if (!last) throw new Error("HTTP 304 without cached data");
          next = { data: last.data, receivedAt: Date.now() };
        } else if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        } else {
          const body = (await response.json()) as RecordResponse;
          if (body.api !== 1) throw new Error("unsupported API version");
          const tag = response.headers.get("ETag");
          if (tag) etag = tag;
          next = { data: body, receivedAt: Date.now() };
        }
        if (!next) throw new Error("no record");
        last = next;
        if (!stopped) {
          setDetail({
            data: next.data,
            receivedAt: next.receivedAt,
            error: null,
            loading: false,
          });
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (!stopped) {
          setDetail({
            data: last?.data ?? null,
            receivedAt: last?.receivedAt ?? null,
            error: message,
            loading: false,
          });
        }
      } finally {
        inFlight = false;
        schedule();
      }
    }

    const onVisibilityChange = () => {
      if (!document.hidden && !inFlight) {
        clearTimeout(timer);
        void tick();
      }
    };

    void tick();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      stopped = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [fetcher, params.source_id, params.type, params.id, pollMs]);

  const record = detail.data?.record ?? null;
  const target = record ? logTarget(record) : null;
  const targetKey = target
    ? `${target.source_id}/${target.type}/${target.id}/${target.field}/${target.index ?? ""}`
    : "";
  // A live record's log can grow without its updated_at moving, so refetch the
  // tail on every poll; a terminal record only refetches when the record does.
  const live = record?.display_state === "running" || record?.display_state === "waiting";
  const fileKey = target
    ? `${targetKey}/${live ? (detail.receivedAt ?? "") : (record?.updated_at ?? "")}`
    : "";
  const fileTargetRef = useRef("");

  useEffect(() => {
    if (!target) {
      fileTargetRef.current = "";
      setFile({ loading: false, data: null, error: null });
      return;
    }
    const sameTarget = fileTargetRef.current === targetKey;
    fileTargetRef.current = targetKey;
    let cancelled = false;
    // A refetch of the same tail keeps the text on screen: no loading flash
    // and no empty panel while the request is in flight.
    if (!sameTarget) setFile({ loading: true, data: null, error: null });
    (async () => {
      try {
        const response = await fetcher(fileUrl(target), { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const body = (await response.json()) as FileResponse;
        if (body.api !== 1) throw new Error("unsupported API version");
        if (!cancelled) setFile({ loading: false, data: body, error: null });
      } catch (error) {
        if (!cancelled) {
          setFile((previous) => ({
            loading: false,
            data: previous.data,
            error: error instanceof Error ? error.message : String(error),
          }));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetcher, fileKey]);

  const receivedClock =
    detail.receivedAt != null
      ? formatClock(new Date(detail.receivedAt).toISOString())
      : null;

  if (detail.loading && !detail.data) {
    return (
      <main className="screen detail">
        <p className="muted">loading record…</p>
      </main>
    );
  }

  if (!detail.data) {
    return (
      <main className="screen detail">
        <Banner kind="unavailable">{detail.error ?? "the record could not be read"}</Banner>
        <p className="muted" style={{ marginTop: "16px" }}>
          The record could not be read. Reload to try again.
        </p>
      </main>
    );
  }

  const data = detail.data;
  const current = data.record;
  const usage = data.usage ?? (current.ref.type === "session" ? (current as SessionSummary).usage : null);
  const ownedJobs = current.ref.type === "run" ? data.relations.jobs : [];
  const waitsOn = current.ref.type === "run" ? (current as RunSummary).waits_on : [];

  return (
    <main className="screen detail">
      {detail.error ? (
        <>
          <Banner kind="unavailable">
            {detail.error}
            {receivedClock
              ? ` — last good data from ${receivedClock}`
              : " — no data available"}
          </Banner>
          <p className="stale-note">
            Showing last good data from {receivedClock ?? "an earlier poll"} — not
            current.
          </p>
        </>
      ) : null}

      <div className="stale-data" data-stale={detail.error ? "true" : undefined}>
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
      </div>
    </main>
  );
}

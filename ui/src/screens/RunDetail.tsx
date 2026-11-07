import { useEffect, useRef, useState } from "react";
import type {
  ExtendedRef,
  FileResponse,
  InboxSummary,
  JobSummary,
  RecordResponse,
  Ref,
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
  formatAgo,
  formatCost,
  formatNumber,
} from "../format";
import { STATE_LABEL, type BadgeState } from "../states";
import { StateBadge } from "../components/StateBadge";
import { RefLink } from "../components/Refs";
import { Banner } from "../components/Banner";
import { LogTail } from "../components/LogTail";

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

function titleOf(record: Summary): string {
  if (record.ref.type === "inbox_item") return record.title ?? record.ref.id;
  if (record.ref.type === "job") {
    const job = record as JobSummary;
    return job.title ?? job.command_summary;
  }
  return record.title ?? record.ref.id;
}

function looksLikeSlug(text: string): boolean {
  return !text.includes(" ") && /^[A-Za-z0-9._/#:-]+$/.test(text);
}

function modelAndAgent(record: Summary): string[] {
  if (record.ref.type === "run") {
    const run = record as RunSummary;
    return [run.model, run.agent].filter((value): value is string => Boolean(value));
  }
  if (record.ref.type === "session") {
    const session = record as SessionSummary;
    return [session.model, session.agent].filter((value): value is string => Boolean(value));
  }
  if (record.ref.type === "job") {
    const job = record as JobSummary;
    return job.kind ? [job.kind] : [];
  }
  return [];
}

function wordsFor(state: string): string {
  const known = STATE_LABEL[state as BadgeState];
  return known ?? state;
}

/** One sentence about the process evidence, never a fabricated check time. */
function evidenceSentence(record: Summary): string | null {
  const evidence = record.evidence;
  if (evidence.kind === "process") {
    return evidence.age_s != null
      ? `The wrapper process is alive, checked ${formatAgo(evidence.age_s)}.`
      : "The wrapper process is alive.";
  }
  if (evidence.kind === "process_gone") {
    return "The wrapper process is gone; no result was recorded.";
  }
  if (evidence.kind === "expired") {
    return evidence.age_s != null
      ? `No recent process check; the last check was ${formatAgo(evidence.age_s)}.`
      : "No recent process check.";
  }
  if (evidence.kind === "activity") {
    return evidence.age_s != null
      ? `Last activity was ${formatAgo(evidence.age_s)}; activity is not proof of execution.`
      : "Activity is not proof of execution.";
  }
  return null;
}

function resolvedWaitSentence(ref: Ref): string | null {
  if (ref.type === "external") return null;
  const extended = ref as ExtendedRef;
  if (extended.resolved === false || !extended.display_state) {
    return ref.type === "job" ? "Job status not found." : "Record status not found.";
  }
  if (ref.type !== "job") return null;
  if (extended.display_state === "running") {
    return "The worker has handed off and resumes when the job ends.";
  }
  return `The job is ${STATE_LABEL[extended.display_state]}.`;
}

/** What is happening, in words, from display state, waits, evidence and the resolved ref. */
function happeningText(record: Summary, now: number): string {
  const parts: string[] = [];
  const state = record.display_state;

  if (record.ref.type === "run" && state === "waiting") {
    const waits = (record as RunSummary).waits_on[0];
    if (waits) {
      if (waits.type === "external") {
        parts.push(`Waiting on ${waits.key ?? waits.kind}.`);
      } else {
        parts.push(`Waiting on ${waits.type} ${waits.id}.`);
        const resolved = resolvedWaitSentence(waits);
        if (resolved) parts.push(resolved);
      }
    } else {
      parts.push("Waiting; no wait is recorded.");
    }
  } else if (record.ref.type === "job" && (record as JobSummary).kind === "wait") {
    const job = record as JobSummary;
    parts.push(
      (job.title ?? "").startsWith("PR #")
        ? "Waiting on review. The lead resumes when the review ends."
        : "This is a lead's wait; the lead resumes when the job ends.",
    );
  } else if (state === "queued") {
    parts.push("Queued; accepted but not started.");
  } else if (state === "running") {
    parts.push("Running.");
  } else if (state === "done") {
    parts.push("Done.");
  } else if (state === "failed") {
    const exit = record.ref.type === "job" ? (record as JobSummary).exit_code : null;
    parts.push(exit != null ? `Failed with exit ${exit}.` : "Failed.");
  } else if (state === "cancelled") {
    parts.push("Cancelled.");
  } else if (state === "stale") {
    const age = record.evidence.age_s ?? ageSince(record.updated_at, now);
    parts.push(
      age != null
        ? `Out of date: the last update was ${formatAgo(age)}; current state cannot be verified.`
        : "Out of date; current state cannot be verified.",
    );
  } else if (state === "lost") {
    parts.push("Process gone, no result recorded.");
  } else if (state === "unknown") {
    parts.push("Unverified: the writer's state could not be determined.");
  } else if (record.ref.type === "session") {
    parts.push("Session activity is not proof of execution.");
  } else if (record.ref.type === "inbox_item") {
    parts.push(`From ${roleOf(record) ?? "an unknown role"}.`);
  } else {
    parts.push(`State: ${wordsFor(state)}.`);
  }

  const evidence = evidenceSentence(record);
  if (evidence) parts.push(evidence);
  return parts.join(" ");
}

interface Edge {
  words: string;
  ref: Ref;
}

function relationshipEdges(
  record: Summary,
  relations: RecordResponse["relations"],
): Edge[] {
  const edges: Edge[] = [];
  const add = (words: string, ref: Ref | null) => {
    if (ref) edges.push({ words, ref });
  };
  add("parent", relations.parent);
  add("continues", relations.resume_of);
  for (const ref of relations.children) add("spawned", ref);
  for (const ref of relations.resumed_by) add("resumed by", ref);
  for (const ref of relations.jobs) add("job", ref);
  for (const ref of relations.inbox) add("inbox item", ref);
  for (const ref of relations.waited_on_by) add("waited on by", ref);
  if (record.ref.type === "run") {
    for (const ref of (record as RunSummary).waits_on) add("waits on", ref);
  }
  return edges;
}

function isUnresolved(ref: Ref): boolean {
  return ref.type !== "external" && (ref as ExtendedRef).resolved === false;
}

function EvidenceLine({ record, now }: { record: Summary; now: number }) {
  const evidence = record.evidence;
  const observed = formatAgo(ageSince(record.observed_at, now));
  let process: string;
  if (evidence.kind === "process") {
    process =
      evidence.age_s != null
        ? `process check: checked ${formatAgo(evidence.age_s)}`
        : "process check: alive, no age recorded";
  } else if (evidence.kind === "process_gone") {
    process = "process check: the process is gone";
  } else if (evidence.kind === "expired") {
    process =
      evidence.age_s != null
        ? `process check: none recent; last check ${formatAgo(evidence.age_s)}`
        : "process check: none recent";
  } else {
    process = "process check: not observable";
  }
  return (
    <ul className="evidence-list">
      <li>{process}</li>
      <li>writer state: {wordsFor(record.state)}</li>
      <li>
        source: <span className="mono">{record.ref.source_id}</span>
        {observed ? ` · observed ${observed}` : ""}
      </li>
      {evidence.detail ? <li>evidence: {evidence.detail}</li> : null}
    </ul>
  );
}

function UsageDetails({ usage }: { usage: Usage }) {
  return (
    <details className="detail-details">
      <summary>Usage</summary>
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
      <p className="quiet">
        token basis: {usage.basis}
        {usage.cost ? ` · cost basis: ${usage.cost.basis}` : ""} · cost bases are never
        added together
      </p>
    </details>
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
  pollMs = 15000,
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
  // A non-terminal record's log can grow without its updated_at moving, even
  // once it shows stale, so refetch the tail on every poll; a terminal record
  // only refetches when the record does.
  const live = record != null && !["done", "failed", "cancelled"].includes(record.state);
  const fileKey = target
    ? `${targetKey}/${live ? (detail.receivedAt ?? "") : (record?.updated_at ?? "")}`
    : "";
  const fileTargetRef = useRef("");
  const fileRequestRef = useRef<object | null>(null);
  const fileSkippedRef = useRef(false);
  const [fileRetry, setFileRetry] = useState(0);

  useEffect(
    () => () => {
      fileRequestRef.current = null;
    },
    [],
  );

  useEffect(() => {
    if (!target) {
      fileTargetRef.current = "";
      fileRequestRef.current = null;
      setFile({ loading: false, data: null, error: null });
      return;
    }
    const sameTarget = fileTargetRef.current === targetKey;
    fileTargetRef.current = targetKey;
    // A slow tail is left to finish, then fetched once more: the record may
    // already be terminal, and then no later poll would fetch it.
    if (sameTarget && fileRequestRef.current) {
      fileSkippedRef.current = true;
      return;
    }
    fileSkippedRef.current = false;
    const request = {};
    fileRequestRef.current = request;
    const finish = () => {
      fileRequestRef.current = null;
      if (fileSkippedRef.current) setFileRetry((count) => count + 1);
    };
    // A refetch of the same tail keeps the text on screen: no loading flash
    // and no empty panel while the request is in flight.
    if (!sameTarget) setFile({ loading: true, data: null, error: null });
    (async () => {
      try {
        const response = await fetcher(fileUrl(target), { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const body = (await response.json()) as FileResponse;
        if (body.api !== 1) throw new Error("unsupported API version");
        if (fileRequestRef.current === request) {
          finish();
          setFile({ loading: false, data: body, error: null });
        }
      } catch (error) {
        if (fileRequestRef.current === request) {
          finish();
          setFile((previous) => ({
            loading: false,
            data: previous.data,
            error: error instanceof Error ? error.message : String(error),
          }));
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetcher, fileKey, fileRetry]);

  if (detail.loading && !detail.data) {
    return (
      <main className="screen detail-screen">
        <p className="quiet">Loading record…</p>
      </main>
    );
  }

  if (!detail.data) {
    return (
      <main className="screen detail-screen">
        <Banner kind="unavailable">
          {detail.error ?? "the record could not be read"} · current state cannot be
          verified
        </Banner>
      </main>
    );
  }

  const data = detail.data;
  const current = data.record;
  const now = Date.parse(data.generated_at);
  const usage =
    data.usage ?? (current.ref.type === "session" ? (current as SessionSummary).usage : null);
  const edges = relationshipEdges(current, data.relations);
  const title = titleOf(current);
  const role = roleOf(current);
  const meta = modelAndAgent(current);

  return (
    <main className="screen detail-screen">
      {detail.error ? (
        <Banner kind="unavailable">
          {detail.error} · last successful refresh{" "}
          {detail.receivedAt != null
            ? formatAgo((Date.now() - detail.receivedAt) / 1000)
            : "unknown"}{" "}
          · current state cannot be verified
        </Banner>
      ) : null}

      <div className={`detail-body${detail.error ? " is-stale" : ""}`}>
        <nav className="breadcrumb" aria-label="Breadcrumb">
          <a href="/">Overview</a>
          <span className="breadcrumb-sep"> / </span>
          <span>{current.project ?? "no project"}</span>
          <span className="breadcrumb-sep"> / </span>
          <span>{title}</span>
        </nav>

        <header className="detail-head">
          <StateBadge state={current.display_state} />
          <h1 className={`detail-title${looksLikeSlug(title) ? " mono" : ""}`}>{title}</h1>
          <p className="detail-meta">
            {meta.length > 0 ? <span>{meta.join(" · ")}</span> : null}
            {role ? (
              <>
                {meta.length > 0 ? <span className="detail-sep"> · </span> : null}
                <span>role {role}</span>
              </>
            ) : null}
          </p>
        </header>

        <section className="panel" aria-label="What is happening">
          <h2>What is happening</h2>
          <p>{happeningText(current, now)}</p>
        </section>

        <section className="panel" aria-label="Relationships">
          <h2>Relationships</h2>
          {edges.length === 0 ? (
            <p className="quiet">No relationships recorded.</p>
          ) : (
            <ol className="relationship-chain">
              {edges.map((edge, index) => (
                <li
                  className={`relationship-edge${isUnresolved(edge.ref) ? " is-unresolved" : ""}`}
                  key={`${edge.words}/${edge.ref.type === "external" ? edge.ref.kind : edge.ref.id}/${index}`}
                >
                  <span className="edge-words">{edge.words}</span>
                  <RefLink ref={edge.ref} />
                  {edge.ref.type !== "external" && (edge.ref as ExtendedRef).display_state ? (
                    <StateBadge
                      state={(edge.ref as ExtendedRef).display_state as BadgeState}
                      variant="glyph"
                    />
                  ) : null}
                  {edge.ref.type !== "external" && (edge.ref as ExtendedRef).title ? (
                    <span className="edge-title">{(edge.ref as ExtendedRef).title}</span>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="panel" aria-label="Evidence">
          <h2>Evidence</h2>
          <EvidenceLine record={current} now={now} />
        </section>

        {current.ref.type === "run" || current.ref.type === "job" ? (
          <section className="panel log-panel" aria-label="Log">
            <h2>Log</h2>
            {target ? (
              <LogTail file={file.data} loading={file.loading} error={file.error} />
            ) : (
              <p className="quiet">No log attached to this record.</p>
            )}
          </section>
        ) : null}

        {usage ? <UsageDetails usage={usage} /> : null}

        <details className="detail-details">
          <summary>Version history</summary>
          <ul className="history-list">
            {data.history.map((entry) => (
              <li key={`${entry.seq}/${entry.byte_offset}`}>
                <span className="mono">#{entry.seq}</span>
                <span title={formatAbsolute(entry.updated_at)}>
                  {formatAbsolute(entry.updated_at)}
                </span>
                <span>{wordsFor(entry.state)}</span>
                <span className="quiet">position {entry.byte_offset}</span>
              </li>
            ))}
          </ul>
        </details>

        {current.links.length > 0 ? (
          <details className="detail-details">
            <summary>Links</summary>
            <ul className="link-list">
              {current.links.map((link, index) => (
                <li key={`${link.label}/${index}`}>
                  <span className="link-label">{link.label}</span>
                  {link.url ? (
                    <a href={link.url} target="_blank" rel="noreferrer noopener">
                      {link.url}
                    </a>
                  ) : (
                    <span className="mono">{link.path}</span>
                  )}
                  {link.path && link.readable === false ? (
                    <span className="quiet">not readable</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </details>
        ) : null}

        <details className="detail-details">
          <summary>Raw fields (redacted)</summary>
          <pre>{JSON.stringify(data.full, null, 2)}</pre>
        </details>
      </div>
    </main>
  );
}

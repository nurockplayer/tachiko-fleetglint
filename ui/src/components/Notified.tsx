import { Fragment, type ReactNode } from "react";
import type { Board, BoardInboxItem } from "../api/types";
import { formatAgo } from "../format";
import { detailHref } from "../router";
import { refKey } from "./Refs";
import { Section } from "./Section";

function itemHref(item: BoardInboxItem): string | null {
  const subject = item.subject;
  if (subject.type === "external") return subject.url ?? null;
  return detailHref(subject);
}

function withoutPrefix(value: string, prefix: string): string {
  return value.startsWith(prefix) ? value.slice(prefix.length) : value;
}

/** The sender from the subject key: never the viewer's own role or a `from:` prefix. */
function senderOf(item: BoardInboxItem): string | null {
  const subject = item.subject;
  if (subject.type !== "external" || !subject.key) return null;
  return withoutPrefix(subject.key, "from:") || null;
}

function metaParts(item: BoardInboxItem): Array<{ key: string; node: ReactNode }> {
  const parts: Array<{ key: string; node: ReactNode }> = [];
  const sender = senderOf(item);
  if (sender) parts.push({ key: "sender", node: sender });
  const key = withoutPrefix(item.ref.id, "owner-notify.");
  if (key) parts.push({ key: "key", node: key });
  const age = formatAgo(item.age_s);
  if (age) parts.push({ key: "age", node: age });
  if (item.outcome === "failed") {
    parts.push({
      key: "outcome",
      node: <span className="notified-failed">delivery failed</span>,
    });
  }
  return parts;
}

function NotifiedItem({ item }: { item: BoardInboxItem }) {
  const message = item.detail ?? item.title ?? refKey(item.subject);
  const href = itemHref(item);
  const external = item.subject.type === "external";
  const parts = metaParts(item);

  const body = (
    <div className="notified-body">
      <span className="notified-message" title={message}>
        {message}
      </span>
      {parts.length > 0 ? (
        <span className="notified-meta">
          {parts.map((part, index) => (
            <Fragment key={part.key}>
              {index > 0 ? <span className="notified-sep"> · </span> : null}
              <span>{part.node}</span>
            </Fragment>
          ))}
        </span>
      ) : null}
    </div>
  );

  if (!href) {
    return <li className="notified-item">{body}</li>;
  }
  return (
    <li className="notified-item">
      <a
        href={href}
        {...(external ? { target: "_blank", rel: "noreferrer noopener" } : {})}
      >
        {body}
      </a>
    </li>
  );
}

/** What the viewer was notified about in the window; never an open/ack state. */
export function Notified({ board }: { board: Board }) {
  const hours = board.window_hours;
  return (
    <Section
      id="notified"
      heading="You were notified"
      aside={`last ${hours} ${hours === 1 ? "hour" : "hours"}`}
      ariaLabel="You were notified"
    >
      {board.needs_you.length === 0 ? (
        <p className="quiet">
          Nothing notified you in the last {hours} {hours === 1 ? "hour" : "hours"}.
        </p>
      ) : (
        <ul className="notified-list">
          {board.needs_you.map((item) => (
            <NotifiedItem key={`${item.ref.source_id}/${item.ref.id}`} item={item} />
          ))}
        </ul>
      )}
    </Section>
  );
}

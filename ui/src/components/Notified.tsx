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

function NotifiedItem({ item }: { item: BoardInboxItem }) {
  const message = item.detail ?? item.title ?? refKey(item.subject);
  const href = itemHref(item);
  const external = item.subject.type === "external";
  const body = (
    <>
      <span className="notified-message" title={message}>
        {message}
      </span>
      <span className="notified-meta">
        <span>{item.role_id}</span>
        <span className="notified-sep"> · </span>
        <span className="mono">{refKey(item.subject)}</span>
        <span className="notified-sep"> · </span>
        <span>{formatAgo(item.age_s)}</span>
      </span>
    </>
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

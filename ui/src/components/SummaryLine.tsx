import { Fragment, type ReactElement } from "react";
import type { Board } from "../api/types";

function CountLink({
  href,
  count,
  noun,
  onOpen,
}: {
  href: string;
  count: number;
  noun: string;
  onOpen?: (href: string) => void;
}) {
  return (
    <a href={href} onClick={onOpen ? () => onOpen(href) : undefined}>
      {count} {noun}
    </a>
  );
}

/**
 * One line of numbers, never tiles. Zero
 * counts stay in the line. When execution cannot be observed, it says so
 * instead of showing zero (visual spec §5).
 */
export function SummaryLine({
  board,
  onOpenSection,
}: {
  board: Board;
  /** Expands a collapsed section when its summary link is followed. */
  onOpenSection?: (href: string) => void;
}) {
  const { counts, capabilities } = board;

  if (!capabilities.execution) {
    const parts: Array<ReactElement> = [];
    if (counts.needs_you > 0) {
      parts.push(<CountLink key="notified" href="#notified" onOpen={onOpenSection} count={counts.needs_you} noun="notified" />);
    }
    parts.push(<span key="waiting">waiting: not observable</span>);
    parts.push(<span key="running">running: not observable</span>);
    if (capabilities.requests) {
      parts.push(<CountLink key="lead-inbox" href="#lead-inbox" onOpen={onOpenSection} count={counts.lead_inbox_open} noun="lead inbox" />);
    }
    return (
      <p className="summary-line">
        {parts.map((part, index) => (
          <Fragment key={index}>
            {index > 0 ? <span className="summary-dot"> · </span> : null}
            {part}
          </Fragment>
        ))}
      </p>
    );
  }

  const exceptions =
    counts.process_gone + counts.out_of_date + counts.unverified_recent;

  const parts: Array<ReactElement> = [
    <span key="notified">{counts.needs_you} notified</span>,
    <span key="waiting">{counts.waiting} waiting</span>,
    <span key="running">{counts.running} running</span>,
  ];
  if (counts.queued > 0) {
    parts.push(<span key="queued">{counts.queued} queued</span>);
  }
  parts.push(
    <span key="lead-inbox">{counts.lead_inbox_open} lead inbox</span>,
    <span key="exceptions">{exceptions} {exceptions === 1 ? "exception" : "exceptions"}</span>,
  );

  return (
    <p className="summary-line">
      {parts.map((part, index) => (
        <Fragment key={index}>
          {index > 0 ? <span className="summary-dot"> · </span> : null}
          {part}
        </Fragment>
      ))}
    </p>
  );
}

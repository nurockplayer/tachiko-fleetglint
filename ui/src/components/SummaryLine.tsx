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
 * One line of numbers, never tiles. Every count links to its section; zero
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
    <CountLink key="notified" href="#notified" onOpen={onOpenSection} count={counts.needs_you} noun="notified" />,
    <CountLink key="waiting" href="#waiting" onOpen={onOpenSection} count={counts.waiting} noun="waiting" />,
    <CountLink key="running" href="#running" onOpen={onOpenSection} count={counts.running} noun="running" />,
  ];
  if (counts.queued > 0) {
    parts.push(<CountLink key="queued" href="#queued" onOpen={onOpenSection} count={counts.queued} noun="queued" />);
  }
  parts.push(
    <CountLink key="lead-inbox" href="#lead-inbox" onOpen={onOpenSection} count={counts.lead_inbox_open} noun="lead inbox" />,
    <CountLink key="exceptions" href="#exceptions" onOpen={onOpenSection} count={exceptions} noun="exceptions" />,
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

import { Fragment, type ReactElement } from "react";
import type { Board } from "../api/types";

function CountLink({
  href,
  count,
  noun,
}: {
  href: string;
  count: number;
  noun: string;
}) {
  return (
    <a href={href}>
      {count} {noun}
    </a>
  );
}

/**
 * One line of numbers, never tiles. Every count links to its section; zero
 * counts stay in the line. When execution cannot be observed, it says so
 * instead of showing zero (visual spec §5).
 */
export function SummaryLine({ board }: { board: Board }) {
  const { counts, capabilities } = board;

  if (!capabilities.execution) {
    const parts: Array<ReactElement> = [];
    if (counts.needs_you > 0) {
      parts.push(<CountLink key="notified" href="#notified" count={counts.needs_you} noun="notified" />);
    }
    parts.push(<span key="waiting">waiting: not observable</span>);
    parts.push(<span key="running">running: not observable</span>);
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
    <CountLink key="notified" href="#notified" count={counts.needs_you} noun="notified" />,
    <CountLink key="waiting" href="#waiting" count={counts.waiting} noun="waiting" />,
    <CountLink key="running" href="#running" count={counts.running} noun="running" />,
  ];
  if (counts.queued > 0) {
    parts.push(<CountLink key="queued" href="#queued" count={counts.queued} noun="queued" />);
  }
  parts.push(
    <CountLink key="lead-inbox" href="#lead-inbox" count={counts.lead_inbox_open} noun="lead inbox" />,
    <CountLink key="exceptions" href="#exceptions" count={exceptions} noun="exceptions" />,
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

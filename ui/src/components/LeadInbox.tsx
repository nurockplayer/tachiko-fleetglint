import type { Board, BoardInboxItem } from "../api/types";
import { formatAgo, formatOverThreshold } from "../format";
import { refKey } from "./Refs";
import { CollapsibleSection } from "./Section";

function inboxMessage(item: BoardInboxItem): string {
  return item.detail ?? item.title ?? refKey(item.subject);
}

function InboxLine({
  item,
  oldAfterS,
}: {
  item: BoardInboxItem;
  oldAfterS: number;
}) {
  const old = item.age_s != null && item.age_s > oldAfterS;
  return (
    <li className={`inbox-line${old ? " is-old" : ""}`}>
      <span className="inbox-message">{inboxMessage(item)}</span>
      <span className="inbox-meta">
        <span className="mono">{refKey(item.subject)}</span>
        <span> · </span>
        <span>{formatAgo(item.age_s)}</span>
        {old ? <span> · {formatOverThreshold(oldAfterS)}</span> : null}
      </span>
    </li>
  );
}

export interface LeadInboxProps {
  board: Board;
  open: boolean;
  onToggle: () => void;
}

/**
 * Addressed to AI leads, not the viewer: quieter than notifications, never
 * amber, and old items say how old rather than asking for anything.
 */
export function LeadInbox({ board, open, onToggle }: LeadInboxProps) {
  const { counts, lead_inbox: roles, inbox_old_after_s: oldAfterS } = board;
  const summary = (
    <>
      {counts.lead_inbox_open} open
      {counts.lead_inbox_old > 0
        ? ` · ${counts.lead_inbox_old} waiting ${formatOverThreshold(oldAfterS)}`
        : null}
    </>
  );

  return (
    <CollapsibleSection
      id="lead-inbox"
      heading="Lead inbox"
      summary={summary}
      open={open}
      onToggle={onToggle}
      ariaLabel="Lead inbox"
      subline={
        roles.length > 0 ? (
          <span className="role-counts">
            {roles.map((role, index) => (
              <span key={role.role_id}>
                {index > 0 ? <span className="role-count-sep"> · </span> : null}
                <span className="role-count">
                  {role.role_id} {role.open}
                </span>
              </span>
            ))}
            {board.truncated.lead_inbox ? (
              <span className="truncation-note"> · showing the newest messages</span>
            ) : null}
          </span>
        ) : null
      }
    >
      {roles.length === 0 ? (
        <p className="quiet">Nothing in the lead inbox.</p>
      ) : (
        roles.map((role) => (
          <div className="inbox-role-group" key={role.role_id}>
            <h3 className="group-heading">
              {role.role_id}
              <span className="group-count">{role.open}</span>
            </h3>
            <ul className="inbox-lines">
              {role.items.map((item) => (
                <InboxLine
                  key={`${item.ref.source_id}/${item.ref.id}`}
                  item={item}
                  oldAfterS={oldAfterS}
                />
              ))}
            </ul>
          </div>
        ))
      )}
    </CollapsibleSection>
  );
}

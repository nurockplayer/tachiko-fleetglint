import type { DisplayState } from "./api/types";

/**
 * Every badge the UI can draw: the API display states plus the notification
 * tone (the board's `needs_you` list is not a record display state).
 */
export type BadgeState = DisplayState | "needs";

/** Words from visual spec §7; never the API's `lost`, `stale` or `unknown`. */
export const STATE_LABEL: Record<BadgeState, string> = {
  queued: "queued",
  running: "running",
  waiting: "waiting",
  done: "done",
  failed: "failed",
  cancelled: "cancelled",
  stale: "out of date",
  lost: "process gone",
  unknown: "unverified",
  open: "notified",
  acked: "seen",
  recent: "recent",
  idle: "idle",
  ended: "ended",
  needs: "notified",
};

/** Glyphs from visual spec §2. */
export const STATE_GLYPH: Record<BadgeState, string> = {
  queued: "ring",
  running: "dot",
  waiting: "hourglass",
  done: "check",
  failed: "cross",
  cancelled: "slash",
  stale: "dashed-circle",
  lost: "broken-link",
  unknown: "question",
  open: "open-dot",
  acked: "acked-dot",
  recent: "clock",
  idle: "crescent",
  ended: "square",
  needs: "bang",
};

export const TERMINAL_DISPLAY: ReadonlySet<DisplayState> = new Set([
  "done",
  "failed",
  "cancelled",
  "ended",
]);

export function isTerminal(state: DisplayState): boolean {
  return TERMINAL_DISPLAY.has(state);
}

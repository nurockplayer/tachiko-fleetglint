import type { DisplayState } from "./api/types";

/** Every badge variant: the API display states plus the inbox attention tone. */
export type BadgeState = DisplayState | "attention";

export const STATE_LABEL: Record<BadgeState, string> = {
  queued: "queued",
  running: "running",
  waiting: "waiting",
  done: "done",
  failed: "failed",
  cancelled: "cancelled",
  stale: "stale",
  lost: "lost",
  unknown: "unknown",
  attention: "action",
  open: "open",
  acked: "acked",
  recent: "recent",
  idle: "idle",
  ended: "ended",
};

/** Glyph kind per badge state (brief §3; Figma token `kind`). */
export const STATE_GLYPH: Record<BadgeState, string> = {
  queued: "ring",
  running: "dot",
  waiting: "arrow",
  done: "check",
  failed: "cross",
  cancelled: "slash",
  stale: "dashed-ring",
  lost: "broken-link",
  unknown: "question",
  attention: "bang",
  open: "open-dot",
  acked: "acked-dot",
  recent: "clock",
  idle: "crescent",
  ended: "square",
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

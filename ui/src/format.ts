/** "1 run", "2 runs"; a cut list ("1+") stays plural. */
export function countNoun(count: number, noun: string, more = false): string {
  return `${count}${more ? "+" : ""} ${noun}${count === 1 && !more ? "" : "s"}`;
}

/**
 * Relative ages per visual spec §7: seconds under a minute, minutes under an
 * hour, `1h 4m` under a day, then days. A missing value is left out, never a
 * dash.
 */
export function formatAge(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) {
    const rest = m % 60;
    return rest === 0 ? `${h}h` : `${h}h ${rest}m`;
  }
  return `${Math.floor(h / 24)}d`;
}

/** `18m ago`, or an empty string when the age is unknown. */
export function formatAgo(seconds: number | null | undefined): string {
  const age = formatAge(seconds);
  return age ? `${age} ago` : "";
}

/** `over 4 h`, from a threshold in seconds (the board's `inbox_old_after_s`). */
export function formatOverThreshold(seconds: number): string {
  if (seconds < 3600) return `over ${Math.round(seconds / 60)} min`;
  return `over ${Math.floor(seconds / 3600)} h`;
}

export function ageSince(iso: string | null, now: number = Date.now()): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.max(0, (now - t) / 1000);
}

// dateStyle/timeStyle cannot be combined with timeZoneName (TypeError), so spell the fields out.
const absoluteFormat = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  timeZoneName: "short",
});

const clockFormat = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** Absolute local time including its zone, e.g. for a title/tooltip. */
export function formatAbsolute(iso: string | null): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  return absoluteFormat.format(new Date(t));
}

/** Local clock time including its zone, e.g. "03:40 JST". */
export function formatClock(iso: string | null): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  return `${clockFormat.format(new Date(t))} ${zoneLabel(t)}`;
}

function zoneLabel(t: number): string {
  const parts = new Intl.DateTimeFormat("en-US", { timeZoneName: "short" }).formatToParts(
    new Date(t),
  );
  return parts.find((part) => part.type === "timeZoneName")?.value ?? "";
}

/** Just the local time, for the unavailable banner. */
export function formatTimeOfDay(iso: string | null): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  return clockFormat.format(new Date(t));
}

export function formatNumber(n: number | null | undefined): string {
  return n == null ? "" : n.toLocaleString("en-US");
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MiB`;
}

export function formatCost(cost: { amount: number; currency: string }): string {
  return `${cost.amount.toFixed(2)} ${cost.currency}`;
}

const SOURCE_NAMES: Record<string, string> = {
  "claude-code": "Claude Code",
  "codex-cli": "Codex CLI",
  "tachiko-harness": "Tachiko Harness",
  demo: "Demo",
};

/**
 * Friendly source name: the part before `@`, mapped for the known adapters.
 * The full `source_id` belongs in a `title` attribute, never in the top bar.
 */
export function sourceName(sourceId: string): string {
  const name = sourceId.split("@")[0] ?? sourceId;
  return SOURCE_NAMES[name] ?? name;
}

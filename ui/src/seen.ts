import type { BoardInboxItem, BoardWork } from "./api/types";

type Item = BoardWork | BoardInboxItem;
export type Mark = (item: Item) => "new" | "changed" | null;
const STORAGE_KEY = "fleetglint.seen.v1";
const LIMIT = 2000;

export function key(item: Item): string {
  return `${item.ref.source_id}|${item.ref.type}|${item.ref.id}`;
}

export function fingerprint(item: Item): string {
  return JSON.stringify([item.state, item.display_state, item.title,
    ("detail" in item ? item.detail : item.section_reason) ?? null,
    "role_id" in item ? item.role_id ?? null : null,
    "command_summary" in item ? item.command_summary ?? null : null]);
}

/** One frozen baseline per visit; saving a poll never changes its markers. */
export function createSeen(): { mark: Mark; save: () => void } {
  let baseline: Map<string, string> | null = null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw !== null) {
      const stored = JSON.parse(raw);
      if (typeof stored.saved_at === "string" && stored.items &&
          typeof stored.items === "object" && !Array.isArray(stored.items) &&
          Object.values(stored.items).every(value => typeof value === "string")) {
        baseline = new Map(Object.entries(stored.items));
      }
    }
  } catch { /* Unavailable storage is a first visit. */ }

  const running = new Map(baseline ?? []);
  const rendered = new Map<string, string>();

  return {
    mark(item) {
      const k = key(item);
      const fp = fingerprint(item);
      rendered.set(k, fp);
      if (baseline === null) return null;
      const previous = baseline.get(k);
      return previous === undefined ? "new" : previous !== fp ? "changed" : null;
    },
    save() {
      try {
        for (const [k, fp] of rendered) {
          if (!running.has(k) || running.get(k) !== fp) running.set(k, fp);
        }
        rendered.clear();
        while (running.size > LIMIT) running.delete(running.keys().next().value!);
        localStorage.setItem(STORAGE_KEY, JSON.stringify({
          saved_at: new Date().toISOString(), items: Object.fromEntries(running),
        }));
      } catch { /* Storage must never interrupt the board. */ }
    },
  };
}

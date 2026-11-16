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
    ("detail" in item ? item.detail : item.section_reason) ?? null]);
}

/** One frozen baseline per visit; saving a poll never changes its markers. */
export function createSeen(): { mark: Mark; save: (items: Item[]) => void } {
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

  return {
    mark(item) {
      if (baseline === null) return null;
      const previous = baseline.get(key(item));
      return previous === undefined ? "new" : previous !== fingerprint(item) ? "changed" : null;
    },
    save(items) {
      try {
        const merged = new Map(baseline);
        for (const item of items) merged.set(key(item), fingerprint(item));
        const entries = [...merged].slice(-LIMIT);
        localStorage.setItem(STORAGE_KEY, JSON.stringify({
          saved_at: new Date().toISOString(), items: Object.fromEntries(entries),
        }));
      } catch { /* Storage must never interrupt the board. */ }
    },
  };
}

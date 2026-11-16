import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { board } from "./fixtures/board";
import { createSeen, fingerprint, key } from "./seen";
import { createElement } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { App } from "./App";

const storageKey = "fleetglint.seen.v1";
const item = board.lead_inbox[0].items[0];
const other = { ...item, ref: { ...item.ref, id: "another-ask" } };
const stored = () => JSON.parse(localStorage.getItem(storageKey)!);

beforeEach(() => localStorage.clear());
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("seen visit", () => {
  it("wires successful board polls through overview and project screens", async () => {
    createSeen().save([]);
    const pageBoard = { ...board, projects: [{ ...board.projects[1], needs_you: [item] }] };
    const fetcher = vi.fn(async () => new Response(JSON.stringify(pageBoard)));
    window.history.replaceState(null, "", "/");
    const { unmount } = render(createElement(App, { fetcher, pollMs: 10 }));
    expect(await screen.findByText("new")).toBeTruthy();
    await waitFor(() => expect(fetcher.mock.calls.length).toBeGreaterThanOrEqual(2));
    expect(screen.getByText("new")).toBeTruthy();
    expect(stored().items[key(item)]).toBe(fingerprint(item));
    unmount();
    window.history.replaceState(null, "", "/project?name=fleetglint");
    render(createElement(App, { fetcher, pollMs: 100000 }));
    expect(await screen.findByRole("heading", { name: "fleetglint" })).toBeTruthy();
    expect(screen.queryByText("new")).toBeNull();
    window.history.replaceState(null, "", "/");
  });
  it("has no markers throughout the first visit and saves a zoned timestamp", () => {
    const seen = createSeen();
    seen.save([item]);
    expect(seen.mark(item)).toBeNull();
    seen.save([item, other]);
    expect(seen.mark(other)).toBeNull();
    expect(stored().saved_at).toMatch(/Z$/);
    expect(stored().items[key(item)]).toBe(fingerprint(item));
  });
  it("marks new and changed asks after a reload, preserving the baseline across two polls", () => {
    createSeen().save([item]);
    const seen = createSeen();
    const changed = { ...item, detail: "A different ask" };
    expect(seen.mark(item)).toBeNull();
    seen.save([changed, other]);
    expect(seen.mark(changed)).toBe("changed");
    expect(seen.mark(other)).toBe("new");
    seen.save([changed, other]);
    expect(seen.mark(changed)).toBe("changed");
    expect(seen.mark(other)).toBe("new");
    const nextVisit = createSeen();
    expect(nextVisit.mark(changed)).toBeNull();
    expect(nextVisit.mark(other)).toBeNull();
  });
  it.each(["state", "display_state", "title", "detail"] as const)("detects changed %s", field => {
    createSeen().save([item]);
    expect(createSeen().mark({ ...item, [field]: "different" })).toBe("changed");
  });
  it("ignores timestamps, age and repeat count, including for run items", () => {
    const run = board.projects[1].in_progress[0];
    createSeen().save([item, run]);
    const seen = createSeen();
    expect(seen.mark({ ...item, created_at: "2026-11-16T01:00:00Z", age_s: 9999,
      updated_at: "2026-11-16T01:00:00Z", observed_at: "2026-11-16T01:00:00Z" })).toBeNull();
    expect(seen.mark({ ...run, started_age_s: 9999, repeat_count: 99 })).toBeNull();
    expect(seen.mark({ ...run, section_reason: "A different reason" })).toBe("changed");
  });
  it("keeps baseline items missing from the current poll", () => {
    createSeen().save([item]);
    createSeen().save([other]);
    expect(Object.keys(stored().items)).toEqual([key(item), key(other)]);
  });
  it.each(["{broken", "null", "{}", '{"saved_at":"now","items":[]}'])("treats broken storage as a first visit: %s", raw => {
    localStorage.setItem(storageKey, raw);
    const seen = createSeen();
    expect(seen.mark(item)).toBeNull();
    expect(() => seen.save([item])).not.toThrow();
  });
  it("does not crash when localStorage access or writes throw", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
    expect(() => createSeen().save([item])).not.toThrow();
    vi.stubGlobal("localStorage", { getItem() { throw new Error("blocked"); } });
    const seen = createSeen();
    expect(seen.mark(item)).toBeNull();
    expect(() => seen.save([item])).not.toThrow();
  });
  it("caps at 2000 entries by oldest insertion, without moving updated entries", () => {
    const items = Array.from({ length: 2000 }, (_, n) => ({ ...item, ref: { ...item.ref, id: String(n) } }));
    createSeen().save(items);
    createSeen().save([{ ...items[0], detail: "updated" }, other]);
    const entries = Object.keys(stored().items);
    expect(entries).toHaveLength(2000);
    expect(entries).not.toContain(key(items[0]));
    expect(entries[0]).toBe(key(items[1]));
    expect(entries.at(-1)).toBe(key(other));
  });
});

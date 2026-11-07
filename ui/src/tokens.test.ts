import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/*
 * Keeps docs/design/visual-spec.md §2 true: parses ui/src/tokens.css and
 * checks the WCAG contrast of every pair the spec lists under "Computed".
 */

const TOKENS_CSS = join(dirname(fileURLToPath(import.meta.url)), "tokens.css");
const CSS = readFileSync(TOKENS_CSS, "utf8");

function blockFrom(text: string, marker: string): string {
  const start = text.indexOf(marker);
  if (start < 0) throw new Error(`missing ${marker}`);
  const open = text.indexOf("{", start);
  const close = text.indexOf("}", open);
  if (open < 0 || close < 0) throw new Error(`unterminated ${marker}`);
  return text.slice(open + 1, close);
}

function parseTokens(block: string): Record<string, string> {
  const tokens: Record<string, string> = {};
  for (const match of block.matchAll(/--([a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    tokens[match[1]] = match[2].trim();
  }
  return tokens;
}

const LIGHT = parseTokens(blockFrom(CSS, ":root"));
const DARK_MARKER = "@media (prefers-color-scheme: dark)";
const DARK = { ...LIGHT, ...parseTokens(blockFrom(CSS, DARK_MARKER)) };

const THEMES: Array<[string, Record<string, string>]> = [
  ["light", LIGHT],
  ["dark", DARK],
];

const TEXT_TOKENS = [
  "text-primary",
  "text-secondary",
  "text-meta",
  "text-mono-data",
  "text-link",
];

const STATE_TOKENS = [
  "needs",
  "running",
  "waiting",
  "failed",
  "gone",
  "stale",
  "unverified",
  "done",
  "recent",
  "idle",
];

const SURFACES = ["surface-canvas", "surface-panel", "surface-raised"];

const REQUIRED = [
  ...SURFACES,
  "surface-chrome",
  "surface-row-hover",
  ...TEXT_TOKENS,
  "line-divider",
  "line-boundary",
  "line-focus",
  "line-unresolved",
  ...STATE_TOKENS.flatMap((state) => [
    `state-${state}-fg`,
    `state-${state}-bg`,
    `state-${state}-border`,
  ]),
  "font-ui",
  "font-mono",
  "radius-panel",
  "radius-small",
  "content-max",
  "row-height",
  "row-height-two-line",
  "topbar-height",
];

function channels(hex: string): [number, number, number] {
  const value = hex.trim().replace("#", "");
  if (!/^[0-9a-f]{6}$/i.test(value)) throw new Error(`not a hex colour: ${hex}`);
  return [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16) / 255) as [
    number,
    number,
    number,
  ];
}

function luminance(hex: string): number {
  const [r, g, b] = channels(hex).map((c) =>
    c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

function token(theme: Record<string, string>, name: string): string {
  const value = theme[name];
  if (!value) throw new Error(`missing token --${name}`);
  return value;
}

describe("tokens.css", () => {
  it("defines every token in both themes", () => {
    for (const [name, theme] of THEMES) {
      for (const required of REQUIRED) {
        expect(theme[required], `${name} --${required}`).toBeTruthy();
      }
    }
  });

  it("sets color-scheme and keeps dark under the system preference", () => {
    expect(CSS).toMatch(/color-scheme:\s*light dark/);
    expect(CSS).toContain(DARK_MARKER);
  });

  it.each(THEMES)("%s: text is at least 4.5:1 on every surface", (name, theme) => {
    for (const text of TEXT_TOKENS) {
      for (const surface of SURFACES) {
        const ratio = contrast(token(theme, text), token(theme, surface));
        expect(ratio, `${name}: --${text} on --${surface}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it.each(THEMES)("%s: state foregrounds are at least 4.5:1 on every surface", (name, theme) => {
    for (const state of STATE_TOKENS) {
      for (const surface of SURFACES) {
        const ratio = contrast(
          token(theme, `state-${state}-fg`),
          token(theme, surface),
        );
        expect(
          ratio,
          `${name}: --state-${state}-fg on --${surface}`,
        ).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it.each(THEMES)("%s: state foregrounds are at least 4.5:1 on their own background", (name, theme) => {
    for (const state of STATE_TOKENS) {
      const ratio = contrast(
        token(theme, `state-${state}-fg`),
        token(theme, `state-${state}-bg`),
      );
      expect(ratio, `${name}: --state-${state}-fg on its background`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it.each(THEMES)("%s: state borders are at least 3:1 on background and panel", (name, theme) => {
    for (const state of STATE_TOKENS) {
      for (const surface of [`state-${state}-bg`, "surface-panel"]) {
        const ratio = contrast(
          token(theme, `state-${state}-border`),
          token(theme, surface),
        );
        expect(
          ratio,
          `${name}: --state-${state}-border on --${surface}`,
        ).toBeGreaterThanOrEqual(3);
      }
    }
  });
});

#!/usr/bin/env node
/*
 * WCAG 2.1 AA contrast check for the Fleetglint design tokens.
 *
 * It reads the TOKENS object out of code.js (the single source of truth),
 * resolves semantic aliases to primitive hex values, and fails if
 *   - any state badge text is below 4.5:1 against its badge background,
 *   - any state glyph or border is below 3:1 against its badge background,
 *   - any text role is below 4.5:1 against any surface,
 *   - any provenance label is below 4.5:1.
 *
 * Run: orb-test --memory 1g --cpus 1 -- node design/figma-plugin/contrast-check.mjs
 */

import { readFileSync } from "node:fs";

const MIN_TEXT = 4.5;
const MIN_GLYPH = 3;

const source = readFileSync(new URL("./code.js", import.meta.url), "utf8");
const marker = source.match(/\/\/ TOKENS-START([\s\S]*?)\/\/ TOKENS-END/);
if (!marker) {
  console.error("contrast-check: TOKENS markers not found in code.js");
  process.exit(2);
}
const objectMatch = marker[1].match(/const TOKENS = (\{[\s\S]*\});/);
if (!objectMatch) {
  console.error("contrast-check: TOKENS object not found between the markers");
  process.exit(2);
}

let TOKENS;
try {
  TOKENS = new Function("return (" + objectMatch[1] + ");")();
} catch (err) {
  console.error("contrast-check: could not evaluate TOKENS: " + err.message);
  process.exit(2);
}

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16) / 255,
    parseInt(h.slice(2, 4), 16) / 255,
    parseInt(h.slice(4, 6), 16) / 255,
  ];
}

function linear(v) {
  return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}

function luminance(hex) {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

function contrast(a, b) {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

function resolve(color) {
  if (typeof color !== "string") return color;
  if (color.startsWith("color/")) return TOKENS.primitives.color[color.slice(6)];
  return color;
}

const failures = [];
const states = TOKENS.semantic.state;
const stateRows = [];

for (const [key, cfg] of Object.entries(states)) {
  const fg = resolve(cfg.fg);
  const bg = resolve(cfg.bg);
  const border = resolve(cfg.border);
  const textRatio = contrast(fg, bg);
  const borderRatio = contrast(border, bg);
  stateRows.push({ key, cfg, fg, bg, border, textRatio, borderRatio });
  if (textRatio < MIN_TEXT) {
    failures.push(
      `state ${key}: text ${fg} on ${bg} is ${textRatio.toFixed(2)}:1 (needs ${MIN_TEXT}:1)`
    );
  }
  if (borderRatio < MIN_GLYPH) {
    failures.push(
      `state ${key}: border ${border} on ${bg} is ${borderRatio.toFixed(2)}:1 (needs ${MIN_GLYPH}:1)`
    );
  }
}

const surfaces = TOKENS.semantic.surface;
const textRoles = TOKENS.semantic.text;
const textRows = [];
const EXEMPT_TEXT = new Set(["disabled"]);

for (const [role, value] of Object.entries(textRoles)) {
  const fg = resolve(value);
  let min = Infinity;
  let minSurface = "";
  for (const [surfaceName, surfaceValue] of Object.entries(surfaces)) {
    const bg = resolve(surfaceValue);
    const ratio = contrast(fg, bg);
    if (ratio < min) {
      min = ratio;
      minSurface = surfaceName;
    }
  }
  textRows.push({ role, fg, min, minSurface, exempt: EXEMPT_TEXT.has(role) });
  if (!EXEMPT_TEXT.has(role) && min < MIN_TEXT) {
    failures.push(
      `text ${role}: ${fg} on ${minSurface} is ${min.toFixed(2)}:1 (needs ${MIN_TEXT}:1)`
    );
  }
}

const provenance = TOKENS.semantic.provenance;
const provenanceRows = [];
const chipFg = resolve(provenance["source-chip-fg"]);
const chipBg = resolve(provenance["source-chip-bg"]);
const chipRatio = contrast(chipFg, chipBg);
provenanceRows.push({ label: "source-chip-fg on source-chip-bg", fg: chipFg, bg: chipBg, ratio: chipRatio });
if (chipRatio < MIN_TEXT) {
  failures.push(`provenance chip: ${chipFg} on ${chipBg} is ${chipRatio.toFixed(2)}:1 (needs ${MIN_TEXT}:1)`);
}
for (const age of ["age-fresh", "age-old"]) {
  const fg = resolve(provenance[age]);
  const bg = resolve(surfaces.panel);
  const ratio = contrast(fg, bg);
  provenanceRows.push({ label: `${age} on panel`, fg, bg, ratio });
  if (ratio < MIN_TEXT) {
    failures.push(`${age}: ${fg} on panel is ${ratio.toFixed(2)}:1 (needs ${MIN_TEXT}:1)`);
  }
}

const lines = TOKENS.semantic.line;
const lineRows = [];
for (const role of ["boundary", "focus", "relationship", "unresolved"]) {
  const fg = resolve(lines[role]);
  const bg = resolve(surfaces.panel);
  const ratio = contrast(fg, bg);
  lineRows.push({ role, fg, bg, ratio });
  if (ratio < MIN_GLYPH) {
    failures.push(`line ${role}: ${fg} on panel is ${ratio.toFixed(2)}:1 (needs ${MIN_GLYPH}:1)`);
  }
}

const out = [];
out.push("# Fleetglint contrast check (WCAG 2.1 AA)");
out.push("");
out.push(`States: ${stateRows.length} · text roles: ${textRows.length} · surfaces: ${Object.keys(surfaces).length}`);
out.push("");
out.push("## State legend");
out.push("");
out.push("| display state | glyph | fg | bg | text | border |");
out.push("|---|---|---|---|---|---|");
for (const row of stateRows) {
  out.push(
    `| \`${row.key}\` | ${row.cfg.glyph} | ${row.fg} | ${row.bg} | ${row.textRatio.toFixed(2)}:1 | ${row.borderRatio.toFixed(2)}:1 |`
  );
}
out.push("");
out.push("## Text roles (worst surface)");
out.push("");
out.push("| role | fg | worst surface | ratio |");
out.push("|---|---|---|---|");
for (const row of textRows) {
  const note = row.exempt ? " (disabled text, exempt)" : "";
  out.push(`| \`${row.role}\`${note} | ${row.fg} | ${row.minSurface} | ${row.min.toFixed(2)}:1 |`);
}
out.push("");
out.push("## Provenance");
out.push("");
out.push("| pair | fg | bg | ratio |");
out.push("|---|---|---|---|");
for (const row of provenanceRows) {
  out.push(`| ${row.label} | ${row.fg} | ${row.bg} | ${row.ratio.toFixed(2)}:1 |`);
}
out.push("");
out.push("## Lines (non-text boundaries)");
out.push("");
out.push("| role | fg | bg | ratio |");
out.push("|---|---|---|---|");
for (const row of lineRows) {
  out.push(`| \`${row.role}\` | ${row.fg} | ${row.bg} | ${row.ratio.toFixed(2)}:1 |`);
}
out.push("");
if (failures.length) {
  out.push(`FAIL: ${failures.length} contrast failure(s)`);
  for (const failure of failures) out.push(`- ${failure}`);
} else {
  out.push(
    `PASS: all ${stateRows.length} states (text >= ${MIN_TEXT}:1, border >= ${MIN_GLYPH}:1), all non-exempt text roles >= ${MIN_TEXT}:1, provenance labels >= ${MIN_TEXT}:1.`
  );
}
console.log(out.join("\n"));
process.exit(failures.length ? 1 : 0);

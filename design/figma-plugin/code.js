/*
 * Fleetglint design system builder (v0.1).
 *
 * A local Figma development plugin. It rebuilds the Fleetglint pages
 * (Foundations, Components, Screens) from the token object below and
 * updates its own variable collections (Primitives, Semantic) in place.
 * It never touches any other page, file or setting.
 *
 * Run from Figma: Plugins -> Development -> Fleetglint Design System.
 * See README.md and docs/design/figma.md.
 */

// TOKENS-START
const TOKENS = {
  primitives: {
    color: {
      "neutral/0": "#04060A",
      "neutral/50": "#080C11",
      "neutral/100": "#0D1218",
      "neutral/115": "#0F1620",
      "neutral/150": "#10151B",
      "neutral/200": "#111820",
      "neutral/250": "#131B24",
      "neutral/300": "#141A22",
      "neutral/350": "#17202A",
      "neutral/380": "#1A2430",
      "neutral/400": "#1A1D21",
      "neutral/450": "#1F2A36",
      "neutral/500": "#26333F",
      "neutral/600": "#2B3743",
      "neutral/650": "#3E4C5C",
      "neutral/700": "#4A5766",
      "neutral/750": "#5A6A80",
      "neutral/760": "#5C6B7D",
      "neutral/780": "#6B7480",
      "neutral/800": "#6E8199",
      "neutral/820": "#7A8798",
      "neutral/840": "#8593A5",
      "neutral/900": "#A8B0BA",
      "neutral/950": "#9FB0C4",
      "neutral/1000": "#B8C4D2",
      "neutral/1050": "#C9D6E4",
      "neutral/1100": "#E8EEF6",
      "accent/950": "#0C2C23",
      "accent/900": "#0A2A22",
      "accent/700": "#14795E",
      "accent/600": "#1FA37D",
      "accent/500": "#33D1A0",
      "accent/400": "#6BEBC0",
      "accent/300": "#A6F7DA",
      "green/900": "#0D2417",
      "green/700": "#2E7D4F",
      "green/500": "#62C98A",
      "green/400": "#8FE0AC",
      "amber/900": "#2B1F0A",
      "amber/700": "#8A5D14",
      "amber/500": "#D9A03F",
      "amber/400": "#F0C270",
      "red/900": "#2B1012",
      "red/650": "#C24A4A",
      "red/500": "#E86A6A",
      "red/400": "#FF8F8F",
      "violet/900": "#1D1330",
      "violet/600": "#8A5EC2",
      "violet/500": "#B37BE8",
      "violet/400": "#CDA2F5",
      "grey/900": "#161C23",
      "grey/750": "#5F6E7E",
      "grey/500": "#9AA6B5",
      "warm/900": "#1A1712",
      "warm/700": "#7A6E55",
      "warm/500": "#C7B89C",
      "orange/900": "#3A1A05",
      "orange/400": "#FF7A3D",
      "orange/200": "#FFD9A8",
      "blue/900": "#0E2233",
      "blue/400": "#8CC4FF"
    },
    space: { "2": 2, "4": 4, "8": 8, "12": 12, "16": 16, "24": 24, "32": 32, "48": 48 },
    radius: { "0": 0, "2": 2, "4": 4, "8": 8 },
    fontSize: { "12": 12, "13": 13, "16": 16, "20": 20, "28": 28 }
  },
  semantic: {
    surface: {
      canvas: "color/neutral/50",
      chrome: "color/neutral/100",
      panel: "color/neutral/200",
      raised: "color/neutral/350",
      overlay: "color/neutral/450",
      "row-hover": "color/neutral/250",
      "row-selected": "color/accent/950"
    },
    text: {
      primary: "color/neutral/1100",
      secondary: "color/neutral/1000",
      meta: "color/neutral/840",
      disabled: "color/neutral/760",
      "mono-data": "color/neutral/1050",
      link: "color/blue/400"
    },
    line: {
      divider: "color/neutral/600",
      boundary: "color/neutral/750",
      focus: "color/blue/400",
      relationship: "color/neutral/800",
      unresolved: "color/amber/500"
    },
    state: {
      queued: {
        label: "queued",
        glyph: "hollow ring",
        kind: "ring",
        fg: "color/neutral/840",
        bg: "color/neutral/115",
        border: "color/neutral/750"
      },
      running: {
        label: "running",
        glyph: "filled dot in ring",
        kind: "dot",
        fg: "color/accent/500",
        bg: "color/accent/900",
        border: "color/accent/600"
      },
      waiting: {
        label: "waiting",
        glyph: "arrow (waits on)",
        kind: "arrow",
        fg: "color/amber/400",
        bg: "color/amber/900",
        border: "color/amber/500"
      },
      done: {
        label: "done",
        glyph: "check",
        kind: "check",
        fg: "color/green/400",
        bg: "color/green/900",
        border: "color/green/700"
      },
      failed: {
        label: "failed",
        glyph: "cross",
        kind: "cross",
        fg: "color/red/400",
        bg: "color/red/900",
        border: "color/red/650"
      },
      cancelled: {
        label: "cancelled",
        glyph: "slash",
        kind: "slash",
        fg: "color/grey/500",
        bg: "color/grey/900",
        border: "color/grey/750"
      },
      stale: {
        label: "stale",
        glyph: "dashed ring",
        kind: "dashed-ring",
        fg: "color/warm/500",
        bg: "color/warm/900",
        border: "color/warm/700"
      },
      lost: {
        label: "lost",
        glyph: "broken link",
        kind: "broken-link",
        fg: "color/violet/400",
        bg: "color/violet/900",
        border: "color/violet/600"
      },
      unknown: {
        label: "unknown",
        glyph: "question on hatch",
        kind: "question",
        fg: "color/neutral/900",
        bg: "color/neutral/400",
        border: "color/neutral/780"
      },
      attention: {
        label: "action",
        glyph: "bar + exclamation",
        kind: "bang",
        fg: "color/orange/200",
        bg: "color/orange/900",
        border: "color/orange/400"
      },
      "inbox-open": {
        label: "open",
        glyph: "hollow dot",
        kind: "open-dot",
        fg: "color/neutral/1000",
        bg: "color/neutral/300",
        border: "color/neutral/750"
      },
      "inbox-acked": {
        label: "acked",
        glyph: "filled dot (muted)",
        kind: "acked-dot",
        fg: "color/neutral/820",
        bg: "color/neutral/150",
        border: "color/neutral/750"
      }
    },
    provenance: {
      "source-chip-bg": "color/neutral/380",
      "source-chip-fg": "color/neutral/950",
      "age-fresh": "color/neutral/840",
      "age-old": "color/amber/500"
    }
  },
  typography: {
    ui: { family: "Inter", row: 13, meta: 12, badge: 12, heading: 16, headingLg: 20 },
    mono: { family: "JetBrains Mono", data: 13, meta: 12, badge: 12, number: 28 }
  },
  motion: { fast: 120, base: 200, ambient: 1600 },
  geometry: {
    rowCompact: 28,
    rowDefault: 32,
    radiusChip: 4,
    radiusPanel: 8,
    chipHeight: 20,
    button: 32
  }
};
// TOKENS-END

const STATE_KEYS = Object.keys(TOKENS.semantic.state);
const PAGE_NAMES = ["Foundations", "Components", "Screens"];
const COLLECTION_PRIMITIVES = "Primitives";
const COLLECTION_SEMANTIC = "Semantic";
const BADGE_STATES = STATE_KEYS;
const BADGE_SIZE = ["sm", "md"];
const BADGE_AGE = ["none", "suffix"];

const PRIM = {};
const OWNER_KEY = "fleetglint";
const SEM = {};
const STYLES = {};
const COMPONENT_SETS = {};
const COMPONENTS = {};
const PAGES = {};
const warnings = [];

let FONTS = {};
let pagesCount = 0;
let currentStep = "start";
let currentItem = "";
let refusedFile = false;
const pendingTextStyles = [];

/* ---------------------------------------------------------------- colors */

function hexToRgba(hex) {
  const h = hex.replace("#", "");
  return {
    r: parseInt(h.slice(0, 2), 16) / 255,
    g: parseInt(h.slice(2, 4), 16) / 255,
    b: parseInt(h.slice(4, 6), 16) / 255,
    a: 1
  };
}

function channelToLinear(v) {
  return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}

function luminance(hex) {
  const c = hexToRgba(hex);
  return (
    0.2126 * channelToLinear(c.r) +
    0.7152 * channelToLinear(c.g) +
    0.0722 * channelToLinear(c.b)
  );
}

function contrastRatio(a, b) {
  const la = luminance(a);
  const lb = luminance(b);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

function stateColorVar(state, part) {
  return "state/" + state + "/" + part;
}

function resolveColorValue(value) {
  if (typeof value === "string" && value.indexOf("color/") === 0) {
    return TOKENS.primitives.color[value.slice("color/".length)];
  }
  return value;
}

function resolveHex(varName) {
  const parts = varName.split("/");
  if (parts[0] === "state") {
    return resolveColorValue(TOKENS.semantic.state[parts[1]][parts[2]]);
  }
  const group = TOKENS.semantic[parts[0]];
  if (group && group[parts[1]]) return resolveColorValue(group[parts[1]]);
  if (TOKENS.primitives.color[varName]) return TOKENS.primitives.color[varName];
  if (varName.indexOf("color/") === 0) {
    const prim = TOKENS.primitives.color[varName.slice("color/".length)];
    if (prim) return prim;
  }
  return "#FF00FF";
}

function paint(varName) {
  const v = SEM[varName] || PRIM[varName];
  const base = { type: "SOLID", color: hexToRgba(resolveHex(varName)) };
  if (v) {
    try {
      return figma.variables.setBoundVariableForPaint(base, "color", v);
    } catch (e) {
      return base;
    }
  }
  return base;
}

/* --------------------------------------------------------------- figma ui */

function makeFrame(name, opt) {
  const o = opt || {};
  const f = figma.createFrame();
  f.name = name;
  f.fills = o.fill ? [paint(o.fill)] : [];
  f.strokes = o.stroke ? [paint(o.stroke)] : [];
  if (o.stroke) f.strokeWeight = o.strokeWeight || 1;
  if (o.radius != null) f.cornerRadius = o.radius;
  f.clipsContent = !!o.clip;
  if (o.w != null && o.h != null) f.resize(o.w, o.h);
  if (o.layout) setAuto(f, o.layout, o);
  return f;
}

function setAuto(node, mode, opt) {
  const o = opt || {};
  node.layoutMode = mode;
  node.primaryAxisSizingMode = o.primary || "AUTO";
  node.counterAxisSizingMode = o.counter || "AUTO";
  node.itemSpacing = o.gap || 0;
  const padX = o.padX || 0;
  const padY = o.padY || 0;
  node.paddingLeft = padX;
  node.paddingRight = padX;
  node.paddingTop = padY;
  node.paddingBottom = padY;
  if (o.align) node.counterAxisAlignItems = o.align;
  if (o.justify) node.primaryAxisAlignItems = o.justify;
}

function makeText(content, styleName, fill, name) {
  const style = STYLES[styleName];
  const t = figma.createText();
  t.name = name || "text";
  if (style) {
    t.fontName = style.fontName;
    t.fontSize = style.fontSize;
    t.lineHeight = style.lineHeight;
    pendingTextStyles.push({ node: t, styleId: style.id });
  } else {
    t.fontName = FONTS.uiRegular;
    t.fontSize = 13;
  }
  t.characters = content;
  t.textAutoResize = "WIDTH_AND_HEIGHT";
  t.fills = fill ? [paint(fill)] : [paint("text/primary")];
  return t;
}

// Dynamic-page plugins must bind text styles with the async setter. Doing it
// once at the end keeps node creation synchronous and easy to read.
async function applyTextStyles() {
  for (let i = 0; i < pendingTextStyles.length; i++) {
    const entry = pendingTextStyles[i];
    try {
      await entry.node.setTextStyleIdAsync(entry.styleId);
    } catch (e) {
      warnings.push("could not bind text style: " + e.message);
    }
  }
}

function truncate(t) {
  try {
    t.textTruncation = "ENDING";
  } catch (e) {
    /* older API: leave wrapping off */
  }
}

function makeRect(w, h, opt) {
  const o = opt || {};
  const r = figma.createRectangle();
  r.resize(w, h);
  r.fills = o.fill ? [paint(o.fill)] : [];
  r.strokes = o.stroke ? [paint(o.stroke)] : [];
  if (o.stroke) r.strokeWeight = o.strokeWeight || 1;
  if (o.radius != null) r.cornerRadius = o.radius;
  if (o.dash) r.dashPattern = o.dash;
  return r;
}

function addEllipse(parent, x, y, w, h, opt) {
  const o = opt || {};
  const e = figma.createEllipse();
  e.resize(w, h);
  e.fills = o.fill ? [paint(o.fill)] : [];
  e.strokes = o.stroke ? [paint(o.stroke)] : [];
  if (o.stroke) e.strokeWeight = o.weight || 1;
  if (o.dash) e.dashPattern = o.dash;
  parent.appendChild(e);
  e.x = x;
  e.y = y;
  return e;
}

function addVector(parent, data, colorVar, weight) {
  const v = figma.createVector();
  v.vectorPaths = [{ windingRule: "NONE", data: data }];
  v.fills = [];
  v.strokes = [paint(colorVar)];
  v.strokeWeight = weight || 1.5;
  v.strokeCap = "ROUND";
  v.strokeJoin = "ROUND";
  parent.appendChild(v);
  v.x = 0;
  v.y = 0;
  return v;
}

function makeGlyph(kind, colorVar) {
  const size = 12;
  const g = figma.createFrame();
  g.name = "glyph";
  g.resize(size, size);
  g.fills = [];
  g.strokes = [];
  g.clipsContent = false;
  g.layoutMode = "NONE";

  if (kind === "ring") {
    addEllipse(g, 1.5, 1.5, size - 3, size - 3, { stroke: colorVar, weight: 1.5 });
  } else if (kind === "dot") {
    addEllipse(g, 1, 1, size - 2, size - 2, { stroke: colorVar, weight: 1 });
    addEllipse(g, 3.5, 3.5, size - 7, size - 7, { fill: colorVar });
  } else if (kind === "arrow") {
    addVector(g, "M 1 7 L 11 7 M 7 3 L 11 7 L 7 11", colorVar, 1.5);
  } else if (kind === "check") {
    addVector(g, "M 1 7 L 4.5 10.5 L 11 2.5", colorVar, 1.8);
  } else if (kind === "cross") {
    addVector(g, "M 2 2 L 10 10 M 10 2 L 2 10", colorVar, 1.8);
  } else if (kind === "slash") {
    addVector(g, "M 2 10 L 10 2", colorVar, 1.8);
  } else if (kind === "dashed-ring") {
    addEllipse(g, 1.5, 1.5, size - 3, size - 3, { stroke: colorVar, weight: 1.5, dash: [2, 2] });
  } else if (kind === "broken-link") {
    addVector(g, "M 1 8 L 4 11", colorVar, 1.6);
    addVector(g, "M 8 4 L 11 1", colorVar, 1.6);
  } else if (kind === "question") {
    const stripes = ["M 0 4 L 4 0", "M 0 9 L 9 0", "M 1 13 L 13 1", "M 5 13 L 13 5"];
    for (let i = 0; i < stripes.length; i++) {
      const line = addVector(g, stripes[i], colorVar, 1);
      line.opacity = 0.35;
    }
    const q = makeText("?", "Fleetglint/Mono/Badge 12", colorVar, "glyph-text");
    g.appendChild(q);
    q.x = (size - q.width) / 2;
    q.y = (size - q.height) / 2 - 1;
  } else if (kind === "bang") {
    const b = makeText("!", "Fleetglint/Mono/Badge 12", colorVar, "glyph-text");
    g.appendChild(b);
    b.x = (size - b.width) / 2;
    b.y = (size - b.height) / 2 - 1;
  } else if (kind === "open-dot") {
    addEllipse(g, 2, 2, size - 4, size - 4, { stroke: colorVar, weight: 1.2 });
  } else if (kind === "acked-dot") {
    addEllipse(g, 3.5, 3.5, size - 7, size - 7, { fill: colorVar });
  } else {
    addEllipse(g, 2, 2, size - 4, size - 4, { stroke: colorVar, weight: 1 });
  }
  return g;
}

function newComponent(parent, name) {
  const c = figma.createComponent();
  c.name = name;
  c.fills = [];
  c.strokes = [];
  parent.appendChild(c);
  return c;
}

function variantName(props) {
  return Object.keys(props)
    .map(function (k) {
      return k + "=" + props[k];
    })
    .join(", ");
}

function registerSet(page, name, comps) {
  const set = figma.combineAsVariants(comps, page);
  set.name = name;
  COMPONENT_SETS[name] = set;
  return set;
}

function variantComponent(setName, props) {
  const set = COMPONENT_SETS[setName];
  if (!set) throw new Error("missing component set " + setName);
  const wanted = variantName(props);
  const found = set.children.filter(function (n) {
    return n.type === "COMPONENT" && n.name === wanted;
  })[0];
  if (!found) {
    throw new Error("missing variant " + setName + " / " + wanted);
  }
  return found;
}

function instantiate(setName, props, parent) {
  const comp = variantComponent(setName, props);
  const inst = comp.createInstance();
  parent.appendChild(inst);
  return inst;
}

function plainInstance(name, parent) {
  const comp = COMPONENTS[name];
  if (!comp) throw new Error("missing component " + name);
  const inst = comp.createInstance();
  parent.appendChild(inst);
  return inst;
}

function setText(root, name, value) {
  const t = root.findOne(function (n) {
    return n.type === "TEXT" && n.name === name;
  });
  if (!t) return false;
  try {
    t.characters = value;
    return true;
  } catch (e) {
    warnings.push("could not set text " + name + ": " + e.message);
    return false;
  }
}

function resizeInstance(inst, w, h) {
  try {
    inst.resize(w, h);
  } catch (e) {
    warnings.push("could not resize instance: " + e.message);
  }
}

/* --------------------------------------------------------- fonts & styles */

async function loadFont(family, style) {
  try {
    await figma.loadFontAsync({ family: family, style: style });
    return { family: family, style: style };
  } catch (e) {
    return null;
  }
}

async function loadFonts() {
  const ui = await loadFont("Inter", "Regular");
  const uiMedium = await loadFont("Inter", "Medium");
  const uiSemi = await loadFont("Inter", "Semi Bold");
  const mono = await loadFont("JetBrains Mono", "Regular");
  const monoMedium = await loadFont("JetBrains Mono", "Medium");

  let uiFamily = null;
  if (ui) uiFamily = "Inter";
  else if (await loadFont("Roboto", "Regular")) uiFamily = "Roboto";
  else if (await loadFont("Arial", "Regular")) uiFamily = "Arial";

  let monoFamily = null;
  if (mono) monoFamily = "JetBrains Mono";
  else if (await loadFont("IBM Plex Mono", "Regular")) monoFamily = "IBM Plex Mono";
  else if (await loadFont("Roboto Mono", "Regular")) monoFamily = "Roboto Mono";

  const uiFallback = uiFamily || "Inter";
  const monoFallback = monoFamily || uiFallback;
  const load = async function (family, style) {
    const f = await loadFont(family, style);
    return f || { family: uiFallback, style: "Regular" };
  };

  FONTS = {
    uiRegular: ui || (await load(uiFallback, "Regular")),
    uiMedium: uiMedium || (await load(uiFallback, "Medium")),
    uiSemiBold: uiSemi || (await load(uiFallback, "Semi Bold")),
    monoRegular: mono || (await load(monoFallback, "Regular")),
    monoMedium: monoMedium || (await load(monoFallback, "Medium"))
  };
  if (!ui) warnings.push("Inter not available; UI uses " + uiFallback);
  if (!mono) warnings.push("JetBrains Mono not available; mono uses " + monoFallback);
}

async function buildTextStyles() {
  // Update the plugin's styles in place (same ids) so text bound to them
  // anywhere in the file keeps its binding; never delete a style.
  const existing = await figma.getLocalTextStylesAsync();
  const byName = {};
  for (let i = 0; i < existing.length; i++) byName[existing[i].name] = existing[i];
  const defs = [
    ["Fleetglint/UI/Row 13", FONTS.uiRegular, 13, 20],
    ["Fleetglint/UI/Row Strong 13", FONTS.uiMedium, 13, 20],
    ["Fleetglint/UI/Meta 12", FONTS.uiRegular, 12, 16],
    ["Fleetglint/UI/Badge 12", FONTS.uiMedium, 12, 16],
    ["Fleetglint/UI/Heading 16", FONTS.uiSemiBold, 16, 22],
    ["Fleetglint/UI/Heading 20", FONTS.uiSemiBold, 20, 26],
    ["Fleetglint/Mono/Data 13", FONTS.monoRegular, 13, 20],
    ["Fleetglint/Mono/Meta 12", FONTS.monoRegular, 12, 16],
    ["Fleetglint/Mono/Badge 12", FONTS.monoMedium, 12, 16],
    ["Fleetglint/Mono/Number 28", FONTS.monoRegular, 28, 34]
  ];
  for (let i = 0; i < defs.length; i++) {
    const d = defs[i];
    const s = byName[d[0]] || figma.createTextStyle();
    s.name = d[0];
    s.fontName = d[1];
    s.fontSize = d[2];
    s.lineHeight = { unit: "PIXELS", value: d[3] };
    STYLES[d[0]] = s;
  }
}

/* ------------------------------------------------------------- variables */

async function getOrCreateCollection(name) {
  const all = await figma.variables.getLocalVariableCollectionsAsync();
  for (let i = 0; i < all.length; i++) {
    if (all[i].name === name) return all[i];
  }
  return figma.variables.createVariableCollection(name);
}

async function syncCollection(collection, desired, register) {
  const modeId = collection.modes[0].modeId;
  const allVariables = await figma.variables.getLocalVariablesAsync();
  const existing = allVariables.filter(function (v) {
    return v.variableCollectionId === collection.id;
  });
  const keep = {};
  for (let i = 0; i < existing.length; i++) {
    const v = existing[i];
    if (!desired[v.name]) {
      // Remove only variables this plugin created; leave anyone else's.
      if (v.getPluginData(OWNER_KEY) === "1") v.remove();
    } else {
      keep[v.name] = v;
    }
  }
  Object.keys(desired).forEach(function (name) {
    const d = desired[name];
    let v = keep[name];
    if (!v) {
      v = figma.variables.createVariable(name, collection, d.type);
      // Mark only what this plugin creates; a same-name variable that was
      // already there is updated but never becomes removable.
      v.setPluginData(OWNER_KEY, "1");
    }
    if (d.type === "COLOR") {
      let value;
      if (typeof d.value === "string" && d.value.indexOf("color/") === 0) {
        const target = PRIM[d.value];
        if (target) {
          value = figma.variables.createVariableAlias(target);
        } else {
          value = hexToRgba(d.value);
        }
      } else {
        value = hexToRgba(d.value);
      }
      v.setValueForMode(modeId, value);
    } else {
      v.setValueForMode(modeId, d.value);
    }
    register[name] = v;
  });
}

async function syncVariables() {
  const primCollection = await getOrCreateCollection(COLLECTION_PRIMITIVES);
  const primDesired = {};
  Object.keys(TOKENS.primitives.color).forEach(function (k) {
    primDesired["color/" + k] = { type: "COLOR", value: TOKENS.primitives.color[k] };
  });
  Object.keys(TOKENS.primitives.space).forEach(function (k) {
    primDesired["space/" + k] = { type: "FLOAT", value: TOKENS.primitives.space[k] };
  });
  Object.keys(TOKENS.primitives.radius).forEach(function (k) {
    primDesired["radius/" + k] = { type: "FLOAT", value: TOKENS.primitives.radius[k] };
  });
  Object.keys(TOKENS.primitives.fontSize).forEach(function (k) {
    primDesired["font-size/" + k] = { type: "FLOAT", value: TOKENS.primitives.fontSize[k] };
  });
  primDesired["motion/fast"] = { type: "FLOAT", value: TOKENS.motion.fast };
  primDesired["motion/base"] = { type: "FLOAT", value: TOKENS.motion.base };
  primDesired["motion/ambient"] = { type: "FLOAT", value: TOKENS.motion.ambient };
  primDesired["geometry/row-compact"] = { type: "FLOAT", value: TOKENS.geometry.rowCompact };
  primDesired["geometry/row-default"] = { type: "FLOAT", value: TOKENS.geometry.rowDefault };
  primDesired["geometry/radius-chip"] = { type: "FLOAT", value: TOKENS.geometry.radiusChip };
  primDesired["geometry/radius-panel"] = { type: "FLOAT", value: TOKENS.geometry.radiusPanel };
  await syncCollection(primCollection, primDesired, PRIM);

  const semCollection = await getOrCreateCollection(COLLECTION_SEMANTIC);
  try {
    semCollection.renameMode(semCollection.modes[0].modeId, "dark");
  } catch (e) {
    /* already named dark */
  }
  const semDesired = {};
  ["surface", "text", "line", "provenance"].forEach(function (group) {
    const g = TOKENS.semantic[group];
    Object.keys(g).forEach(function (k) {
      semDesired[group + "/" + k] = { type: "COLOR", value: g[k] };
    });
  });
  Object.keys(TOKENS.semantic.state).forEach(function (state) {
    const cfg = TOKENS.semantic.state[state];
    ["fg", "bg", "border"].forEach(function (part) {
      semDesired[stateColorVar(state, part)] = { type: "COLOR", value: cfg[part] };
    });
  });
  await syncCollection(semCollection, semDesired, SEM);
}

/* ---------------------------------------------------------------- pages */

function getOrCreatePage(name) {
  const pages = figma.root.children.filter(function (n) {
    return n.type === "PAGE";
  });
  for (let i = 0; i < pages.length; i++) {
    if (pages[i].name === name) return pages[i];
  }
  const p = figma.createPage();
  p.name = name;
  return p;
}

async function clearPage(page) {
  await page.loadAsync();
  const kids = page.children.slice();
  for (let i = 0; i < kids.length; i++) kids[i].remove();
}

async function preparePages() {
  PAGES.foundations = getOrCreatePage(PAGE_NAMES[0]);
  PAGES.components = getOrCreatePage(PAGE_NAMES[1]);
  PAGES.screens = getOrCreatePage(PAGE_NAMES[2]);
  PAGE_NAMES.forEach(function (name, i) {
    const p = PAGES[name.toLowerCase()];
    try {
      figma.root.insertChild(i, p);
    } catch (e) {
      /* order is cosmetic */
    }
  });
  await clearPage(PAGES.foundations);
  await clearPage(PAGES.components);
  await clearPage(PAGES.screens);
  pagesCount = 3;
}

/* ------------------------------------------------------------ components */

function buildStateBadge(page) {
  const comps = [];
  let row = 0;
  for (let s = 0; s < BADGE_STATES.length; s++) {
    const state = BADGE_STATES[s];
    const cfg = TOKENS.semantic.state[state];
    for (let z = 0; z < BADGE_SIZE.length; z++) {
      for (let a = 0; a < BADGE_AGE.length; a++) {
        const size = BADGE_SIZE[z];
        const age = BADGE_AGE[a];
        const c = newComponent(page, "state=" + state + ", size=" + size + ", age=" + age);
        setAuto(c, "HORIZONTAL", {
          gap: size === "sm" ? 5 : 6,
          padX: size === "sm" ? 7 : 9,
          padY: size === "sm" ? 2 : 4,
          align: "CENTER"
        });
        c.fills = [paint(stateColorVar(state, "bg"))];
        c.strokes = [paint(stateColorVar(state, "border"))];
        c.strokeWeight = 1;
        c.cornerRadius = TOKENS.geometry.radiusChip;
        if (state === "stale") c.dashPattern = [3, 2];
        if (state === "attention") {
          const bar = makeRect(2, 12, { fill: stateColorVar(state, "border") });
          c.appendChild(bar);
        }
        c.appendChild(makeGlyph(cfg.kind, stateColorVar(state, "fg")));
        const label = makeText(
          cfg.label,
          size === "sm" ? "Fleetglint/UI/Badge 12" : "Fleetglint/UI/Row Strong 13",
          stateColorVar(state, "fg"),
          "label"
        );
        c.appendChild(label);
        if (age === "suffix") {
          const ageText = makeText(
            "42m",
            "Fleetglint/Mono/Meta 12",
            stateColorVar(state, "fg"),
            "age"
          );
          c.appendChild(ageText);
        }
        const col = z * 2 + a;
        c.x = col * 190;
        c.y = row * 44;
        comps.push(c);
      }
    }
    row += 1;
  }
  return registerSet(page, "StateBadge", comps);
}

function buildSourceChip(page) {
  const statuses = ["ok", "discontinuity", "unavailable", "quarantine"];
  const dotColors = {
    ok: "state/running/fg",
    discontinuity: "state/waiting/fg",
    unavailable: "state/failed/fg",
    quarantine: "state/cancelled/fg"
  };
  const comps = [];
  for (let i = 0; i < statuses.length; i++) {
    const status = statuses[i];
    const c = newComponent(page, "status=" + status);
    setAuto(c, "HORIZONTAL", { gap: 5, padX: 6, padY: 3, align: "CENTER" });
    c.fills = [paint("provenance/source-chip-bg")];
    c.cornerRadius = TOKENS.geometry.radiusChip;
    c.appendChild(makeGlyph("acked-dot", dotColors[status]));
    c.appendChild(makeText("my-workflow@mbp", "Fleetglint/Mono/Meta 12", "provenance/source-chip-fg", "source"));
    c.x = 0;
    c.y = i * 30;
    comps.push(c);
  }
  return registerSet(page, "SourceChip", comps);
}

function buildEvidenceLabel(page) {
  const kinds = ["process", "refresh", "none"];
  const contents = { process: "pid ok 12s", refresh: "refresh 3m", none: "no evidence" };
  const comps = [];
  for (let i = 0; i < kinds.length; i++) {
    const kind = kinds[i];
    const c = newComponent(page, "kind=" + kind);
    setAuto(c, "HORIZONTAL", { gap: 5, align: "CENTER" });
    c.appendChild(makeGlyph("acked-dot", kind === "none" ? "provenance/age-old" : "provenance/age-fresh"));
    c.appendChild(
      makeText(
        contents[kind],
        "Fleetglint/Mono/Meta 12",
        kind === "none" ? "provenance/age-old" : "provenance/age-fresh",
        "text"
      )
    );
    c.x = 0;
    c.y = i * 26;
    comps.push(c);
  }
  return registerSet(page, "EvidenceLabel", comps);
}

function buildRefLink(page) {
  const kinds = ["record", "external", "unresolved"];
  const contents = { record: "run · lead-7f3a", external: "PR · eddington-1919#176", unresolved: "job · lw-store-blink" };
  const comps = [];
  for (let i = 0; i < kinds.length; i++) {
    const kind = kinds[i];
    const c = newComponent(page, "kind=" + kind);
    setAuto(c, "VERTICAL", { gap: 2 });
    c.fills = [];
    const row = makeFrame("ref-row", { layout: "HORIZONTAL", gap: 6, align: "CENTER" });
    row.fills = [];
    row.appendChild(makeGlyph(kind === "unresolved" ? "broken-link" : "ring", kind === "unresolved" ? "line/unresolved" : "line/relationship"));
    row.appendChild(
      makeText(
        contents[kind],
        "Fleetglint/Mono/Data 13",
        kind === "unresolved" ? "line/unresolved" : "text/link",
        "ref"
      )
    );
    if (kind === "unresolved") {
      row.appendChild(makeText("not seen", "Fleetglint/UI/Meta 12", "line/unresolved", "meta"));
    }
    c.appendChild(row);
    if (kind === "unresolved") {
      const line = addVector(c, "M 0 0 L 220 0", "line/unresolved", 1);
      line.dashPattern = [2, 2];
    }
    c.x = 0;
    c.y = i * 30;
    comps.push(c);
  }
  return registerSet(page, "RefLink", comps);
}

function buildRunRow(page) {
  const sizes = { compact: 28, default: 32 };
  const fills = {
    rest: null,
    hover: "surface/row-hover",
    selected: "surface/row-selected"
  };
  const comps = [];
  const densities = ["compact", "default"];
  const interactions = ["rest", "hover", "selected"];
  let i = 0;
  for (let d = 0; d < densities.length; d++) {
    for (let n = 0; n < interactions.length; n++) {
      const density = densities[d];
      const interaction = interactions[n];
      const c = newComponent(page, "density=" + density + ", interaction=" + interaction);
      setAuto(c, "HORIZONTAL", { gap: 12, padX: 12, align: "CENTER" });
      c.primaryAxisSizingMode = "FIXED";
      c.counterAxisSizingMode = "FIXED";
      c.resize(1000, sizes[density]);
      c.fills = fills[interaction] ? [paint(fills[interaction])] : [];
      c.strokes = [];

      const badge = instantiate("StateBadge", { state: "running", size: "sm", age: "none" }, c);
      badge.name = "badge";

      const title = makeText("worker: task summary", "Fleetglint/UI/Row 13", "text/primary", "title");
      title.textAutoResize = "HEIGHT";
      title.layoutGrow = 1;
      truncate(title);
      c.appendChild(title);

      c.appendChild(makeText("deepseek-flash", "Fleetglint/Mono/Meta 12", "text/secondary", "agent"));
      c.appendChild(makeText("edd-lead", "Fleetglint/UI/Meta 12", "text/meta", "role"));
      c.appendChild(makeText("eddington-1919", "Fleetglint/UI/Meta 12", "text/meta", "project"));
      c.appendChild(makeText("12s", "Fleetglint/Mono/Meta 12", "text/meta", "age"));
      c.appendChild(makeText("pid ok 12s", "Fleetglint/Mono/Meta 12", "provenance/age-fresh", "note"));

      c.x = n * 1020;
      c.y = d * 44;
      comps.push(c);
      i += 1;
    }
  }
  return registerSet(page, "RunRow", comps);
}

function buildJobRow(page) {
  const sizes = { compact: 28, default: 32 };
  const comps = [];
  const densities = ["compact", "default"];
  for (let d = 0; d < densities.length; d++) {
    const density = densities[d];
    const c = newComponent(page, "density=" + density);
    setAuto(c, "HORIZONTAL", { gap: 12, padX: 12, align: "CENTER" });
    c.primaryAxisSizingMode = "FIXED";
    c.counterAxisSizingMode = "FIXED";
    c.resize(1000, sizes[density]);
    c.fills = [];
    const badge = instantiate("StateBadge", { state: "running", size: "sm", age: "none" }, c);
    badge.name = "badge";
    const cmd = makeText("pnpm test --filter web", "Fleetglint/Mono/Data 13", "text/mono-data", "command");
    cmd.textAutoResize = "HEIGHT";
    cmd.layoutGrow = 1;
    truncate(cmd);
    c.appendChild(cmd);
    c.appendChild(makeText("test", "Fleetglint/UI/Meta 12", "text/meta", "kind"));
    c.appendChild(makeText("run · ds-fg-2", "Fleetglint/Mono/Meta 12", "text/meta", "run"));
    c.appendChild(makeText("exit 0", "Fleetglint/Mono/Meta 12", "text/meta", "exit"));
    c.x = 0;
    c.y = d * 44;
    comps.push(c);
  }
  return registerSet(page, "JobRow", comps);
}

function buildInboxItem(page) {
  const tones = ["action", "normal", "acked"];
  const comps = [];
  for (let i = 0; i < tones.length; i++) {
    const tone = tones[i];
    const c = newComponent(page, "tone=" + tone);
    setAuto(c, "VERTICAL", { gap: 6, padX: 12, padY: 10 });
    c.primaryAxisSizingMode = "AUTO";
    c.counterAxisSizingMode = "FIXED";
    c.resize(1000, 100);
    c.fills = tone === "action" ? [paint("state/attention/bg")] : [paint("surface/panel")];
    c.strokes = tone === "action" ? [paint("state/attention/border")] : [paint("line/divider")];
    c.strokeWeight = 1;
    c.cornerRadius = TOKENS.geometry.radiusPanel;

    const head = makeFrame("head", { layout: "HORIZONTAL", gap: 10, align: "CENTER" });
    head.fills = [];
    const badgeState = tone === "action" ? "attention" : tone === "acked" ? "inbox-acked" : "inbox-open";
    const badge = instantiate("StateBadge", { state: badgeState, size: "sm", age: "none" }, head);
    badge.name = "badge";
    head.appendChild(makeText("edd-lead", "Fleetglint/Mono/Meta 12", "text/secondary", "role"));
    head.appendChild(makeText("job_finished", "Fleetglint/UI/Meta 12", "text/meta", "kind"));
    const spacer = makeFrame("spacer", { layout: "HORIZONTAL" });
    spacer.fills = [];
    spacer.layoutGrow = 1;
    head.appendChild(spacer);
    head.appendChild(makeText("12m", "Fleetglint/Mono/Meta 12", "text/meta", "age"));
    c.appendChild(head);

    const ref = instantiate("RefLink", { kind: "record" }, c);
    ref.name = "subject";
    c.appendChild(
      makeText(
        "ds-edd-1 finished (exit 0); review the PR before the next run starts.",
        "Fleetglint/UI/Row 13",
        "text/secondary",
        "detail"
      )
    );
    const detail = c.findOne(function (n) {
      return n.type === "TEXT" && n.name === "detail";
    });
    if (detail) {
      detail.textAutoResize = "HEIGHT";
      detail.layoutAlign = "STRETCH";
    }
    c.x = 0;
    c.y = i * 140;
    comps.push(c);
  }
  return registerSet(page, "InboxItem", comps);
}

function buildCountTile(page) {
  const tiles = [
    ["running", "3", "Running"],
    ["waiting", "1", "Waiting"],
    ["attention", "2", "Needs attention"],
    ["stale-lost-unknown", "3", "Stale · lost · unknown"]
  ];
  const comps = [];
  for (let i = 0; i < tiles.length; i++) {
    const key = tiles[i][0];
    const c = newComponent(page, "key=" + key);
    setAuto(c, "VERTICAL", { gap: 4, padX: 14, padY: 12 });
    c.primaryAxisSizingMode = "FIXED";
    c.counterAxisSizingMode = "FIXED";
    c.resize(250, 96);
    c.fills = [paint("surface/panel")];
    c.strokes = [paint("line/divider")];
    c.strokeWeight = 1;
    c.cornerRadius = TOKENS.geometry.radiusPanel;
    c.appendChild(makeText(tiles[i][1], "Fleetglint/Mono/Number 28", "text/primary", "number"));
    c.appendChild(makeText(tiles[i][2], "Fleetglint/UI/Meta 12", "text/meta", "label"));
    const badgeState =
      key === "stale-lost-unknown" ? "unknown" : key === "attention" ? "attention" : key;
    const badge = instantiate("StateBadge", { state: badgeState, size: "sm", age: "none" }, c);
    badge.name = "badge";
    c.x = 0;
    c.y = i * 110;
    comps.push(c);
  }
  return registerSet(page, "CountTile", comps);
}

function buildTopBar(page) {
  const sources = ["ok", "discontinuity", "unavailable"];
  const comps = [];
  for (let i = 0; i < sources.length; i++) {
    const source = sources[i];
    const c = newComponent(page, "source=" + source);
    setAuto(c, "HORIZONTAL", { gap: 12, padX: 16, align: "CENTER" });
    c.primaryAxisSizingMode = "FIXED";
    c.counterAxisSizingMode = "FIXED";
    c.resize(1400, 44);
    c.fills = [paint("surface/chrome")];
    c.strokes = [paint("line/divider")];
    c.strokeWeight = 1;
    c.appendChild(makeText("FLEETGLINT", "Fleetglint/Mono/Meta 12", "state/running/fg", "mark"));
    const divider = makeRect(1, 16, { fill: "line/divider" });
    c.appendChild(divider);
    const chipStates =
      source === "unavailable" ? ["unavailable"] : source === "discontinuity" ? ["ok", "discontinuity"] : ["ok", "ok"];
    for (let k = 0; k < chipStates.length; k++) {
      const chip = instantiate("SourceChip", { status: chipStates[k] }, c);
      chip.name = "source-" + k;
    }
    const spacer = makeFrame("spacer", { layout: "HORIZONTAL" });
    spacer.fills = [];
    spacer.layoutGrow = 1;
    c.appendChild(spacer);
    c.appendChild(makeText("refresh 2s", "Fleetglint/Mono/Meta 12", "text/meta", "refresh"));
    const ro = makeFrame("read-only", { layout: "HORIZONTAL", gap: 5, padX: 6, padY: 3, align: "CENTER" });
    ro.fills = [paint("surface/raised")];
    ro.cornerRadius = TOKENS.geometry.radiusChip;
    ro.appendChild(makeText("read-only", "Fleetglint/UI/Meta 12", "text/meta", "text"));
    c.appendChild(ro);
    c.x = 0;
    c.y = i * 60;
    comps.push(c);
  }
  return registerSet(page, "TopBar", comps);
}

function buildBanner(page) {
  const kinds = ["unavailable", "discontinuity", "quarantine"];
  const cfg = {
    unavailable: { state: "failed", glyph: "cross", title: "Unavailable", detail: "the adapter cannot read this source; no data is shown as current" },
    discontinuity: { state: "waiting", glyph: "arrow", title: "Discontinuity", detail: "3 bad lines were skipped; counts may be incomplete" },
    quarantine: { state: "unknown", glyph: "question", title: "Quarantine", detail: "3 lines were rejected at ingest; they are not shown" }
  };
  const comps = [];
  for (let i = 0; i < kinds.length; i++) {
    const kind = kinds[i];
    const c = newComponent(page, "kind=" + kind);
    setAuto(c, "HORIZONTAL", { gap: 10, padX: 14, padY: 10, align: "CENTER" });
    c.primaryAxisSizingMode = "FIXED";
    c.counterAxisSizingMode = "FIXED";
    c.resize(1000, 44);
    c.fills = [paint(stateColorVar(cfg[kind].state, "bg"))];
    c.strokes = [paint(stateColorVar(cfg[kind].state, "border"))];
    c.strokeWeight = 1;
    c.cornerRadius = TOKENS.geometry.radiusChip;
    c.appendChild(makeGlyph(cfg[kind].glyph, stateColorVar(cfg[kind].state, "fg")));
    c.appendChild(makeText(cfg[kind].title, "Fleetglint/UI/Row Strong 13", stateColorVar(cfg[kind].state, "fg"), "title"));
    c.appendChild(makeText(cfg[kind].detail, "Fleetglint/UI/Meta 12", stateColorVar(cfg[kind].state, "fg"), "detail"));
    c.x = 0;
    c.y = i * 60;
    comps.push(c);
  }
  return registerSet(page, "Banner", comps);
}

function buildLogTail(page) {
  const kinds = ["readable", "redacted", "not-readable"];
  const lines = {
    readable: ["12:31:28 worker started", "12:31:29 tokens loaded", "12:35:02 build ok", "12:47:40 exit 0"],
    redacted: ["12:31:28 worker started", "env DEEPSEEK_API_KEY=[redacted]", "12:35:02 build ok", "12:47:40 exit 0"],
    "not-readable": ["not readable: path is outside the allowed root"]
  };
  const comps = [];
  for (let i = 0; i < kinds.length; i++) {
    const kind = kinds[i];
    const c = newComponent(page, "kind=" + kind);
    setAuto(c, "VERTICAL", { gap: 2, padX: 12, padY: 10 });
    c.primaryAxisSizingMode = "FIXED";
    c.counterAxisSizingMode = "FIXED";
    c.resize(720, 140);
    c.fills = [paint("surface/canvas")];
    c.strokes = [paint("line/divider")];
    c.strokeWeight = 1;
    c.cornerRadius = TOKENS.geometry.radiusChip;
    c.appendChild(makeText("log tail · last 64 KiB · size cap 256 KiB", "Fleetglint/UI/Meta 12", "text/meta", "header"));
    const rows = lines[kind];
    for (let k = 0; k < rows.length; k++) {
      c.appendChild(makeText(rows[k], "Fleetglint/Mono/Meta 12", "text/mono-data", "line-" + k));
    }
    c.x = 0;
    c.y = i * 160;
    comps.push(c);
  }
  return registerSet(page, "LogTail", comps);
}

function buildStateTransition(page) {
  const c = newComponent(page, "StateTransition");
  setAuto(c, "HORIZONTAL", { gap: 8, padX: 10, padY: 4, align: "CENTER" });
  c.fills = [paint("surface/panel")];
  c.strokes = [paint("line/divider")];
  c.strokeWeight = 1;
  c.cornerRadius = TOKENS.geometry.radiusChip;
  c.appendChild(makeText("running", "Fleetglint/Mono/Meta 12", "text/secondary", "from"));
  c.appendChild(makeText("→", "Fleetglint/Mono/Meta 12", "text/meta", "arrow"));
  c.appendChild(makeText("stale 42m", "Fleetglint/Mono/Meta 12", "state/stale/fg", "to"));
  COMPONENTS.StateTransition = c;
  return c;
}

function buildRelationshipTree(page) {
  const c = newComponent(page, "RelationshipTree");
  setAuto(c, "VERTICAL", { gap: 6, padX: 12, padY: 12 });
  c.primaryAxisSizingMode = "AUTO";
  c.counterAxisSizingMode = "FIXED";
  c.resize(848, 100);
  c.fills = [paint("surface/panel")];
  c.strokes = [paint("line/divider")];
  c.strokeWeight = 1;
  c.cornerRadius = TOKENS.geometry.radiusPanel;
  c.appendChild(makeText("Relationships", "Fleetglint/UI/Heading 16", "text/primary", "heading"));
  const rows = [
    ["parent", "lead-7f3a"],
    ["children (2)", "ds-edd-1 · review-oracle-331"],
    ["resume chain", "lead-7f3a → lead-9c21"],
    ["waits on", "PR · nurockplayer/eddington-1919#176"]
  ];
  for (let i = 0; i < rows.length; i++) {
    const row = makeFrame("rel-" + i, { layout: "HORIZONTAL", gap: 12, align: "CENTER" });
    row.fills = [];
    const label = makeText(rows[i][0], "Fleetglint/UI/Meta 12", "text/meta", "label");
    label.textAutoResize = "NONE";
    label.resize(120, 16);
    row.appendChild(label);
    row.appendChild(makeText(rows[i][1], "Fleetglint/Mono/Meta 12", "text/secondary", "value"));
    c.appendChild(row);
  }
  COMPONENTS.RelationshipTree = c;
  return c;
}

function buildTooltip(page) {
  const c = newComponent(page, "Tooltip");
  setAuto(c, "VERTICAL", { gap: 4, padX: 12, padY: 8 });
  c.primaryAxisSizingMode = "FIXED";
  c.counterAxisSizingMode = "FIXED";
  c.resize(260, 56);
  c.fills = [paint("surface/overlay")];
  c.strokes = [paint("line/boundary")];
  c.strokeWeight = 1;
  c.cornerRadius = TOKENS.geometry.radiusChip;
  c.effects = [
    {
      type: "DROP_SHADOW",
      color: { r: 0, g: 0, b: 0, a: 0.45 },
      offset: { x: 0, y: 4 },
      radius: 12,
      spread: 0,
      visible: true,
      blendMode: "NORMAL"
    }
  ];
  c.appendChild(makeText("waits on", "Fleetglint/UI/Row Strong 13", "text/primary", "title"));
  c.appendChild(makeText("blocked on PR #176 until the review gate runs", "Fleetglint/UI/Meta 12", "text/meta", "body"));
  COMPONENTS.Tooltip = c;
  return c;
}

function buildEmptyState(page) {
  const c = newComponent(page, "EmptyState");
  setAuto(c, "VERTICAL", { gap: 8, padX: 24, padY: 24, align: "CENTER", justify: "CENTER" });
  c.primaryAxisSizingMode = "FIXED";
  c.counterAxisSizingMode = "FIXED";
  c.resize(640, 280);
  c.fills = [paint("surface/panel")];
  c.strokes = [paint("line/divider")];
  c.strokeWeight = 1;
  c.cornerRadius = TOKENS.geometry.radiusPanel;
  c.appendChild(makeText("No sources yet", "Fleetglint/UI/Heading 20", "text/primary", "title"));
  c.appendChild(
    makeText(
      "Write NDJSON records into the watch directory and Fleetglint will pick them up.",
      "Fleetglint/UI/Row 13",
      "text/secondary",
      "body"
    )
  );
  c.appendChild(makeText("~/.local/state/fleetglint/records/", "Fleetglint/Mono/Data 13", "state/running/fg", "path"));
  COMPONENTS.EmptyState = c;
  return c;
}

async function buildComponents(page) {
  await figma.setCurrentPageAsync(page);
  let y = 80;
  const sets = [];
  currentItem = "StateBadge";
  const badge = buildStateBadge(page);
  sets.push(badge);
  currentItem = "SourceChip";
  sets.push(buildSourceChip(page));
  currentItem = "EvidenceLabel";
  sets.push(buildEvidenceLabel(page));
  currentItem = "RefLink";
  sets.push(buildRefLink(page));
  currentItem = "RunRow";
  sets.push(buildRunRow(page));
  currentItem = "JobRow";
  sets.push(buildJobRow(page));
  currentItem = "InboxItem";
  sets.push(buildInboxItem(page));
  currentItem = "CountTile";
  sets.push(buildCountTile(page));
  currentItem = "TopBar";
  sets.push(buildTopBar(page));
  currentItem = "Banner";
  sets.push(buildBanner(page));
  currentItem = "LogTail";
  sets.push(buildLogTail(page));
  for (let i = 0; i < sets.length; i++) {
    sets[i].x = 80;
    sets[i].y = y;
    y += sets[i].height + 100;
  }
  currentItem = "StateTransition";
  const plain = [buildStateTransition(page)];
  currentItem = "RelationshipTree";
  plain.push(buildRelationshipTree(page));
  currentItem = "Tooltip";
  plain.push(buildTooltip(page));
  currentItem = "EmptyState";
  plain.push(buildEmptyState(page));
  for (let i = 0; i < plain.length; i++) {
    plain[i].x = 80;
    plain[i].y = y;
    y += plain[i].height + 100;
  }
  currentItem = "";
}

/* ----------------------------------------------------------- foundations */

async function buildFoundations(page) {
  await figma.setCurrentPageAsync(page);
  const x = 80;
  let y = 240; // leaves the top-left corner for fleetglint-build-log
  page.appendChild(makeTextAt("Foundations", "Fleetglint/UI/Heading 20", "text/primary", x, y));
  y += 40;
  page.appendChild(
    makeTextAt(
      "Generated by design/figma-plugin/code.js. Values are reviewed in code; this page is the visual reference.",
      "Fleetglint/UI/Meta 12",
      "text/meta",
      x,
      y
    )
  );
  y += 40;

  page.appendChild(makeTextAt("Semantic colors", "Fleetglint/UI/Heading 16", "text/primary", x, y));
  y += 30;

  const swatches = [];
  ["surface", "text", "line", "provenance"].forEach(function (group) {
    Object.keys(TOKENS.semantic[group]).forEach(function (k) {
      swatches.push({ name: group + "/" + k });
    });
  });
  STATE_KEYS.forEach(function (state) {
    ["fg", "bg", "border"].forEach(function (part) {
      swatches.push({ name: "state/" + state + "/" + part });
    });
  });

  const cols = 5;
  const cardW = 240;
  const cardH = 72;
  for (let i = 0; i < swatches.length; i++) {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const cx = x + col * (cardW + 16);
    const cy = y + row * (cardH + 12);
    const sw = makeFrame("swatch " + swatches[i].name, { layout: "VERTICAL", gap: 4 });
    sw.fills = [];
    const chip = makeRect(cardW - 8, 28, { fill: swatches[i].name, radius: 2 });
    sw.appendChild(chip);
    sw.appendChild(makeText(swatches[i].name, "Fleetglint/Mono/Meta 12", "text/secondary", "name"));
    sw.appendChild(makeText(resolveHex(swatches[i].name), "Fleetglint/Mono/Meta 12", "text/meta", "hex"));
    sw.x = cx;
    sw.y = cy;
    page.appendChild(sw);
  }
  const rowsOfSwatches = Math.ceil(swatches.length / cols);
  y += rowsOfSwatches * (cardH + 12) + 40;

  page.appendChild(makeTextAt("Primitive ramps", "Fleetglint/UI/Heading 16", "text/primary", x, y));
  y += 30;
  const ramps = {};
  Object.keys(TOKENS.primitives.color).forEach(function (key) {
    const ramp = key.split("/")[0];
    if (!ramps[ramp]) ramps[ramp] = [];
    ramps[ramp].push(key);
  });
  Object.keys(ramps).forEach(function (ramp) {
    page.appendChild(makeTextAt(ramp, "Fleetglint/UI/Meta 12", "text/meta", x, y));
    let cx = x + 90;
    for (let i = 0; i < ramps[ramp].length; i++) {
      const key = ramps[ramp][i];
      const chip = makeRect(34, 22, { fill: "color/" + key, radius: 2 });
      chip.x = cx;
      chip.y = y - 2;
      page.appendChild(chip);
      cx += 38;
    }
    y += 30;
  });
  y += 20;

  page.appendChild(makeTextAt("Type ramp", "Fleetglint/UI/Heading 16", "text/primary", x, y));
  y += 30;
  const typeSpecimens = [
    ["Fleetglint/UI/Heading 20", "Heading 20 · screen title"],
    ["Fleetglint/UI/Heading 16", "Heading 16 · section"],
    ["Fleetglint/UI/Row 13", "Row 13 · run title and body"],
    ["Fleetglint/UI/Meta 12", "Meta 12 · role, project, kind"],
    ["Fleetglint/Mono/Data 13", "Mono Data 13 · commands, ids"],
    ["Fleetglint/Mono/Meta 12", "Mono Meta 12 · ages, process"],
    ["Fleetglint/Mono/Number 28", "28"]
  ];
  for (let i = 0; i < typeSpecimens.length; i++) {
    page.appendChild(makeTextAt(typeSpecimens[i][1], typeSpecimens[i][0], "text/primary", x, y));
    y += i === typeSpecimens.length - 1 ? 44 : 28;
  }
  y += 20;

  page.appendChild(makeTextAt("State legend", "Fleetglint/UI/Heading 16", "text/primary", x, y));
  y += 30;
  const head = ["glyph", "state", "fg", "bg", "text", "border"];
  const widths = [40, 130, 90, 90, 70, 70];
  let hx = x;
  for (let i = 0; i < head.length; i++) {
    const t = makeTextAt(head[i], "Fleetglint/UI/Meta 12", "text/meta", hx, y);
    page.appendChild(t);
    hx += widths[i];
  }
  y += 24;
  for (let i = 0; i < STATE_KEYS.length; i++) {
    const state = STATE_KEYS[i];
    const cfg = TOKENS.semantic.state[state];
    const fg = resolveHex(stateColorVar(state, "fg"));
    const bg = resolveHex(stateColorVar(state, "bg"));
    const border = resolveHex(stateColorVar(state, "border"));
    const row = makeFrame("legend " + state, { layout: "HORIZONTAL", gap: 0, align: "CENTER" });
    row.fills = [];
    const cell = function (width, node) {
      const f = makeFrame("cell", { layout: "HORIZONTAL" });
      f.fills = [];
      f.resize(width, 28);
      f.appendChild(node);
      row.appendChild(f);
    };
    cell(40, makeGlyph(cfg.kind, stateColorVar(state, "fg")));
    cell(130, makeText(cfg.label === "action" ? "action (inbox)" : cfg.label, "Fleetglint/UI/Row 13", "text/secondary", "state"));
    cell(90, makeText(fg, "Fleetglint/Mono/Meta 12", "text/meta", "fg"));
    cell(90, makeText(bg, "Fleetglint/Mono/Meta 12", "text/meta", "bg"));
    cell(70, makeText(contrastRatio(fg, bg).toFixed(1) + ":1", "Fleetglint/Mono/Meta 12", "text/secondary", "text-contrast"));
    cell(70, makeText(contrastRatio(border, bg).toFixed(1) + ":1", "Fleetglint/Mono/Meta 12", "text/meta", "border-contrast"));
    row.x = x;
    row.y = y;
    page.appendChild(row);
    y += 28;
    const divider = makeRect(500, 1, { fill: "line/divider" });
    divider.x = x;
    divider.y = y - 1;
    page.appendChild(divider);
  }
  y += 30;

  page.appendChild(makeTextAt("Motion", "Fleetglint/UI/Heading 16", "text/primary", x, y));
  y += 28;
  page.appendChild(
    makeTextAt(
      "fast 120 ms (hover, focus) · base 200 ms (panels) · ambient 1600 ms (running pulse; static under reduced motion)",
      "Fleetglint/UI/Row 13",
      "text/secondary",
      x,
      y
    )
  );
  y += 28;
  page.appendChild(
    makeTextAt(
      "Geometry: row height 28 compact / 32 default; radius 4 chips, 8 panels; shadow only on overlays (tooltip).",
      "Fleetglint/UI/Row 13",
      "text/secondary",
      x,
      y
    )
  );
}

function makeTextAt(content, styleName, fill, x, y) {
  const t = makeText(content, styleName, fill, "label");
  t.x = x;
  t.y = y;
  return t;
}

/* --------------------------------------------------------------- screens */

const DATA = {
  sources: [
    { id: "my-workflow@mbp", status: "discontinuity" },
    { id: "tachiko-harness@mbp", status: "ok" },
    { id: "fleetglint@ci", status: "ok" }
  ],
  runs: [
    {
      id: "ds-edd-1-20261105-053128",
      state: "running",
      title: "store-blink: fix the blinking store badge",
      agent: "claude-code",
      model: "deepseek-flash",
      role: "edd-lead",
      project: "eddington-1919",
      age: "12s",
      note: "pid ok 12s",
      source: "my-workflow@mbp"
    },
    {
      id: "lead-9c21",
      state: "waiting",
      title: "edd-lead session (after /clear)",
      agent: "claude-code",
      model: "claude-opus-5-5",
      role: "edd-lead",
      project: "eddington-1919",
      age: "8m",
      note: "waits on → nurockplayer/eddington-1919#176",
      source: "my-workflow@mbp"
    },
    {
      id: "gteki-lead",
      state: "running",
      title: "tachiko-harness: review queue drain",
      agent: "claude-code",
      model: "claude-opus-5-5",
      role: "gteki-lead",
      project: "tachiko-harness",
      age: "3m",
      note: "pid ok 3s",
      source: "tachiko-harness@mbp"
    },
    {
      id: "old-worker-88",
      state: "stale",
      title: "migration replay: checkpoint rebuild",
      agent: "codex-cli",
      model: "gpt-6.1-terra",
      role: "gteki-ops",
      project: "tachiko-harness",
      age: "stale 42m",
      note: "no evidence",
      source: "tachiko-harness@mbp"
    },
    {
      id: "cx-harness-4821",
      state: "done",
      title: "harness: policy docs pass",
      agent: "codex-cli",
      model: "gpt-6.1-terra",
      role: "gteki-merge",
      project: "tachiko-harness",
      age: "3h",
      note: "exit 0",
      source: "tachiko-harness@mbp"
    },
    {
      id: "fleetglint-lead-2",
      state: "queued",
      title: "fleetglint: Figma import and review",
      agent: "claude-code",
      model: "claude-opus-5-5",
      role: "fleetglint-lead",
      project: "fleetglint",
      age: "1m",
      note: "no evidence",
      source: "my-workflow@mbp"
    },
    {
      id: "ds-fg-2-20261105-0800",
      state: "failed",
      title: "figma plugin: build the token builder",
      agent: "claude-code",
      model: "deepseek-flash",
      role: "fleetglint-lead",
      project: "fleetglint",
      age: "26m",
      note: "exit 1",
      source: "my-workflow@mbp"
    },
    {
      id: "review-oracle-331",
      state: "done",
      title: "review: PR #1 design brief",
      agent: "gemini-cli",
      model: "gemini-3.0-pro",
      role: "fleetglint-lead",
      project: "fleetglint",
      age: "4h",
      note: "exit 0",
      source: "fleetglint@ci"
    },
    {
      id: "eps-runner-19",
      state: "lost",
      title: "eps replay: nightly matrix",
      agent: "codex-cli",
      model: "gpt-6.1-terra",
      role: "gteki-ops",
      project: "tachiko-harness",
      age: "lost 2h",
      note: "pid gone, no terminal record",
      source: "tachiko-harness@mbp"
    },
    {
      id: "adapter-scan-4",
      state: "unknown",
      title: "adapter scan: tachiko-harness records",
      agent: "human",
      model: "—",
      role: "gteki-lead",
      project: "tachiko-harness",
      age: "unknown 15m",
      note: "source discontinuity",
      source: "tachiko-harness@mbp"
    }
  ],
  jobs: [
    {
      id: "lw-store-blink-20261105-053128",
      state: "done",
      command: "lead-wait run store-blink -- ds-exec ds-edd-1",
      kind: "wait",
      run: "lead-7f3a",
      exit: "exit 0"
    },
    {
      id: "job-run-eps-77",
      state: "lost",
      command: "pnpm test --filter eps -- --reporter=dot",
      kind: "test",
      run: "eps-runner-19",
      exit: "no exit record"
    },
    {
      id: "build-fg-1",
      state: "failed",
      command: "pnpm build --filter web",
      kind: "build",
      run: "ds-fg-2",
      exit: "exit 1"
    }
  ],
  inbox: [
    {
      tone: "action",
      role: "edd-lead",
      kind: "review_finished",
      subject: "PR · nurockplayer/eddington-1919#176",
      outcome: "merged-armed",
      age: "4m",
      detail: "Review approved at head 4f2a; auto-merge is armed and pinned to that head."
    },
    {
      tone: "normal",
      role: "fleetglint-lead",
      kind: "job_finished",
      subject: "job · build-fg-1",
      outcome: "failed",
      age: "26m",
      detail: "Build failed: TS2304 in packages/web/src/board.ts. Exit 1; the log tail is on the run detail screen."
    },
    {
      tone: "acked",
      role: "edd-lead",
      kind: "job_finished",
      subject: "job · lw-store-blink-20261105-053128",
      outcome: "done",
      age: "52m",
      detail: "ds-edd-1 finished (exit 0); review the PR."
    }
  ]
};

function screen(name, w, h) {
  const f = makeFrame(name, { fill: "surface/canvas", w: w, h: h });
  f.clipsContent = true;
  PAGES.screens.appendChild(f);
  return f;
}

function screenLabel(page, text, x, y) {
  const t = makeText(text, "Fleetglint/Mono/Meta 12", "text/meta", "screen-label");
  t.x = x;
  t.y = y;
  page.appendChild(t);
}

function runRow(parent, run, x, y, width, density) {
  const row = instantiate("RunRow", { density: density || "compact", interaction: "rest" }, parent);
  resizeInstance(row, width, density === "default" ? 32 : 28);
  const badge = row.findOne(function (n) {
    return n.name === "badge";
  });
  if (badge) {
    try {
      badge.setProperties({ state: run.state, size: "sm", age: "none" });
    } catch (e) {
      warnings.push("could not set badge variant: " + e.message);
    }
  }
  setText(row, "title", run.title);
  setText(row, "agent", run.model);
  setText(row, "role", run.role);
  setText(row, "project", run.project);
  setText(row, "age", run.age);
  setText(row, "note", run.note);
  row.x = x;
  row.y = y;
  return row;
}

function jobRow(parent, job, x, y, width, density) {
  const row = instantiate("JobRow", { density: density || "compact" }, parent);
  resizeInstance(row, width, density === "default" ? 32 : 28);
  const badge = row.findOne(function (n) {
    return n.name === "badge";
  });
  if (badge) {
    try {
      badge.setProperties({ state: job.state, size: "sm", age: "none" });
    } catch (e) {
      warnings.push("could not set job badge variant: " + e.message);
    }
  }
  setText(row, "command", job.command);
  setText(row, "kind", job.kind);
  setText(row, "run", "run · " + job.run);
  setText(row, "exit", job.exit);
  row.x = x;
  row.y = y;
  return row;
}

function inboxItem(parent, item, x, y, width) {
  const node = instantiate("InboxItem", { tone: item.tone }, parent);
  resizeInstance(node, width, node.height);
  const badge = node.findOne(function (n) {
    return n.name === "badge";
  });
  if (badge) {
    const badgeState = item.tone === "action" ? "attention" : item.tone === "acked" ? "inbox-acked" : "inbox-open";
    try {
      badge.setProperties({ state: badgeState, size: "sm", age: "none" });
    } catch (e) {
      warnings.push("could not set inbox badge variant: " + e.message);
    }
  }
  setText(node, "role", item.role);
  setText(node, "kind", item.outcome ? item.kind + " · " + item.outcome : item.kind);
  setText(node, "age", item.age);
  setText(node, "detail", item.detail);
  const subject = node.findOne(function (n) {
    return n.name === "subject";
  });
  if (subject) {
    let kind = "record";
    if (item.subject.indexOf("PR ·") === 0) kind = "external";
    try {
      subject.setProperties({ kind: kind });
    } catch (e) {
      warnings.push("could not set subject variant: " + e.message);
    }
    setText(subject, "ref", item.subject);
    setText(subject, "meta", item.outcome || "");
  }
  node.x = x;
  node.y = y;
  return node;
}

function countTile(parent, key, x, y, w, h) {
  const tile = instantiate("CountTile", { key: key }, parent);
  resizeInstance(tile, w, h);
  tile.x = x;
  tile.y = y;
  return tile;
}

function topBar(parent, source, w, y) {
  const bar = instantiate("TopBar", { source: source }, parent);
  resizeInstance(bar, w, 44);
  if (w < 500) {
    ["source-1", "refresh"].forEach(function (name) {
      const n = bar.findOne(function (child) {
        return child.name === name;
      });
      if (n) n.visible = false;
    });
  }
  bar.x = 0;
  bar.y = y || 0;
  return bar;
}

function textAt(parent, content, styleName, fill, x, y, name) {
  const t = makeText(content, styleName, fill, name || "label");
  parent.appendChild(t);
  t.x = x;
  t.y = y;
  return t;
}

function panel(parent, name, x, y, w, h) {
  const p = makeFrame(name, {
    layout: "VERTICAL",
    gap: 8,
    padX: 12,
    padY: 12,
    fill: "surface/panel",
    stroke: "line/divider",
    strokeWeight: 1,
    radius: TOKENS.geometry.radiusPanel
  });
  p.primaryAxisSizingMode = "FIXED";
  p.counterAxisSizingMode = "FIXED";
  p.resize(w, h);
  p.appendChild(makeText(name, "Fleetglint/UI/Heading 16", "text/primary", "heading"));
  parent.appendChild(p);
  p.x = x;
  p.y = y;
  return p;
}

function buildOverview(page, x, y, narrow) {
  const w = narrow ? 390 : 1440;
  const h = narrow ? 844 : 900;
  const f = screen("Overview — " + w + "×" + h, w, h);
  f.x = x;
  f.y = y;
  const pad = narrow ? 16 : 32;
  topBar(f, "discontinuity", w);

  textAt(f, "Overview", narrow ? "Fleetglint/UI/Heading 16" : "Fleetglint/UI/Heading 20", "text/primary", pad, 64);
  textAt(f, "3 projects · 8 runs · 3 jobs · read-only · last refresh 2s ago", "Fleetglint/UI/Meta 12", "text/meta", pad, narrow ? 88 : 94);

  const tileW = narrow ? Math.floor((w - pad * 3) / 2) : 250;
  const tileH = narrow ? 88 : 96;
  const tileKeys = ["running", "waiting", "attention", "stale-lost-unknown"];
  const tileNumbers = ["3", "1", "2", "3"];
  for (let i = 0; i < tileKeys.length; i++) {
    const tx = narrow ? pad + (i % 2) * (tileW + 12) : pad + i * (tileW + 16);
    const ty = narrow ? 112 + Math.floor(i / 2) * (tileH + 12) : 124;
    const tile = countTile(f, tileKeys[i], tx, ty, tileW, tileH);
    setText(tile, "number", tileNumbers[i]);
  }

  let cy = narrow ? 112 + 2 * (tileH + 12) + 24 : 250;
  const groups = {};
  const order = [];
  for (let i = 0; i < DATA.runs.length; i++) {
    const p = DATA.runs[i].project;
    if (!groups[p]) {
      groups[p] = [];
      order.push(p);
    }
    groups[p].push(DATA.runs[i]);
  }

  for (let g = 0; g < order.length; g++) {
    if (cy > h - 180) break;
    const project = order[g];
    const runs = groups[project];
    textAt(f, project, "Fleetglint/UI/Row Strong 13", "text/primary", pad, cy);
    textAt(f, runs.length + " runs", "Fleetglint/UI/Meta 12", "text/meta", pad + (narrow ? 130 : 170), cy + 2);
    cy += narrow ? 24 : 28;
    for (let r = 0; r < runs.length; r++) {
      if (narrow) {
        mobileRow(f, runs[r], pad, cy, w - pad * 2);
        cy += 52;
      } else {
        runRow(f, runs[r], pad, cy, w - pad * 2, "compact");
        cy += 28;
      }
    }
    cy += narrow ? 14 : 20;
  }

  const terminal = "done 3 · failed 1 · cancelled 0 — terminal runs collapsed";
  textAt(f, terminal, "Fleetglint/UI/Meta 12", "text/disabled", pad, h - 64);
  textAt(f, "click a row for the record · no actions in this build", "Fleetglint/UI/Meta 12", "text/disabled", pad, h - 40);
  return f;
}

function mobileRow(parent, run, x, y, width) {
  const row = makeFrame("run " + run.id, {
    layout: "HORIZONTAL",
    gap: 8,
    padX: 8,
    padY: 8,
    align: "CENTER",
    fill: "surface/panel",
    radius: 4
  });
  row.primaryAxisSizingMode = "FIXED";
  row.counterAxisSizingMode = "AUTO";
  row.strokes = [paint("line/divider")];
  row.strokeWeight = 1;
  row.resize(width, 1);
  const badge = instantiate("StateBadge", { state: run.state, size: "sm", age: "none" }, row);
  badge.name = "badge";
  const col = makeFrame("col", { layout: "VERTICAL", gap: 2 });
  col.fills = [];
  col.primaryAxisSizingMode = "FIXED";
  col.counterAxisSizingMode = "AUTO";
  col.layoutGrow = 1;
  const title = makeText(run.title, "Fleetglint/UI/Row 13", "text/primary", "title");
  title.textAutoResize = "HEIGHT";
  title.layoutAlign = "STRETCH";
  truncate(title);
  col.appendChild(title);
  col.appendChild(makeText(run.model + " · " + run.role, "Fleetglint/Mono/Meta 12", "text/meta", "meta"));
  row.appendChild(col);
  row.appendChild(makeText(run.age, "Fleetglint/Mono/Meta 12", "text/meta", "age"));
  parent.appendChild(row);
  row.x = x;
  row.y = y;
  return row;
}

function buildRunDetail(page, x, y) {
  const w = 1440;
  const h = 900;
  const f = screen("Run detail — 1440×900", w, h);
  f.x = x;
  f.y = y;
  topBar(f, "discontinuity", w);

  textAt(f, "Overview / eddington-1919 / run · ds-edd-1-20261105-053128", "Fleetglint/Mono/Meta 12", "text/meta", 32, 60);
  textAt(f, "store-blink: fix the blinking store badge", "Fleetglint/UI/Heading 20", "text/primary", 32, 82);
  const transition = plainInstance("StateTransition", f);
  transition.x = 32;
  transition.y = 120;
  setText(transition, "from", "running");
  setText(transition, "to", "stale 42m");
  textAt(f, "claude-code · deepseek-flash · effort medium", "Fleetglint/Mono/Meta 12", "text/secondary", 240, 124);
  textAt(f, "role edd-lead · source my-workflow@mbp · started 05:31 · updated 05:47", "Fleetglint/Mono/Meta 12", "text/meta", 32, 152);

  const rel = plainInstance("RelationshipTree", f);
  rel.x = 32;
  rel.y = 188;

  const jobsPanel = panel(f, "Owned jobs", 32, 360, 848, 160);
  for (let i = 0; i < DATA.jobs.length; i++) {
    jobRow(jobsPanel, DATA.jobs[i], 0, 0, 824, "compact");
  }

  const history = panel(f, "Version history", 32, 530, 848, 170);
  const versions = [
    "05:31:28  running  · position 4  · source my-workflow@mbp",
    "05:31:30  running  · process pid 42247 observed",
    "05:47:40  done     · exit 0 · ended 05:47:40",
    "05:47:42  done     · record refreshed (no change)"
  ];
  for (let i = 0; i < versions.length; i++) {
    history.appendChild(makeText(versions[i], "Fleetglint/Mono/Meta 12", "text/secondary", "version-" + i));
  }

  const raw = panel(f, "Raw fields (redacted)", 32, 700, 848, 170);
  raw.appendChild(makeText('{"v":1,"type":"run","id":"ds-edd-1-20261105-053128",', "Fleetglint/Mono/Meta 12", "text/mono-data", "raw-1"));
  raw.appendChild(makeText(' "state":"done","exit_code":0,"agent":"claude-code",', "Fleetglint/Mono/Meta 12", "text/mono-data", "raw-2"));
  raw.appendChild(makeText(' "model":"deepseek-flash","usage":{"basis":"measured",', "Fleetglint/Mono/Meta 12", "text/mono-data", "raw-3"));
  raw.appendChild(makeText(' "input_tokens":182340,"cost":{"basis":"api_equivalent"}}}', "Fleetglint/Mono/Meta 12", "text/mono-data", "raw-4"));
  raw.appendChild(makeText(' "links":[{"label":"worker log","path":"…/[redacted].log"}]}', "Fleetglint/Mono/Meta 12", "text/mono-data", "raw-5"));

  const evidence = panel(f, "Evidence", 912, 188, 496, 150);
  const chip = instantiate("SourceChip", { status: "ok" }, evidence);
  chip.name = "source";
  setText(chip, "source", "my-workflow@mbp");
  const ev = instantiate("EvidenceLabel", { kind: "process" }, evidence);
  ev.name = "evidence";
  setText(ev, "text", "pid ok 12s");
  evidence.appendChild(makeText("observed_at 05:47:40 · stale_after_s 1800", "Fleetglint/Mono/Meta 12", "text/meta", "observed"));

  const usage = panel(f, "Usage", 912, 360, 496, 150);
  usage.appendChild(makeText("input 182,340 (cached 120,000) · output 9,120", "Fleetglint/Mono/Data 13", "text/mono-data", "tokens"));
  usage.appendChild(makeText("cost 1.85 USD · basis api_equivalent", "Fleetglint/Mono/Data 13", "text/mono-data", "cost"));
  usage.appendChild(makeText("usage basis: measured", "Fleetglint/UI/Meta 12", "text/meta", "basis"));

  const log = instantiate("LogTail", { kind: "redacted" }, f);
  resizeInstance(log, 496, 140);
  log.x = 912;
  log.y = 530;
  setText(log, "line-1", "env DEEPSEEK_API_KEY=[redacted]");

  const link = instantiate("RefLink", { kind: "external" }, f);
  link.x = 912;
  link.y = 700;
  setText(link, "ref", "PR · nurockplayer/eddington-1919#176");

  return f;
}

function buildAttention(page, x, y) {
  const w = 1440;
  const h = 900;
  const f = screen("Needs attention — 1440×900", w, h);
  f.x = x;
  f.y = y;
  topBar(f, "discontinuity", w);

  textAt(f, "Needs attention", "Fleetglint/UI/Heading 20", "text/primary", 32, 64);
  textAt(f, "who must act, about what · 6 open items", "Fleetglint/UI/Meta 12", "text/meta", 32, 94);

  const banner = instantiate("Banner", { kind: "discontinuity" }, f);
  resizeInstance(banner, 1376, 44);
  banner.x = 32;
  banner.y = 120;

  let cy = 184;
  textAt(f, "Action required (1)", "Fleetglint/UI/Heading 16", "state/attention/fg", 32, cy);
  cy += 26;
  const action = DATA.inbox.filter(function (i) {
    return i.tone === "action";
  })[0];
  inboxItem(f, action, 32, cy, 1376);
  cy += 116;

  textAt(f, "Open (1)", "Fleetglint/UI/Heading 16", "text/primary", 32, cy);
  cy += 26;
  const normal = DATA.inbox.filter(function (i) {
    return i.tone === "normal";
  })[0];
  inboxItem(f, normal, 32, cy, 1376);
  cy += 116;

  textAt(f, "Lost (2)", "Fleetglint/UI/Heading 16", "state/lost/fg", 32, cy);
  cy += 26;
  const lostRun = DATA.runs.filter(function (r) {
    return r.state === "lost";
  })[0];
  runRow(f, lostRun, 32, cy, 1376, "default");
  cy += 32;
  const lostJob = DATA.jobs.filter(function (j) {
    return j.state === "lost";
  })[0];
  jobRow(f, lostJob, 32, cy, 1376, "default");
  cy += 48;

  textAt(f, "Stale / unknown (2)", "Fleetglint/UI/Heading 16", "text/primary", 32, cy);
  cy += 26;
  const staleRun = DATA.runs.filter(function (r) {
    return r.state === "stale";
  })[0];
  const unknownRun = DATA.runs.filter(function (r) {
    return r.state === "unknown";
  })[0];
  runRow(f, staleRun, 32, cy, 1376, "compact");
  cy += 28;
  runRow(f, unknownRun, 32, cy, 1376, "compact");
  cy += 44;

  textAt(f, "Sources (3)", "Fleetglint/UI/Heading 16", "text/primary", 32, cy);
  cy += 28;
  const sourceStates = [
    ["my-workflow@mbp", "discontinuity", "3 bad lines skipped at 05:47 · counts may be incomplete"],
    ["tachiko-harness@mbp", "ok", "read 1,204 records · last append 2s ago"],
    ["fleetglint@ci", "quarantine", "3 lines rejected at ingest · not shown"]
  ];
  for (let i = 0; i < sourceStates.length; i++) {
    const chip = instantiate("SourceChip", { status: sourceStates[i][1] }, f);
    setText(chip, "source", sourceStates[i][0]);
    chip.x = 32;
    chip.y = cy;
    textAt(f, sourceStates[i][2], "Fleetglint/UI/Meta 12", "text/meta", 220, cy + 4);
    cy += 28;
  }

  textAt(f, "acked 1 · stays visible but muted", "Fleetglint/UI/Meta 12", "text/disabled", 32, h - 36);
  return f;
}

function buildUnavailable(page, x, y) {
  const w = 1440;
  const h = 900;
  const f = screen("Unavailable — 1440×900", w, h);
  f.x = x;
  f.y = y;
  topBar(f, "unavailable", w);
  const banner = instantiate("Banner", { kind: "unavailable" }, f);
  resizeInstance(banner, 1376, 44);
  banner.x = 32;
  banner.y = 64;
  textAt(f, "The source cannot be read", "Fleetglint/UI/Heading 20", "text/primary", 32, 150);
  textAt(f, "Retry is automatic on the next refresh; this board has no action to take.", "Fleetglint/UI/Meta 12", "text/meta", 32, 184);
  const empty = plainInstance("EmptyState", f);
  empty.x = 32;
  empty.y = 230;
  setText(empty, "title", "Nothing to show");
  setText(empty, "body", "The board shows no cached or sample data while a source is unreadable.");
  setText(empty, "path", "adapter: tachiko-harness@mbp · error: EACCES reading segment file");
  return f;
}

function buildEmpty(page, x, y) {
  const w = 1440;
  const h = 900;
  const f = screen("Empty — 1440×900", w, h);
  f.x = x;
  f.y = y;
  topBar(f, "ok", w);
  textAt(f, "No sources yet", "Fleetglint/UI/Heading 20", "text/primary", 32, 64);
  const empty = plainInstance("EmptyState", f);
  empty.x = 400;
  empty.y = 260;
  textAt(f, 'the one-line hint: write NDJSON here → ~/.local/state/fleetglint/records/', "Fleetglint/Mono/Meta 12", "text/meta", 32, 180);
  return f;
}

async function buildScreens(page) {
  await figma.setCurrentPageAsync(page);
  currentItem = "Overview desktop";
  screenLabel(page, "Overview — desktop 1440×900", 0, -28);
  buildOverview(page, 0, 0, false);
  currentItem = "Run detail";
  screenLabel(page, "Run detail — 1440×900", 1560, -28);
  buildRunDetail(page, 1560, 0);
  currentItem = "Needs attention";
  screenLabel(page, "Needs attention — 1440×900", 3120, -28);
  buildAttention(page, 3120, 0);
  currentItem = "Overview 390";
  screenLabel(page, "Overview — 390 wide", 0, 992);
  buildOverview(page, 0, 1020, true);
  currentItem = "Unavailable";
  screenLabel(page, "Unavailable — 1440×900", 480, 992);
  buildUnavailable(page, 480, 1020);
  currentItem = "Empty";
  screenLabel(page, "Empty — 1440×900", 2000, 992);
  buildEmpty(page, 2000, 1020);
  currentItem = "";
}

/* ------------------------------------------------------------------ main */

async function build() {
  currentStep = "check file";
  if (!figma.root.name.includes("Fleetglint")) {
    refusedFile = true;
    throw new Error(
      'refusing to run on "' + figma.root.name + '": file name must contain "Fleetglint"'
    );
  }
  currentStep = "load pages";
  if (typeof figma.loadAllPagesAsync === "function") {
    try {
      await figma.loadAllPagesAsync();
    } catch (e) {
      /* older API: all pages are already loaded */
    }
  }
  currentStep = "fonts";
  await loadFonts();
  currentStep = "pages";
  await preparePages();
  currentStep = "text styles";
  await buildTextStyles();
  currentStep = "variables";
  await syncVariables();

  currentStep = "foundations";
  await buildFoundations(PAGES.foundations);
  currentStep = "components";
  await buildComponents(PAGES.components);
  currentStep = "screens";
  await buildScreens(PAGES.screens);
  currentStep = "text styles (bind)";
  await applyTextStyles();
  currentStep = "done";

  await figma.setCurrentPageAsync(PAGES.screens);

  const setCount = Object.keys(COMPONENT_SETS).length;
  const plainCount = Object.keys(COMPONENTS).length;
  let componentCount = plainCount;
  Object.keys(COMPONENT_SETS).forEach(function (name) {
    componentCount += COMPONENT_SETS[name].children.filter(function (n) {
      return n.type === "COMPONENT";
    }).length;
  });
  const warningText = warnings.length ? " " + warnings.length + " warning(s): " + warnings.slice(0, 3).join("; ") : "";
  return (
    "Fleetglint v0.1 built: " +
    pagesCount +
    " pages, 2 variable collections, " +
    Object.keys(STYLES).length +
    " text styles, " +
    setCount +
    " component sets + " +
    plainCount +
    " components (" +
    componentCount +
    " components in total), 6 screens." +
    warningText
  );
}

async function pickLogFont() {
  const candidates = [
    { family: "Inter", style: "Regular" },
    { family: "Roboto", style: "Regular" }
  ];
  for (let i = 0; i < candidates.length; i++) {
    try {
      await figma.loadFontAsync(candidates[i]);
      return candidates[i];
    } catch (e) {
      /* try the next family */
    }
  }
  try {
    const fonts = await figma.listAvailableFontsAsync();
    if (fonts && fonts.length) return fonts[0].fontName;
  } catch (e) {
    /* none available */
  }
  return null;
}

function buildLogContent(result, error, summary) {
  return [
    "fleetglint build log",
    "time: " + new Date().toISOString(),
    "result: " + result,
    "step: " + currentStep + (currentItem ? " (" + currentItem + ")" : ""),
    "error: " + (error && error.message ? error.message : "none"),
    "stack: " +
      (error && error.stack ? String(error.stack).replace(/\n/g, " | ").slice(0, 1500) : "none"),
    "warnings: " + (warnings.length ? warnings.join(" | ") : "none"),
    "summary: " + (summary || "none")
  ].join("\n");
}

async function writeBuildLog(result, error, summary) {
  const content = buildLogContent(result, error, summary);
  const font = await pickLogFont();

  const place = async function (page) {
    await page.loadAsync();
    let log = null;
    const kids = page.children;
    for (let i = 0; i < kids.length; i++) {
      if (kids[i].type === "TEXT" && kids[i].name === "fleetglint-build-log") {
        log = kids[i];
        break;
      }
    }
    if (!log) {
      log = figma.createText();
      page.appendChild(log);
      log.name = "fleetglint-build-log";
    }
    if (font) {
      try {
        log.fontName = font;
      } catch (e) {
        /* keep the default font */
      }
    }
    log.characters = content;
    log.textAutoResize = "WIDTH_AND_HEIGHT";
    log.fills = [{ type: "SOLID", color: hexToRgba("#E8EEF6") }];
    log.x = 16;
    log.y = 16;
  };

  try {
    let page = null;
    const pages = figma.root.children.filter(function (n) {
      return n.type === "PAGE";
    });
    for (let i = 0; i < pages.length; i++) {
      if (pages[i].name === "Foundations") page = pages[i];
    }
    if (!page) {
      page = figma.createPage();
      page.name = "Foundations";
    }
    await figma.setCurrentPageAsync(page);
    await place(page);
  } catch (e) {
    console.error("fleetglint build log: primary placement failed: " + e.message);
    try {
      const page = figma.root.children[0];
      if (page) {
        await figma.setCurrentPageAsync(page);
        await place(page);
      }
    } catch (e2) {
      console.error("fleetglint build log: fallback placement failed: " + e2.message);
    }
  }
}

(async function main() {
  let summary = "";
  try {
    summary = await build();
    await writeBuildLog("ok", null, summary);
    figma.closePlugin(summary);
  } catch (e) {
    const message = e && e.message ? e.message : String(e);
    console.error("Fleetglint build failed at step " + currentStep + ": " + message);
    if (e && e.stack) console.error(e.stack);
    if (!refusedFile) {
      try {
        await writeBuildLog("failed", e, message);
      } catch (e2) {
        console.error("fleetglint build log failed: " + e2.message);
      }
    }
    figma.closePlugin("Fleetglint build failed: " + message);
  }
})();

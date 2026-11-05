# Fleetglint Figma plugin

A local Figma development plugin that builds the Fleetglint design system
(variables, text styles, components and screens) from the token object at the
top of `code.js`. It runs entirely inside Figma: no network access, no other
file is touched.

## Import and run (about two minutes)

1. Open Figma desktop and open the **Fleetglint Design System** file:
   <https://www.figma.com/design/ImzDcmpKT8i3XnwIx0ftpB>.
   The file name must contain `Fleetglint`; the plugin refuses to run
   anywhere else.
2. Menu **Plugins → Development → Import plugin from manifest…**, and choose
   `design/figma-plugin/manifest.json` from this repository.
   **After the 2026-11-05 manifest change, re-import it once**: Figma caches
   the manifest, and `documentAccess: dynamic-page` only takes effect after a
   re-import.
3. Menu **Plugins → Development → Fleetglint Design System**.
4. Wait a few seconds. The plugin builds or rebuilds the pages
   `Foundations`, `Components` and `Screens`, then closes with a summary such
   as `Fleetglint v0.1 built: 3 pages, 2 variable collections, …`.
5. Open the pages in order: `Foundations` for the tokens and the state
   legend, `Components` for the variant sets, `Screens` for the six frames.

Every run, successful or not, writes a text node `fleetglint-build-log` at
the top-left of `Foundations` (page 16,16) with the UTC timestamp, result,
step, error message and stack, warnings and the summary. If the build fails
and the toast is gone, read that node first.

## Re-running

Run the same menu item again. It clears only its own three pages, updates its
own variable collections (`Primitives`, `Semantic`) by name, and rebuilds
everything from `code.js`. Other pages and variables are left alone.

## Changing tokens

Edit the `TOKENS` object between the `// TOKENS-START` and `// TOKENS-END`
markers in `code.js`, then run the contrast check from the repository root:

```
orb-test --memory 1g --cpus 1 -- node design/figma-plugin/contrast-check.mjs
```

It reads the same object, so code and check cannot drift apart.

## Fonts

The plugin loads Inter for UI text and JetBrains Mono for data. If a font is
missing it falls back (Roboto / Arial, then Roboto Mono / IBM Plex Mono) and
says so in the closing summary.

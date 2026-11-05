import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = dirname(fileURLToPath(import.meta.url));
const NOT_APP = new Set(["test-setup.ts", "test-fixtures.ts", "test-fetcher.ts"]);

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (name !== "fixtures") sourceFiles(path, out);
    } else if (
      /\.(ts|tsx)$/.test(name) &&
      !/\.test\.(ts|tsx)$/.test(name) &&
      !NOT_APP.has(name)
    ) {
      out.push(path);
    }
  }
  return out;
}

const files = sourceFiles(SRC).map((path) => ({
  path,
  text: readFileSync(path, "utf8"),
}));

describe("read-only app", () => {
  it("contains no non-GET request anywhere in the app source", () => {
    for (const { path, text } of files) {
      expect(text, path).not.toMatch(/\bmethod\s*:/);
      expect(text, path).not.toMatch(/\b(XMLHttpRequest|sendBeacon)\b/);
      expect(text, path).not.toMatch(/\b(POST|PUT|PATCH|DELETE)\b/);
      expect(text, path).not.toMatch(/["'`]file:\/\//);
    }
  });

  it("has no onClick handler in a file that also sends a request", () => {
    for (const { path, text } of files) {
      if (text.includes("onClick")) {
        expect(text, path).not.toContain("fetch(");
      }
    }
  });

  it("only the API client module calls fetch()", () => {
    const callers = files
      .filter(({ text }) => text.includes("fetch("))
      .map(({ path }) => path.replace(`${SRC}/`, ""));
    expect(callers).toEqual(["api/client.ts"]);
  });
});

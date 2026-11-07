import { render, screen, waitFor } from "@testing-library/react";
import { App } from "./App";
import { board, snapshot } from "./test-fixtures";
import { jsonResponse, notModified, routeFetcher, sequenceFetcher } from "./test-fetcher";

const TITLE = "Rebuild the viewer board";
// Under a loaded host a poll cycle can take longer than the default 1 s.
const SLOW = { timeout: 5000 };

const demoBoard = { ...board, demo: true };

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("App polling", () => {
  it("shows Unavailable on a network failure and keeps old data marked out of date", async () => {
    const { fetcher } = sequenceFetcher([
      () => jsonResponse(board),
      () => Promise.reject(new TypeError("Failed to fetch")),
      () => Promise.reject(new TypeError("Failed to fetch")),
    ]);
    render(<App fetcher={fetcher} pollMs={200} />);

    const alert = await screen.findByRole("alert", undefined, SLOW);
    expect(alert).toHaveTextContent("Failed to fetch");
    expect(alert).toHaveTextContent(/last successful refresh \d{2}:\d{2}/);
    expect(alert).toHaveTextContent("current state cannot be verified");
    expect(screen.getByText(TITLE)).toBeInTheDocument();
    expect(document.querySelector(".stale-data.is-stale")).toBeTruthy();
  });

  it("shows Unavailable on HTTP 500 without presenting old data as current", async () => {
    const { fetcher } = sequenceFetcher([
      () => jsonResponse(board),
      () => jsonResponse({ api: 1, error: { code: "internal", message: "boom" } }, 500),
    ]);
    render(<App fetcher={fetcher} pollMs={200} />);

    const alert = await screen.findByRole("alert", undefined, SLOW);
    expect(alert).toHaveTextContent("HTTP 500");
    expect(alert).toHaveTextContent("current state cannot be verified");
    expect(screen.getByText(TITLE)).toBeInTheDocument();
    expect(document.querySelector(".stale-data.is-stale")).toBeTruthy();
  });

  it("recovers automatically on the next good poll", async () => {
    // The third poll waits for the test, so a slow machine cannot clear the
    // banner before the assertion sees it.
    let release: (response: Response) => void = () => {};
    const recovered = new Promise<Response>((resolve) => {
      release = resolve;
    });
    const { fetcher } = sequenceFetcher([
      () => jsonResponse(board),
      () => Promise.reject(new TypeError("Failed to fetch")),
      () => recovered,
    ]);
    render(<App fetcher={fetcher} pollMs={20} />);

    expect(await screen.findByRole("alert", undefined, SLOW)).toBeInTheDocument();
    release(jsonResponse(board));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(document.querySelector(".stale-data.is-stale")).toBeNull();
    expect(screen.getByText(TITLE)).toBeInTheDocument();
  });

  it("keeps data on 304 and sends If-None-Match", async () => {
    const tag = 'W/"7-1234"';
    const { fetcher, calls } = sequenceFetcher([
      () => jsonResponse(board, 200, { ETag: tag }),
      () => notModified(tag),
    ]);
    render(<App fetcher={fetcher} pollMs={20} />);

    expect(await screen.findByText(TITLE, undefined, SLOW)).toBeInTheDocument();
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(2));
    expect(calls[0].url).toBe("/api/board");

    const headers = calls[1].init?.headers as unknown as Record<string, string>;
    expect(headers["If-None-Match"]).toBe(tag);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText(TITLE)).toBeInTheDocument();
  });

  it("keeps a permanent sample-data banner for a demo board", async () => {
    const { fetcher, calls } = sequenceFetcher([() => jsonResponse(demoBoard)]);
    render(<App fetcher={fetcher} pollMs={20} />);

    expect(
      await screen.findByText(
        /Sample records from fleetglint demo · not real work/,
        undefined,
        SLOW,
      ),
    ).toBeInTheDocument();
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(2));
    expect(
      screen.getByText(/Sample records from fleetglint demo · not real work/),
    ).toBeInTheDocument();
  });

  it("shows a skeleton before the first board arrives", () => {
    const fetcher = () => new Promise<Response>(() => {});
    const { unmount } = render(<App fetcher={fetcher} />);
    expect(document.querySelector(".overview-skeleton")).toBeTruthy();
    expect(screen.queryByText(TITLE)).toBeNull();
    unmount();
  });

  it("redirects /attention to the overview", async () => {
    window.history.replaceState(null, "", "/attention");
    const { fetcher } = sequenceFetcher([() => jsonResponse(board)]);
    render(<App fetcher={fetcher} pollMs={200} />);

    await waitFor(() => expect(window.location.pathname).toBe("/"));
    expect(await screen.findByText(TITLE, undefined, SLOW)).toBeInTheDocument();
  });

  it("serves the plain record list at /history", async () => {
    window.history.replaceState(null, "", "/history");
    const fetcher = routeFetcher({
      "/api/board": () => jsonResponse(board),
      "/api/snapshot": () => jsonResponse(snapshot),
    });
    render(<App fetcher={fetcher} pollMs={200} />);

    expect(await screen.findByRole("heading", { name: "History" }, SLOW)).toBeInTheDocument();
    expect(
      screen.getByText("At most 500 records per list; older records are not shown."),
    ).toBeInTheDocument();
  });
});

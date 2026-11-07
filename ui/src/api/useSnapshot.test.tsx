import { act, render } from "@testing-library/react";
import { useBoard } from "./useSnapshot";
import type { Fetcher } from "./client";
import { board } from "../test-fixtures";
import { jsonResponse, notModified, sequenceFetcher } from "../test-fetcher";

function Probe({ fetcher, pollMs }: { fetcher: Fetcher; pollMs: number }) {
  const state = useBoard(fetcher, pollMs);
  return (
    <>
      <span data-testid="received-at">{state.receivedAt ?? "null"}</span>
      <span data-testid="running">{state.data?.counts.running ?? "none"}</span>
    </>
  );
}

async function until(predicate: () => boolean) {
  for (let i = 0; i < 100; i += 1) {
    if (predicate()) return;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
  }
  throw new Error("condition not reached");
}

describe("useBoard", () => {
  it("reads /api/board and moves the refresh time to the time of a 304", async () => {
    const tag = 'W/"9-1"';
    const { fetcher, calls } = sequenceFetcher([
      () => jsonResponse(board, 200, { ETag: tag }),
      () => notModified(tag),
    ]);
    const { getByTestId } = render(<Probe fetcher={fetcher} pollMs={60} />);
    const probe = getByTestId("received-at");

    await until(() => probe.textContent !== "null");
    const first = Number(probe.textContent);
    expect(calls[0].url).toBe("/api/board");
    expect(getByTestId("running").textContent).toBe("4");

    // A 304 later on is a successful validation: receivedAt moves forward.
    await until(() => Number(probe.textContent) > first + 40);
    expect(getByTestId("running").textContent).toBe("4");
  });

  it("sends If-None-Match once an ETag is known", async () => {
    const tag = 'W/"3-abc"';
    const { fetcher, calls } = sequenceFetcher([
      () => jsonResponse(board, 200, { ETag: tag }),
      () => notModified(tag),
    ]);
    render(<Probe fetcher={fetcher} pollMs={20} />);

    await until(() => calls.length >= 2);
    const headers = calls[1].init?.headers as unknown as Record<string, string>;
    expect(headers["If-None-Match"]).toBe(tag);
  });
});

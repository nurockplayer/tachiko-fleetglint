import { act, render } from "@testing-library/react";
import { useSnapshot } from "./useSnapshot";
import type { Fetcher } from "./client";
import { snapshot } from "../test-fixtures";
import { jsonResponse, notModified, sequenceFetcher } from "../test-fetcher";

function Probe({ fetcher, pollMs }: { fetcher: Fetcher; pollMs: number }) {
  const state = useSnapshot(fetcher, pollMs);
  return <span data-testid="received-at">{state.receivedAt ?? "null"}</span>;
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

describe("useSnapshot", () => {
  it("moves the refresh time to the time of a 304", async () => {
    const tag = 'W/"9-1"';
    const { fetcher } = sequenceFetcher([
      () => jsonResponse(snapshot, 200, { ETag: tag }),
      () => notModified(tag),
    ]);
    const { getByTestId } = render(<Probe fetcher={fetcher} pollMs={60} />);
    const probe = getByTestId("received-at");

    await until(() => probe.textContent !== "null");
    const first = Number(probe.textContent);

    // A 304 later on is a successful validation: receivedAt moves forward.
    await until(() => Number(probe.textContent) > first + 40);
  });
});

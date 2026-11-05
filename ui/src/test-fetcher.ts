import type { Fetcher } from "./api/client";

/*
 * jsdom does not ship fetch/Response; the app only uses status, ok, headers
 * and json(), so the tests use this minimal stand-in.
 */
class TestResponse {
  readonly status: number;
  readonly headers: { get(name: string): string | null };
  private readonly bodyText: string | null;

  constructor(
    body: string | null,
    init: { status?: number; headers?: Record<string, string> } = {},
  ) {
    this.status = init.status ?? 200;
    this.bodyText = body;
    const headers = init.headers ?? {};
    const lower = new Map(
      Object.entries(headers).map(([key, value]) => [key.toLowerCase(), value]),
    );
    this.headers = { get: (name) => lower.get(name.toLowerCase()) ?? null };
  }

  get ok(): boolean {
    return this.status >= 200 && this.status < 300;
  }

  async json(): Promise<unknown> {
    return JSON.parse(this.bodyText ?? "null");
  }
}

export function jsonResponse(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
): Response {
  return new TestResponse(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  }) as unknown as Response;
}

export function notModified(etag?: string): Response {
  return new TestResponse(null, {
    status: 304,
    headers: etag ? { ETag: etag } : {},
  }) as unknown as Response;
}

export interface FetcherCall {
  url: string;
  init?: RequestInit;
}

export type Handler = () => Response | Promise<Response>;

/** Repeats the last handler once the list is exhausted. */
export function sequenceFetcher(handlers: Handler[]): {
  fetcher: Fetcher;
  calls: FetcherCall[];
} {
  const calls: FetcherCall[] = [];
  let index = 0;
  const fetcher: Fetcher = async (url, init) => {
    calls.push({ url, init });
    const handler = handlers[Math.min(index, handlers.length - 1)];
    index += 1;
    return handler();
  };
  return { fetcher, calls };
}

export function routeFetcher(
  routes: Record<string, () => Response | Promise<Response>>,
): Fetcher {
  return async (url) => {
    for (const [prefix, handler] of Object.entries(routes)) {
      if (url.startsWith(prefix)) return handler();
    }
    return jsonResponse({ api: 1, error: { code: "not_found", message: "no route" } }, 404);
  };
}

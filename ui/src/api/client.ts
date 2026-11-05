export type Fetcher = (input: string, init?: RequestInit) => Promise<Response>;

export const defaultFetcher: Fetcher = (input, init) => fetch(input, init);

export function snapshotUrl(): string {
  return "/api/snapshot";
}

export function recordUrl(params: {
  source_id: string;
  type: string;
  id: string;
}): string {
  const query = new URLSearchParams({
    source_id: params.source_id,
    type: params.type,
    id: params.id,
  });
  return `/api/record?${query.toString()}`;
}

export function fileUrl(params: {
  source_id: string;
  type: string;
  id: string;
  field: "log_path" | "result_path" | "link";
  index?: number;
}): string {
  const query = new URLSearchParams({
    source_id: params.source_id,
    type: params.type,
    id: params.id,
    field: params.field,
  });
  if (params.index != null) query.set("index", String(params.index));
  return `/api/file?${query.toString()}`;
}

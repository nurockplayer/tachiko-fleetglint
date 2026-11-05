import { useEffect, useState } from "react";
import type { RecordType } from "./api/types";

export interface DetailParams {
  source_id: string;
  type: string;
  id: string;
}

export type Route =
  | { kind: "overview" }
  | { kind: "attention" }
  | { kind: "detail"; params: DetailParams };

export function parseRoute(location: { pathname: string; search: string }): Route {
  if (location.pathname === "/attention") return { kind: "attention" };
  if (location.pathname === "/run") {
    const query = new URLSearchParams(location.search);
    const source_id = query.get("source_id");
    const type = query.get("type");
    const id = query.get("id");
    if (source_id && type && id) {
      return { kind: "detail", params: { source_id, type, id } };
    }
  }
  return { kind: "overview" };
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location));
    window.addEventListener("popstate", onChange);
    return () => window.removeEventListener("popstate", onChange);
  }, []);
  return route;
}

export function detailHref(ref: {
  type: RecordType | string;
  id: string;
  source_id: string;
}): string {
  const query = new URLSearchParams({
    source_id: ref.source_id,
    type: ref.type,
    id: ref.id,
  });
  return `/run?${query.toString()}`;
}

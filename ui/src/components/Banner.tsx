import type { ReactNode } from "react";

export type BannerKind = "unavailable" | "demo";

const LABEL: Record<BannerKind, string> = {
  unavailable: "Unavailable",
  demo: "Demo",
};

/** One restrained banner; the unavailable one is the app's only alert. */
export function Banner({ kind, children }: { kind: BannerKind; children: ReactNode }) {
  return (
    <div
      className={`banner banner-${kind}`}
      role={kind === "unavailable" ? "alert" : "status"}
      data-banner={kind}
    >
      <strong>{LABEL[kind]}</strong>
      <span>{children}</span>
    </div>
  );
}

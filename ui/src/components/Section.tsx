import type { ReactNode } from "react";

export interface SectionProps {
  id: string;
  heading: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  ariaLabel?: string;
}

/** A plain section whose heading states what its rows share. */
export function Section({ id, heading, aside, children, ariaLabel }: SectionProps) {
  return (
    <section className="section" id={id} aria-label={ariaLabel ?? id}>
      <div className="section-head">
        <h2 className="section-heading">{heading}</h2>
        {aside ? <span className="section-aside">{aside}</span> : null}
      </div>
      {children}
    </section>
  );
}

export interface CollapsibleSectionProps extends SectionProps {
  summary?: ReactNode;
  subline?: ReactNode;
  open: boolean;
  onToggle: () => void;
}

/**
 * A section that keeps its expanded state outside itself (the screen owns it),
 * so a refresh never collapses it back.
 */
export function CollapsibleSection({
  id,
  heading,
  summary,
  subline,
  open,
  onToggle,
  children,
  ariaLabel,
}: CollapsibleSectionProps) {
  return (
    <section className="section" id={id} aria-label={ariaLabel ?? id}>
      <div className="section-head">
        <h2 className="section-heading">{heading}</h2>
        {summary ? <span className="section-summary">{summary}</span> : null}
        <button
          type="button"
          className="section-toggle"
          aria-expanded={open}
          aria-controls={`${id}-body`}
          onClick={onToggle}
        >
          {open ? "[hide]" : "[show]"}
        </button>
      </div>
      {subline ? <div className="section-subline">{subline}</div> : null}
      {open ? (
        <div className="section-body" id={`${id}-body`}>
          {children}
        </div>
      ) : null}
    </section>
  );
}

import type { ReactElement } from "react";
import type { DisplayState } from "../api/types";
import { STATE_GLYPH, STATE_LABEL, type BadgeState } from "../states";

const svgProps = {
  width: 12,
  height: 12,
  viewBox: "0 0 16 16",
  "aria-hidden": true,
} as const;

function glyphFor(state: BadgeState): ReactElement {
  switch (STATE_GLYPH[state]) {
    case "ring":
      return (
        <svg {...svgProps}>
          <circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      );
    case "dot":
      return (
        <svg {...svgProps}>
          <circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <circle cx="8" cy="8" r="2.6" fill="currentColor" />
        </svg>
      );
    case "arrow":
      return (
        <svg {...svgProps}>
          <path
            d="M2 8h9M8 4.5 11.5 8 8 11.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "check":
      return (
        <svg {...svgProps}>
          <path
            d="M3.5 8.5l3 3 6-7"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "cross":
      return (
        <svg {...svgProps}>
          <path
            d="M4 4l8 8M12 4l-8 8"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      );
    case "slash":
      return (
        <svg {...svgProps}>
          <path
            d="M4 12L12 4"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      );
    case "dashed-ring":
      return (
        <svg {...svgProps}>
          <circle
            cx="8"
            cy="8"
            r="5.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeDasharray="2.4 1.8"
          />
        </svg>
      );
    case "broken-link":
      return (
        <svg {...svgProps}>
          <path
            d="M6.5 3.5 5 5a4.2 4.2 0 0 0 0 6l1.5 1.5M9.5 12.5 11 11a4.2 4.2 0 0 0 0-6L9.5 3.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
      );
    case "question":
      return (
        <svg {...svgProps}>
          <text
            x="8"
            y="12"
            textAnchor="middle"
            fontSize="12"
            fontFamily="var(--font-mono)"
            fill="currentColor"
          >
            ?
          </text>
        </svg>
      );
    case "bang":
      return (
        <svg {...svgProps}>
          <rect x="2" y="3" width="2" height="10" fill="currentColor" />
          <text
            x="9.5"
            y="12"
            textAnchor="middle"
            fontSize="12"
            fontFamily="var(--font-mono)"
            fill="currentColor"
          >
            !
          </text>
        </svg>
      );
    case "open-dot":
      return (
        <svg {...svgProps}>
          <circle cx="8" cy="8" r="3.6" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      );
    case "acked-dot":
      return (
        <svg {...svgProps}>
          <circle cx="8" cy="8" r="3.6" fill="currentColor" opacity="0.7" />
        </svg>
      );
    case "clock":
      return (
        <svg {...svgProps}>
          <circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
          <path
            d="M8 4.5V8l2.4 1.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
          />
        </svg>
      );
    case "crescent":
      return (
        <svg {...svgProps}>
          <path
            d="M10.5 3a5.5 5.5 0 1 0 0 10 4.4 4.4 0 0 1 0-10z"
            fill="currentColor"
            opacity="0.8"
          />
        </svg>
      );
    case "square":
      return (
        <svg {...svgProps}>
          <rect x="4.5" y="4.5" width="7" height="7" fill="currentColor" opacity="0.8" />
        </svg>
      );
    default:
      return <svg {...svgProps} />;
  }
}

export interface StateBadgeProps {
  state: BadgeState;
  size?: "sm" | "md";
  age?: string | null;
  title?: string;
}

/**
 * Every display state, encoded by glyph + text label + color. Color is never
 * the only signal: `stale` is also dashed, `unknown` is hatched, `attention`
 * has a leading bar.
 */
export function StateBadge({ state, size = "sm", age, title }: StateBadgeProps) {
  const kind = STATE_GLYPH[state];
  return (
    <span className={`badge badge-${size}`} data-state={state} title={title}>
      <span className="badge-glyph" data-glyph={kind} aria-hidden="true">
        {glyphFor(state)}
      </span>
      <span className="badge-label">{STATE_LABEL[state]}</span>
      {age ? <span className="badge-age">{age}</span> : null}
    </span>
  );
}

export interface StateTransitionProps {
  writerState: string;
  displayState: DisplayState;
  age?: string | null;
  size?: "sm" | "md";
}

/** Shows both states when liveness differs from the writer's claim. */
export function StateTransition({
  writerState,
  displayState,
  age,
  size = "md",
}: StateTransitionProps) {
  if (writerState === displayState) {
    return <StateBadge state={displayState} size={size} age={age} />;
  }
  return (
    <span className="transition" data-writer-state={writerState}>
      <span className="transition-from mono">{writerState}</span>
      <span className="transition-arrow" aria-hidden="true">
        →
      </span>
      <StateBadge state={displayState} size={size} age={age} />
    </span>
  );
}

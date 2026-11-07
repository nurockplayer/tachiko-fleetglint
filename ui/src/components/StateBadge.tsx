import type { ReactElement } from "react";
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
          <circle cx="8" cy="8" r="5" fill="currentColor" />
        </svg>
      );
    case "hourglass":
      return (
        <svg {...svgProps}>
          <path
            d="M4 2.5h8M4 13.5h8M5 2.5v3l3 2.5-3 2.5v3M11 2.5v3L8 8l3 2.5v3"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
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
    case "dashed-circle":
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
          <rect x="7" y="2.5" width="2" height="8" fill="currentColor" />
          <circle cx="8" cy="13" r="1.1" fill="currentColor" />
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
  /** Glyph only, for a section heading that already states the state. */
  variant?: "words" | "glyph";
  age?: string | null;
  title?: string;
}

/**
 * A display state encoded by glyph + words + colour, never colour alone. The
 * glyph-only variant exists for rows under a section heading that names the
 * state; it keeps the words in `aria-label`.
 */
export function StateBadge({ state, variant = "words", age, title }: StateBadgeProps) {
  const label = STATE_LABEL[state];
  const kind = STATE_GLYPH[state];

  if (variant === "glyph") {
    return (
      <span
        className="state-badge is-glyph"
        data-state={state}
        data-glyph={kind}
        role="img"
        aria-label={label}
        title={title ?? label}
      >
        {glyphFor(state)}
      </span>
    );
  }

  return (
    <span className="state-badge" data-state={state} data-glyph={kind} title={title}>
      <span className="state-glyph" aria-hidden="true">
        {glyphFor(state)}
      </span>
      <span className="state-words">{label}</span>
      {age ? <span className="state-age">{age}</span> : null}
    </span>
  );
}

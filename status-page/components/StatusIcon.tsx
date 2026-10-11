import type { DisplayStatus } from "../lib/status.ts";

/**
 * One distinct SHAPE per status, so status never depends on colour alone:
 * check (operational), triangle (degraded), half-filled square (partial
 * outage), octagon with a cross (major outage), clock (maintenance), circled
 * question mark (no data). Always rendered next to the text label; the icon
 * itself is decorative to assistive technology.
 */
export function StatusIcon({ status, size = 18 }: { status: DisplayStatus; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 20 20",
    "aria-hidden": true,
    focusable: false,
    className: `icon s-${status}`,
  } as const;
  switch (status) {
    case "operational":
      return (
        <svg {...common}>
          <circle cx="10" cy="10" r="9" fill="currentColor" />
          <path d="M5.5 10.5l3 3 6-7" fill="none" stroke="var(--surface)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "degraded":
      return (
        <svg {...common}>
          <path d="M10 1.5l9 16.5H1z" fill="currentColor" />
          <path d="M10 7v5" stroke="var(--surface)" strokeWidth="2.2" strokeLinecap="round" />
          <circle cx="10" cy="15" r="1.3" fill="var(--surface)" />
        </svg>
      );
    case "partial_outage":
      return (
        <svg {...common}>
          <rect x="1.5" y="1.5" width="17" height="17" rx="3" fill="none" stroke="currentColor" strokeWidth="2.2" />
          <path d="M2.6 17.4V2.6H10v14.8z" fill="currentColor" />
        </svg>
      );
    case "major_outage":
      return (
        <svg {...common}>
          <path d="M6.3 1h7.4L19 6.3v7.4L13.7 19H6.3L1 13.7V6.3z" fill="currentColor" />
          <path d="M6.8 6.8l6.4 6.4M13.2 6.8l-6.4 6.4" stroke="var(--surface)" strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      );
    case "maintenance":
      return (
        <svg {...common}>
          <circle cx="10" cy="10" r="9" fill="currentColor" />
          <path d="M10 5v5.5l3.5 2" fill="none" stroke="var(--surface)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "unknown":
      return (
        <svg {...common}>
          <circle cx="10" cy="10" r="8" fill="none" stroke="currentColor" strokeWidth="2.2" />
          <path d="M7.6 7.6a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .8-1 1.5v.6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          <circle cx="10" cy="14.6" r="1.2" fill="currentColor" />
        </svg>
      );
  }
}

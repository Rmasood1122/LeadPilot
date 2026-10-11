import type { ComponentView } from "../lib/snapshot.ts";
import { formatDay, formatPercent } from "../lib/format.ts";

function barClass(uptime: number | null): string {
  if (uptime === null) return "bar nodata";
  if (uptime >= 99.9) return "bar s-operational";
  if (uptime >= 99) return "bar s-degraded";
  if (uptime >= 95) return "bar s-partial_outage";
  return "bar s-major_outage";
}

function dayLabel(date: string, uptime: number | null): string {
  return uptime === null ? `${formatDay(date)}: no data` : `${formatDay(date)}: ${formatPercent(uptime)} uptime`;
}

/**
 * 90 daily bars from UptimeRobot. Each bar has a native tooltip (works without
 * JavaScript). The bar row is one image to screen readers with a summary
 * label; the days below 100% are also listed as text in a disclosure.
 */
export function UptimeBars({ name, uptime }: { name: string; uptime: NonNullable<ComponentView["uptime"]> }) {
  const known = uptime.days.filter((d) => d.uptime !== null);
  const imperfect = uptime.days.filter((d) => d.uptime !== null && d.uptime < 100);
  const ratio = uptime.ratio;
  const summary =
    known.length === 0
      ? "No uptime data yet"
      : `${ratio !== null ? formatPercent(ratio) : "Unknown"} uptime over the last 90 days`;
  return (
    <div className="uptime">
      <div className="bars" role="img" aria-label={`${name}: ${summary}. ${imperfect.length} of ${known.length} measured days below 100%.`}>
        {uptime.days.map((d) => (
          <span key={d.date} className={barClass(d.uptime)} title={dayLabel(d.date, d.uptime)} />
        ))}
      </div>
      <div className="bars-legend" aria-hidden="true">
        <span>90 days ago</span>
        <span>{summary}</span>
        <span>Today</span>
      </div>
      {imperfect.length > 0 && (
        <details className="days">
          <summary>
            {imperfect.length} day{imperfect.length === 1 ? "" : "s"} below 100%
          </summary>
          <ul>
            {imperfect.map((d) => (
              <li key={d.date}>{dayLabel(d.date, d.uptime)}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

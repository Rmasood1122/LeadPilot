/** Date formatting. Everything is rendered in UTC on the server; the browser
 * only adds a local-time tooltip (components/LocalTime.tsx). */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** "11 Oct 2026, 14:05 UTC" */
export function formatUtc(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}

/** "11 Oct 2026" for a YYYY-MM-DD UTC day. */
export function formatDay(day: string): string {
  const d = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return day;
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** "October 2026" for grouping the history page. */
export function formatMonth(iso: string): string {
  const d = new Date(iso);
  const long = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  return `${long[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function formatPercent(value: number): string {
  if (value >= 100) return "100%";
  return `${(Math.floor(value * 100) / 100).toFixed(2)}%`;
}

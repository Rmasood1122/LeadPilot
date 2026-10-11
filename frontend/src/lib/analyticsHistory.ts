/** The window GET /strategies/{id}/analytics applied to `series`
 *  (`history_days`: the plan's analytics_history_days; null = all history;
 *  undefined = an older server that does not report it). */
export function historyLabel(historyDays: number | null | undefined): string | null {
  if (historyDays === undefined) return null;
  if (historyDays === null) return "all history";
  return `last ${historyDays} day${historyDays === 1 ? "" : "s"}`;
}

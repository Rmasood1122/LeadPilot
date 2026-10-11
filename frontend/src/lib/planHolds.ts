/** Campaign notice for messages held at send time because the account's
 *  current plan does not cover them (app/services/plan_holds.py). Pure. */

export interface PlanHolds {
  count: number;
  reasons: string[];
}

export function planHoldNotice(holds: PlanHolds | null | undefined): string | null {
  if (!holds || holds.count <= 0) return null;
  const what = holds.count === 1 ? "1 message is" : `${holds.count} messages are`;
  const why = holds.reasons.length ? ` ${holds.reasons.join(" ")}` : "";
  return (
    `${what} on hold because your current plan does not cover ${holds.count === 1 ? "it" : "them"}.` +
    `${why} Held messages are not sent. They go out automatically within about ` +
    `15 minutes of a plan change that covers them.`
  );
}

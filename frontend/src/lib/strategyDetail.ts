import type { VerificationPass } from "@/lib/api/types";

/** One line of the "10x verification loop" card.
 *
 *  The server sends the raw log (app/verification/loop.py::_log_attempt): one
 *  row per attempt, append-only across verification runs, plus manual
 *  sign-off rows (app/services/verification_override.py). The card shows each
 *  check once, in its latest state. */
export interface VerificationRow {
  pass_no: number;
  name: string;
  result: "PASS" | "FAIL";
  /** Attempts in the check's latest run (the server's `attempt` number). */
  attempts: number;
  manual: boolean;
  note:
    | { kind: "fix"; text: string }
    | { kind: "failure"; text: string }
    | { kind: "manual"; text: string }
    | null;
}

export function verificationSummary(log: VerificationPass[]): VerificationRow[] {
  // Rows of each check's latest run: a row with attempt 1 (or a lower attempt
  // than the previous row of the same check) starts a new run. A manual
  // sign-off row closes the run it signs off.
  const runs = new Map<number, VerificationPass[]>();
  for (const row of log) {
    const current = runs.get(row.pass_no);
    const prev = current?.[current.length - 1];
    const startsRun =
      !row.manual_override &&
      (prev === undefined || (row.attempt ?? 1) <= (prev.attempt ?? 1));
    if (current === undefined || startsRun) runs.set(row.pass_no, [row]);
    else current.push(row);
  }

  return [...runs.entries()]
    .sort(([a], [b]) => a - b)
    .map(([passNo, rows]) => {
      const last = rows[rows.length - 1];
      let note: VerificationRow["note"] = null;
      if (last.manual_override) {
        note = {
          kind: "manual",
          text: `${last.overridden_by_email ?? "a person"}: ${last.reason ?? ""}`,
        };
      } else if (last.result === "FAIL") {
        if (last.fix_description) note = { kind: "failure", text: last.fix_description };
      } else {
        const fixed = [...rows].reverse().find((r) => r.fix_applied && r.fix_description);
        if (fixed?.fix_description) note = { kind: "fix", text: fixed.fix_description };
      }
      return {
        pass_no: passNo,
        name: last.name,
        result: last.result,
        // A sign-off row carries attempt = last judged attempt + 1.
        attempts: last.manual_override
          ? Math.max(1, (last.attempt ?? 1) - 1)
          : (last.attempt ?? rows.length),
        manual: Boolean(last.manual_override),
        note,
      };
    });
}

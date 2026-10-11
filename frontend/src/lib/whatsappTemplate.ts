/** WhatsApp template drafting rules the editor mirrors. The server
 *  (app/services/whatsapp_templates.py) enforces all of them; the editor uses
 *  them to ask for what the server needs before it refuses. */

const PLACEHOLDER = /\{\{(\d+)\}\}/g;

/** Case-insensitive pattern for one word, keeping the rest case-sensitive
 *  (JavaScript has no scoped (?i:) flag). */
function ci(word: string): string {
  return [...word].map((c) => (/[a-z]/i.test(c) ? `[${c.toLowerCase()}${c.toUpperCase()}]` : c)).join("");
}

/** Mirrors _OPT_OUT_INSTRUCTION in app/services/whatsapp_templates.py (a
 *  legal guard): an instruction -- a verb then STOP, or STOP then "opt out" /
 *  "unsubscribe" -- within 25 characters and one sentence, STOP in capitals. */
const OPT_OUT_INSTRUCTION = new RegExp(
  `\\b(?:${["reply", "text", "send", "respond", "message"].map(ci).join("|")})\\b` +
    "[^.\\n]{0,25}\\bSTOP\\b" +
    `|\\bSTOP\\b[^.\\n]{0,25}\\b(?:${ci("opt")}[ -]?${ci("out")}|${ci("unsubscribe")})\\b`,
);

/** The placeholder numbers in a body, sorted, each once ({{1}} -> 1). */
export function placeholderNumbers(body: string): number[] {
  const found = new Set<number>();
  for (const match of body.matchAll(PLACEHOLDER)) found.add(Number(match[1]));
  return [...found].sort((a, b) => a - b);
}

/** One description per placeholder the body uses -- the server requires
 *  exactly that set (missing or extra keys are refused). */
export function variableDescriptions(
  body: string,
  descriptions: Record<string, string>,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const n of placeholderNumbers(body)) {
    out[String(n)] = (descriptions[String(n)] ?? "").trim();
  }
  return out;
}

export function missingDescriptions(
  body: string,
  descriptions: Record<string, string>,
): number[] {
  const filled = variableDescriptions(body, descriptions);
  return placeholderNumbers(body).filter((n) => !filled[String(n)]);
}

export function hasOptOutInstruction(body: string): boolean {
  return OPT_OUT_INSTRUCTION.test(body);
}

/** Only MARKETING templates must carry the instruction (as on the server). */
export function needsOptOutInstruction(category: string | undefined): boolean {
  return (category ?? "marketing").toLowerCase() === "marketing";
}

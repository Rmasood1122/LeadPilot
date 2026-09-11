/** Split an assembled strategy document into its phase sections, so the
 *  document page can hang uncertain-zone badges on the section they belong to.
 *
 *  The backend assembles the document as "# <title>" followed by one
 *  "## Phase <n>: <step name>" section per phase synthesis
 *  (app/pipeline/engine.py::_assemble). A mutation version prepends its own
 *  "## Strategy mutation — version N" section, which has no phase. */

export interface DocSection {
  /** The whole heading line without the leading "## ". */
  heading: string;
  /** Phase number for "Phase N: ..." headings, else null. */
  phase: number | null;
  /** The section's markdown, INCLUDING its heading line. */
  body: string;
}

export function splitSections(md: string | null | undefined): {
  preamble: string;
  sections: DocSection[];
} {
  const text = md ?? "";
  const lines = text.split("\n");
  const preamble: string[] = [];
  const sections: DocSection[] = [];
  let current: DocSection | null = null;
  let inFence = false;

  for (const line of lines) {
    if (/^\s*```/.test(line)) inFence = !inFence;
    const heading = !inFence ? line.match(/^##\s+(.+?)\s*$/) : null;
    if (heading) {
      if (current) sections.push(current);
      const phase = heading[1].match(/^Phase\s+(\d+)\b/i);
      current = { heading: heading[1], phase: phase ? Number(phase[1]) : null, body: `${line}\n` };
    } else if (current) {
      current.body += `${line}\n`;
    } else {
      preamble.push(line);
    }
  }
  if (current) sections.push(current);
  return { preamble: preamble.join("\n").trim(), sections };
}

/** Group zones by the phase they sit in; zones for a pipeline the document
 *  does not show are dropped by the caller filtering on `pipeline` first. */
export function zonesByPhase<T extends { phase: number }>(zones: T[]): Map<number, T[]> {
  const out = new Map<number, T[]>();
  for (const zone of zones) {
    const list = out.get(zone.phase) ?? [];
    list.push(zone);
    out.set(zone.phase, list);
  }
  return out;
}

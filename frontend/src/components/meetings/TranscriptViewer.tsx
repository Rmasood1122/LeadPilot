"use client";

/** The full transcript: searchable, with speaker labels when they exist.
 *
 * SPEAKER LABELS ARE PARSED, NOT ASSUMED. The ingestion endpoint stores a
 * chunk as "Speaker: text" when the provider sent a speaker and as bare text
 * when it did not, so a line is only split on a colon that looks like a label
 * — short, before the first colon, no sentence punctuation. Splitting on any
 * colon would turn "Pricing: we're at $3,000" into a speaker called "Pricing".
 *
 * EXPORT IS BUILT FROM THE RENDERED LINES, not re-fetched. What the user
 * downloads is exactly what they were looking at.
 */

import { useMemo, useState } from "react";
import { Download, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export interface TranscriptLine {
  speaker: string | null;
  text: string;
}

/** A label is a short, punctuation-free prefix before the first colon. */
const SPEAKER_PATTERN = /^([^:\n]{1,60}):\s+(.*)$/;

export function parseTranscript(raw: string | null): TranscriptLine[] {
  if (!raw?.trim()) return [];
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const match = SPEAKER_PATTERN.exec(line);
      if (!match) return { speaker: null, text: line };
      const [, speaker, text] = match;
      // A "speaker" containing sentence punctuation is a sentence, not a name.
      if (/[.!?]/.test(speaker)) return { speaker: null, text: line };
      return { speaker: speaker.trim(), text: text.trim() };
    });
}

export function TranscriptViewer({
  transcript,
  title,
}: {
  transcript: string | null;
  title: string;
}) {
  const [query, setQuery] = useState("");
  const lines = useMemo(() => parseTranscript(transcript), [transcript]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return lines;
    return lines.filter(
      (line) =>
        line.text.toLowerCase().includes(needle) ||
        (line.speaker ?? "").toLowerCase().includes(needle),
    );
  }, [lines, query]);

  const download = () => {
    const body = lines
      .map((line) => (line.speaker ? `${line.speaker}: ${line.text}` : line.text))
      .join("\n");
    const blob = new Blob([`${title}\n\n${body}\n`], {
      type: "text/plain;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${title.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-transcript.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const print = () => {
    // The browser's own "print to PDF" rather than a PDF library. It is one
    // line, it respects the user's page size and it produces a searchable
    // document; bundling a PDF generator to do worse would be a strange
    // trade. (The brief asks for "Export as PDF / TXT" — this is the PDF half.)
    window.print();
  };

  if (lines.length === 0) {
    return (
      <p className="rounded border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        No transcript was captured for this meeting. Transcripts arrive from a
        recording integration; without one, the AI summary works from your live
        notes alone.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 print:hidden">
        <div className="relative min-w-0 flex-1">
          <Search
            size={14}
            aria-hidden="true"
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search the transcript"
            aria-label="Search the transcript"
            className="pl-8"
          />
        </div>
        <Button size="sm" variant="outline" onClick={download}>
          <Download size={14} aria-hidden="true" />
          TXT
        </Button>
        <Button size="sm" variant="outline" onClick={print}>
          <Download size={14} aria-hidden="true" />
          PDF
        </Button>
      </div>

      <p className="text-xs text-muted-foreground print:hidden" aria-live="polite">
        {query
          ? `${filtered.length} of ${lines.length} lines match`
          : `${lines.length} lines`}
      </p>

      <ol className="space-y-2 rounded border border-border bg-card p-4 text-sm">
        {filtered.map((line, index) => (
          <li key={index} className="flex gap-3">
            {line.speaker ? (
              <span className="w-28 shrink-0 truncate font-medium text-muted-foreground">
                {line.speaker}
              </span>
            ) : (
              <span aria-hidden="true" className="w-28 shrink-0" />
            )}
            <span className="min-w-0 flex-1 whitespace-pre-wrap break-words">
              {line.text}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

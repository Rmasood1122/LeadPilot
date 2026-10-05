/** Pure rules for the Network page. The server is the real gate (402 on
 *  Free/Starter); these only decide what the screen offers. */
import { ApiError } from "@/lib/api/client";

export function checkExportFile(
  file: { name: string; size: number },
  maxBytes: number,
): string | null {
  if (!/\.csv$/i.test(file.name)) return "Choose the Connections.csv file from your LinkedIn export.";
  if (file.size === 0) return "That file is empty.";
  if (file.size > maxBytes) {
    return `That file is larger than ${Math.floor(maxBytes / 1_000_000)} MB.`;
  }
  return null;
}

export function importErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 402) return "Your plan does not include the LinkedIn network. Upgrade to Growth or higher.";
    if (err.status === 413) return "That file is too large.";
    if (err.status === 422) return err.message;
  }
  return "Import failed. Try again.";
}

export function importSummary(r: { added: number; skipped: number; matched: number }): string {
  return `Added ${r.added} connection${r.added === 1 ? "" : "s"}` +
    (r.skipped ? `, skipped ${r.skipped}` : "") +
    `. ${r.matched} match${r.matched === 1 ? "" : "es"} for your products.`;
}

export function scoreLabel(score: number): "Strong" | "Good" | "Possible" {
  return score >= 70 ? "Strong" : score >= 50 ? "Good" : "Possible";
}

/** Only linkedin.com links are rendered as links. */
export function safeProfileUrl(url: string | null): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === "https:" && /(^|\.)linkedin\.com$/i.test(u.hostname) ? u.toString() : null;
  } catch {
    return null;
  }
}

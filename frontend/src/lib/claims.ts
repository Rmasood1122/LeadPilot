/** Feature A1 — the claim engine's audit, shaped for the lead page.
 *  Pure helpers; tested in src/tests/claims.test.ts. */

export type ClaimVerdict = "verified" | "stripped" | "rewritten";

export interface ClaimCheck {
  id: string;
  lead_id: string | null;
  message_id: string | null;
  channel: string;
  field: string;
  category: string;
  claim_text: string;
  verdict: ClaimVerdict;
  extractor: "rules" | "model";
  evidence_source: string | null;
  evidence_excerpt: string | null;
  unsupported: string[];
  replacement_text: string | null;
  created_at: string | null;
}

export function verdictTone(verdict: ClaimVerdict): "success" | "warning" | "destructive" {
  if (verdict === "verified") return "success";
  return verdict === "rewritten" ? "warning" : "destructive";
}

const CATEGORY_LABELS: Record<string, string> = {
  funding: "Funding", headcount: "Headcount", hiring: "Hiring", job_change: "Job change",
  news: "News", metrics: "Metrics", expansion: "Expansion", their_content: "Their post",
  other: "Other claim",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category.replace(/_/g, " ");
}

/** "apollo:enrichment.person.organization.estimated_num_employees" -> "Apollo · estimated num employees";
 *  "newsapi:https://…" -> "NewsAPI". */
export function sourceLabel(source: string | null): string {
  if (!source) return "No stored source";
  const [provider, rest = ""] = source.split(/:(.+)/);
  const names: Record<string, string> = {
    apollo: "Apollo", hunter: "Hunter", newsapi: "NewsAPI", linkedin_post: "LinkedIn post",
    signalforge: "SIGNALFORGE", manual: "Manual entry",
  };
  const name = names[provider] ?? provider;
  if (provider === "newsapi" || provider === "linkedin_post") return name;
  const leaf = rest.split(/[.[\]]/).filter(Boolean).pop();
  return leaf ? `${name} · ${leaf.replace(/_/g, " ")}` : name;
}

/** "number:2.5e+07" -> "the number 25,000,000"; "name:Salesforce" -> "“Salesforce”". */
export function describeMissing(token: string): string {
  const [kind, value = ""] = token.split(/:(.+)/);
  if (kind === "number") {
    const n = Number(value);
    return Number.isFinite(n) ? `the number ${n.toLocaleString("en-US")}` : token;
  }
  if (kind === "series") return `Series ${value.toUpperCase()}`;
  if (kind === "name" || kind === "quote") return `“${value}”`;
  return token.replace(/_/g, " ");
}

export interface ClaimGroup {
  key: string;
  message_id: string | null;
  created_at: string | null;
  checks: ClaimCheck[];
  removed: number;
}

/** One group per message, newest first; removed = stripped + rewritten. */
export function groupByMessage(checks: ClaimCheck[]): ClaimGroup[] {
  const groups = new Map<string, ClaimGroup>();
  for (const check of checks) {
    const key = check.message_id ?? `unsent:${check.created_at ?? check.id}`;
    const group = groups.get(key) ?? { key, message_id: check.message_id,
                                       created_at: check.created_at, checks: [], removed: 0 };
    group.checks.push(check);
    if (check.verdict !== "verified") group.removed += 1;
    if ((check.created_at ?? "") > (group.created_at ?? "")) group.created_at = check.created_at;
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
}

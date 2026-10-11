/**
 * Incidents are Markdown files in status-page/incidents/, posted by PR:
 *
 *   incidents/YYYY-MM-DD-<slug>.md
 *   ---
 *   title: Background processing delayed
 *   impact: major            # none | minor | major | critical | maintenance
 *   components: [background-processing]
 *   updates:
 *     - status: investigating   # investigating | identified | monitoring | resolved
 *       at: 2026-10-11T14:05:00Z
 *       text: We are investigating delays in scheduled sends.
 *   ---
 *   Optional longer write-up (plain paragraphs).
 *
 * The same parser backs the pages, the feeds and `npm run incident-lint`, so
 * a file that passes the lint is exactly a file the site can render. Format
 * guide for humans: incidents/README.md.
 */

import fs from "node:fs";
import path from "node:path";
import { parse as parseYaml } from "yaml";

import { COMPONENT_IDS, type ComponentId } from "./config.ts";
import type { PublicStatus } from "./status.ts";

export const IMPACTS = ["none", "minor", "major", "critical", "maintenance"] as const;
export type Impact = (typeof IMPACTS)[number];

export const UPDATE_STATUSES = ["investigating", "identified", "monitoring", "resolved"] as const;
export type UpdateStatus = (typeof UPDATE_STATUSES)[number];

export const UPDATE_STATUS_LABELS: Record<UpdateStatus, string> = {
  investigating: "Investigating",
  identified: "Identified",
  monitoring: "Monitoring",
  resolved: "Resolved",
};

export const IMPACT_LABELS: Record<Impact, string> = {
  none: "No impact",
  minor: "Minor",
  major: "Major",
  critical: "Critical",
  maintenance: "Maintenance",
};

export interface IncidentUpdate {
  status: UpdateStatus;
  /** UTC ISO-8601 with a trailing Z. */
  at: string;
  text: string;
}

export interface Incident {
  slug: string;
  file: string;
  title: string;
  impact: Impact;
  components: ComponentId[];
  /** Newest first. */
  updates: IncidentUpdate[];
  /** Plain paragraphs from the Markdown body (may be empty). */
  body: string[];
  resolved: boolean;
  startedAt: string;
  updatedAt: string;
  resolvedAt: string | null;
}

export const FILENAME_RE = /^(\d{4}-\d{2}-\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$/;
const ISO_UTC_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,3})?)?Z$/;
const ALLOWED_KEYS = new Set(["title", "impact", "components", "updates"]);
const ALLOWED_UPDATE_KEYS = new Set(["status", "at", "text"]);
/** Clock skew allowed for an update timestamp "from the future". */
const FUTURE_SKEW_MS = 10 * 60 * 1000;
const MAX_TITLE = 120;

function splitFrontMatter(source: string): { front: string; body: string } | null {
  const text = source.replace(/^﻿/, "").replace(/\r\n/g, "\n");
  if (!text.startsWith("---\n")) return null;
  const end = text.indexOf("\n---", 4);
  if (end === -1) return null;
  const after = text.slice(end + 4);
  if (after !== "" && !after.startsWith("\n")) return null;
  return { front: text.slice(4, end + 1), body: after.replace(/^\n/, "") };
}

function paragraphs(body: string): string[] {
  return body
    .split(/\n\s*\n/)
    .map((p) => p.replace(/\s*\n\s*/g, " ").trim())
    .filter(Boolean);
}

export function parseIncident(
  fileName: string,
  source: string,
  now: Date = new Date(),
): { incident: Incident | null; errors: string[] } {
  const errors: string[] = [];
  const nameMatch = FILENAME_RE.exec(fileName);
  if (!nameMatch) {
    errors.push(
      `file name must be YYYY-MM-DD-<slug>.md with a lowercase, hyphenated slug (got "${fileName}")`,
    );
  }

  const parts = splitFrontMatter(source);
  if (!parts) {
    errors.push("missing front matter: the file must start with a line '---' and close it with '---'");
    return { incident: null, errors };
  }

  let data: unknown;
  try {
    data = parseYaml(parts.front, { version: "1.2", schema: "core", uniqueKeys: true });
  } catch (e) {
    errors.push(`front matter is not valid YAML: ${(e as Error).message.split("\n")[0]}`);
    return { incident: null, errors };
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    errors.push("front matter must be a mapping of keys to values");
    return { incident: null, errors };
  }
  const fm = data as Record<string, unknown>;

  for (const key of Object.keys(fm)) {
    if (!ALLOWED_KEYS.has(key)) errors.push(`unknown front-matter key "${key}"`);
  }

  const title = typeof fm.title === "string" ? fm.title.trim() : "";
  if (!title) errors.push("title is required");
  else if (title.length > MAX_TITLE) errors.push(`title is longer than ${MAX_TITLE} characters`);

  const impact = fm.impact;
  if (!(IMPACTS as readonly unknown[]).includes(impact)) {
    errors.push(`impact must be one of ${IMPACTS.join(", ")} (got ${JSON.stringify(impact)})`);
  }

  const components: ComponentId[] = [];
  if (!Array.isArray(fm.components) || fm.components.length === 0) {
    errors.push(`components must be a non-empty list of: ${COMPONENT_IDS.join(", ")}`);
  } else {
    for (const c of fm.components) {
      if (typeof c === "string" && (COMPONENT_IDS as readonly string[]).includes(c)) {
        if (!components.includes(c as ComponentId)) components.push(c as ComponentId);
      } else {
        errors.push(`unknown component ${JSON.stringify(c)}; use: ${COMPONENT_IDS.join(", ")}`);
      }
    }
  }

  const updates: IncidentUpdate[] = [];
  if (!Array.isArray(fm.updates) || fm.updates.length === 0) {
    errors.push("updates must be a non-empty list");
  } else {
    fm.updates.forEach((raw: unknown, i: number) => {
      const where = `updates[${i}]`;
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
        errors.push(`${where} must be a mapping with status, at and text`);
        return;
      }
      const u = raw as Record<string, unknown>;
      for (const key of Object.keys(u)) {
        if (!ALLOWED_UPDATE_KEYS.has(key)) errors.push(`${where}: unknown key "${key}"`);
      }
      const status = u.status;
      if (!(UPDATE_STATUSES as readonly unknown[]).includes(status)) {
        errors.push(`${where}: status must be one of ${UPDATE_STATUSES.join(", ")} (got ${JSON.stringify(status)})`);
      }
      const at = typeof u.at === "string" ? u.at.trim() : "";
      if (!ISO_UTC_RE.test(at) || Number.isNaN(Date.parse(at))) {
        errors.push(`${where}: at must be a UTC timestamp like 2026-10-11T14:05:00Z (got ${JSON.stringify(u.at)})`);
      } else if (Date.parse(at) > now.getTime() + FUTURE_SKEW_MS) {
        errors.push(`${where}: at ${at} is in the future`);
      }
      const text = typeof u.text === "string" ? u.text.trim() : "";
      if (!text) errors.push(`${where}: text is required`);
      updates.push({ status: status as UpdateStatus, at, text });
    });
  }

  if (errors.length === 0) {
    // Newest first; the newest decides whether the incident is resolved.
    updates.sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
    const resolvedCount = updates.filter((u) => u.status === "resolved").length;
    if (resolvedCount > 1) errors.push("only one update may have status resolved");
    if (resolvedCount === 1 && updates[0]!.status !== "resolved") {
      errors.push("the resolved update must be the latest one (nothing can follow resolution)");
    }
    const earliest = updates[updates.length - 1]!;
    if (nameMatch && earliest.at.slice(0, 10) !== nameMatch[1]) {
      errors.push(
        `file name date ${nameMatch[1]} must equal the UTC date of the first update (${earliest.at.slice(0, 10)})`,
      );
    }
  }

  if (errors.length > 0) return { incident: null, errors };

  const resolved = updates[0]!.status === "resolved";
  return {
    incident: {
      slug: fileName.replace(/\.md$/, ""),
      file: fileName,
      title,
      impact: impact as Impact,
      components,
      updates,
      body: paragraphs(parts.body),
      resolved,
      startedAt: updates[updates.length - 1]!.at,
      updatedAt: updates[0]!.at,
      resolvedAt: resolved ? updates[0]!.at : null,
    },
    errors: [],
  };
}

export function incidentsDir(): string {
  return path.join(process.cwd(), "incidents");
}

/** Every .md file except README.md. Non-.md files are reported by the lint. */
export function listIncidentFiles(dir: string): string[] {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f !== "README.md" && !f.startsWith("."))
    .sort();
}

export interface LintReport {
  file: string;
  errors: string[];
}

export function lintIncidentDir(dir: string, now: Date = new Date()): LintReport[] {
  const reports: LintReport[] = [];
  for (const file of listIncidentFiles(dir)) {
    if (!file.endsWith(".md")) {
      reports.push({ file, errors: ["only .md incident files (and README.md) belong in incidents/"] });
      continue;
    }
    const { errors } = parseIncident(file, fs.readFileSync(path.join(dir, file), "utf8"), now);
    reports.push({ file, errors });
  }
  return reports;
}

/**
 * All incidents, newest first. Throws on any invalid file: the build fails
 * rather than silently dropping an incident customers should see.
 * (CI's incident-lint step reports the same errors earlier, per file.)
 */
export function loadIncidents(dir: string = incidentsDir(), now: Date = new Date()): Incident[] {
  const out: Incident[] = [];
  const problems: string[] = [];
  for (const file of listIncidentFiles(dir)) {
    if (!file.endsWith(".md")) {
      problems.push(`${file}: not a .md file`);
      continue;
    }
    const { incident, errors } = parseIncident(file, fs.readFileSync(path.join(dir, file), "utf8"), now);
    if (incident) out.push(incident);
    else problems.push(...errors.map((e) => `${file}: ${e}`));
  }
  if (problems.length > 0) {
    throw new Error(`invalid incident files (run npm run incident-lint):\n${problems.join("\n")}`);
  }
  return out.sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
}

/** What an unresolved incident of this impact says about its components. */
export function impactStatus(impact: Impact): PublicStatus | null {
  switch (impact) {
    case "minor":
      return "degraded";
    case "major":
      return "partial_outage";
    case "critical":
      return "major_outage";
    case "maintenance":
      return "maintenance";
    case "none":
      return null;
  }
}

export function activeIncidents(incidents: Incident[]): Incident[] {
  return incidents.filter((i) => !i.resolved);
}

/** Unresolved incidents, plus any incident updated within the last `days` days. */
export function recentIncidents(incidents: Incident[], now: Date, days: number): Incident[] {
  const cutoff = now.getTime() - days * 86_400_000;
  return incidents.filter((i) => !i.resolved || Date.parse(i.updatedAt) >= cutoff);
}

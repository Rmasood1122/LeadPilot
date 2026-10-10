import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, it } from "node:test";

import { lintIncidentDir, loadIncidents, parseIncident, recentIncidents } from "../lib/incidents.ts";
import { NOW } from "./helpers.ts";

const GOOD = `---
title: Scheduled sends delayed
impact: major
components: [background-processing, api]
updates:
  - status: investigating
    at: 2026-10-10T14:05:00Z
    text: Scheduled emails are not going out.
  - status: resolved
    at: 2026-10-10T14:40:00Z
    text: Sends resumed.
---
First paragraph
wraps here.

Second paragraph.
`;

function errorsFor(name: string, src: string): string[] {
  return parseIncident(name, src, NOW).errors;
}

function withUpdates(updates: string, extra = ""): string {
  return `---\ntitle: T\nimpact: minor\ncomponents: [api]\n${extra}updates:\n${updates}\n---\n`;
}

describe("parseIncident", () => {
  it("parses a valid file, newest update first", () => {
    const { incident, errors } = parseIncident("2026-10-10-sends-delayed.md", GOOD, NOW);
    assert.deepEqual(errors, []);
    assert.equal(incident!.slug, "2026-10-10-sends-delayed");
    assert.equal(incident!.resolved, true);
    assert.equal(incident!.updates[0]!.status, "resolved");
    assert.equal(incident!.startedAt, "2026-10-10T14:05:00Z");
    assert.equal(incident!.resolvedAt, "2026-10-10T14:40:00Z");
    assert.deepEqual(incident!.components, ["background-processing", "api"]);
    assert.deepEqual(incident!.body, ["First paragraph wraps here.", "Second paragraph."]);
  });

  it("accepts CRLF line endings and a BOM", () => {
    assert.deepEqual(errorsFor("2026-10-10-sends-delayed.md", "﻿" + GOOD.replace(/\n/g, "\r\n")), []);
  });

  const bad: [string, string, string, RegExp][] = [
    ["bad file name", "Oct-10-outage.md", GOOD, /file name must be/],
    ["uppercase slug", "2026-10-10-Outage.md", GOOD, /file name must be/],
    ["no front matter", "2026-10-10-x.md", "title: x\n", /missing front matter/],
    ["unterminated front matter", "2026-10-10-x.md", "---\ntitle: x\n", /missing front matter/],
    ["invalid YAML", "2026-10-10-x.md", "---\ntitle: [unclosed\n---\n", /not valid YAML/],
    ["duplicate key", "2026-10-10-x.md", "---\ntitle: a\ntitle: b\n---\n", /not valid YAML/],
    ["unknown key", "2026-10-10-x.md", withUpdates("  - status: investigating\n    at: 2026-10-10T10:00:00Z\n    text: x", "severity: high\n"), /unknown front-matter key "severity"/],
    ["bad impact", "2026-10-10-x.md", GOOD.replace("impact: major", "impact: huge"), /impact must be one of/],
    ["unknown component", "2026-10-10-x.md", GOOD.replace("[background-processing, api]", "[database]"), /unknown component "database"/],
    ["empty components", "2026-10-10-x.md", GOOD.replace("[background-processing, api]", "[]"), /components must be a non-empty list/],
    ["no updates", "2026-10-10-x.md", "---\ntitle: T\nimpact: minor\ncomponents: [api]\nupdates: []\n---\n", /updates must be a non-empty list/],
    ["bad status", "2026-10-10-x.md", withUpdates("  - status: fixed\n    at: 2026-10-10T10:00:00Z\n    text: x"), /status must be one of/],
    ["local time, no Z", "2026-10-10-x.md", withUpdates("  - status: investigating\n    at: 2026-10-10T10:00:00+02:00\n    text: x"), /must be a UTC timestamp/],
    ["date only", "2026-10-10-x.md", withUpdates("  - status: investigating\n    at: 2026-10-10\n    text: x"), /must be a UTC timestamp/],
    ["future", "2026-10-12-x.md", withUpdates("  - status: investigating\n    at: 2026-10-12T10:00:00Z\n    text: x"), /is in the future/],
    ["empty text", "2026-10-10-x.md", withUpdates("  - status: investigating\n    at: 2026-10-10T10:00:00Z\n    text: ''"), /text is required/],
    ["unknown update key", "2026-10-10-x.md", withUpdates("  - status: investigating\n    at: 2026-10-10T10:00:00Z\n    text: x\n    author: bob"), /unknown key "author"/],
    ["resolved not last", "2026-10-10-x.md", withUpdates("  - status: resolved\n    at: 2026-10-10T10:00:00Z\n    text: x\n  - status: monitoring\n    at: 2026-10-10T11:00:00Z\n    text: y"), /resolved update must be the latest/],
    ["two resolved", "2026-10-10-x.md", withUpdates("  - status: resolved\n    at: 2026-10-10T10:00:00Z\n    text: x\n  - status: resolved\n    at: 2026-10-10T11:00:00Z\n    text: y"), /only one update may have status resolved/],
    ["file date mismatch", "2026-10-09-x.md", GOOD, /must equal the UTC date of the first update/],
    ["missing title", "2026-10-10-x.md", GOOD.replace("title: Scheduled sends delayed\n", ""), /title is required/],
  ];
  for (const [label, name, src, pattern] of bad) {
    it(`rejects: ${label}`, () => {
      const errors = errorsFor(name, src);
      assert.ok(errors.some((e) => pattern.test(e)), `expected ${pattern} in ${JSON.stringify(errors)}`);
    });
  }
});

describe("directory lint and loading", () => {
  function tmpDir(files: Record<string, string>): string {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "incidents-"));
    for (const [name, body] of Object.entries(files)) fs.writeFileSync(path.join(dir, name), body);
    return dir;
  }

  it("ignores README.md and passes an empty folder", () => {
    const dir = tmpDir({ "README.md": "# not an incident" });
    assert.deepEqual(lintIncidentDir(dir, NOW), []);
    assert.deepEqual(loadIncidents(dir, NOW), []);
  });

  it("the committed incidents folder is valid and has no example incidents", () => {
    const dir = path.join(import.meta.dirname, "..", "incidents");
    const reports = lintIncidentDir(dir);
    assert.ok(reports.every((r) => r.errors.length === 0), JSON.stringify(reports));
    assert.ok(fs.existsSync(path.join(dir, "README.md")));
  });

  it("reports stray non-markdown files", () => {
    const dir = tmpDir({ "notes.txt": "x" });
    assert.match(lintIncidentDir(dir, NOW)[0]!.errors[0]!, /only \.md incident files/);
  });

  it("loadIncidents throws on any invalid file so the build fails loudly", () => {
    const dir = tmpDir({ "2026-10-10-ok.md": GOOD, "2026-10-10-bad.md": GOOD.replace("impact: major", "impact: x") });
    assert.throws(() => loadIncidents(dir, NOW), /2026-10-10-bad\.md: impact must be one of/);
  });

  it("sorts newest first and keeps the last 14 days plus anything unresolved", () => {
    const old = GOOD.replaceAll("2026-10-10", "2026-09-01");
    const oldOpen = withUpdates("  - status: monitoring\n    at: 2026-09-02T10:00:00Z\n    text: still watching");
    const dir = tmpDir({ "2026-09-01-old.md": old, "2026-10-10-new.md": GOOD, "2026-09-02-open.md": oldOpen });
    const all = loadIncidents(dir, NOW);
    assert.deepEqual(all.map((i) => i.slug), ["2026-10-10-new", "2026-09-02-open", "2026-09-01-old"]);
    assert.deepEqual(recentIncidents(all, NOW, 14).map((i) => i.slug), ["2026-10-10-new", "2026-09-02-open"]);
  });
});

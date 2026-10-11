import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildAtom, buildRss, escapeXml } from "../lib/feeds.ts";
import { parseIncident } from "../lib/incidents.ts";
import { NOW } from "./helpers.ts";

const SITE = "https://status.calendarharvest.com";
const inc = parseIncident(
  "2026-10-10-sends-delayed.md",
  "---\ntitle: Sends <delayed> & retried\nimpact: major\ncomponents: [api]\nupdates:\n  - status: investigating\n    at: 2026-10-10T14:05:00Z\n    text: Looking into \"it\".\n---\n",
  NOW,
).incident!;

describe("feeds", () => {
  it("RSS lists the incident with an escaped title and a permalink", () => {
    const rss = buildRss([inc], SITE, NOW);
    assert.match(rss, /^<\?xml version="1\.0" encoding="UTF-8"\?>\n<rss version="2\.0"/);
    assert.ok(rss.includes("<title>Sends &lt;delayed&gt; &amp; retried</title>"));
    assert.ok(rss.includes(`<link>${SITE}/incidents/2026-10-10-sends-delayed</link>`));
    assert.ok(rss.includes("<pubDate>Sat, 10 Oct 2026 14:05:00 GMT</pubDate>"));
    assert.ok(rss.includes("Investigating (10 Oct 2026, 14:05 UTC): Looking into &quot;it&quot;."));
  });

  it("Atom has one entry with published and updated times", () => {
    const atom = buildAtom([inc], SITE, NOW);
    assert.ok(atom.includes('<feed xmlns="http://www.w3.org/2005/Atom">'));
    assert.equal(atom.match(/<entry>/g)!.length, 1);
    assert.ok(atom.includes("<published>2026-10-10T14:05:00Z</published>"));
    assert.ok(atom.includes("<updated>2026-10-10T14:05:00Z</updated>"));
  });

  it("empty history is still a valid feed", () => {
    assert.ok(!buildRss([], SITE, NOW).includes("<item>"));
    assert.ok(buildAtom([], SITE, NOW).includes("<updated>2026-10-11T12:00:00Z</updated>"));
  });

  it("escapes all five XML characters", () => {
    assert.equal(escapeXml(`<a href="x">'&'</a>`), "&lt;a href=&quot;x&quot;&gt;&apos;&amp;&apos;&lt;/a&gt;");
  });
});

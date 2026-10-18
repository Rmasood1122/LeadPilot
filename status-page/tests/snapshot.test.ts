import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { getSnapshot, DETAIL_UNAVAILABLE, DERIVED_NOTE, STATUS_DATA_UNAVAILABLE } from "../lib/snapshot.ts";
import { parseIncident, type Incident } from "../lib/incidents.ts";
import { API, KEY, NOW, UR, allMonitors, backendBody, fakeFetch, json, refused } from "./helpers.ts";

const ENV = { UPTIMEROBOT_API_KEY: KEY, LEADPILOT_API_URL: API };

function statuses(snap: Awaited<ReturnType<typeof getSnapshot>>) {
  return Object.fromEntries(snap.components.map((c) => [c.id, c.status]));
}

function incident(name: string, yaml: string): Incident {
  const { incident, errors } = parseIncident(name, `---\n${yaml}\n---\n`, NOW);
  assert.deepEqual(errors, []);
  return incident!;
}

describe("both sources healthy", () => {
  it("shows every component operational and the all-clear banner", async () => {
    const { fetch } = fakeFetch({ [UR]: () => json(allMonitors()), [API]: () => json(backendBody()) });
    const snap = await getSnapshot(ENV, { fetch, now: NOW, incidents: [] });
    assert.deepEqual(new Set(Object.values(statuses(snap))), new Set(["operational"]));
    assert.equal(snap.overall.title, "All systems operational");
    assert.equal(snap.dataNotice, null);
    const api = snap.components.find((c) => c.id === "api")!;
    assert.equal(api.source, "backend");
    assert.equal(api.checkedAt, "2026-10-11T11:59:40Z");
    assert.equal(api.uptime?.days.length, 90);
    assert.equal(snap.components.find((c) => c.id === "ai-features")!.uptime, null);
  });

  it("uses the backend's own statuses when it answers", async () => {
    const { fetch } = fakeFetch({
      [UR]: () => json(allMonitors()),
      [API]: () => json(backendBody({ "background-processing": "major_outage", "ai-features": "degraded" })),
    });
    const s = statuses(await getSnapshot(ENV, { fetch, now: NOW, incidents: [] }));
    assert.equal(s["background-processing"], "major_outage");
    assert.equal(s["ai-features"], "degraded");
  });
});

describe("API unreachable (drill a)", () => {
  it("derives API and background from UptimeRobot and says detail unavailable", async () => {
    // The API is down: our fetch is refused and UptimeRobot's API monitors are down.
    const { fetch, calls } = fakeFetch({
      [UR]: () => json(allMonitors({ apiHttp: 9, apiKeyword: 9, worker: 2 })),
      [API]: refused,
    });
    const snap = await getSnapshot(ENV, { fetch, now: NOW, incidents: [] });
    const s = statuses(snap);
    assert.equal(s.api, "major_outage");
    assert.equal(s["booking-pages"], "major_outage"); // booking needs the API
    assert.equal(s["ai-features"], "unknown"); // never derived
    assert.equal(s.website, "operational");
    assert.equal(snap.overall.title, "Major outage");
    assert.equal(snap.dataNotice?.title, DETAIL_UNAVAILABLE);
    assert.equal(snap.components.find((c) => c.id === "api")!.note, DERIVED_NOTE);
    assert.equal(snap.components.find((c) => c.id === "ai-features")!.note, DETAIL_UNAVAILABLE);
    assert.ok(calls.some((c) => c.url === `${API}/status/public`));
  });

  it("never shows Operational for a component no check covered", async () => {
    // Our fetch fails but UptimeRobot still sees the API up: API is derived
    // operational (an external check said so), AI features stays unknown.
    const { fetch } = fakeFetch({ [UR]: () => json(allMonitors()), [API]: refused });
    const snap = await getSnapshot(ENV, { fetch, now: NOW, incidents: [] });
    const s = statuses(snap);
    assert.equal(s.api, "operational");
    assert.equal(s["background-processing"], "operational"); // keyword monitor up
    assert.equal(s["ai-features"], "unknown");
    assert.equal(s["booking-pages"], "unknown");
    assert.notEqual(snap.overall.title, "All systems operational");
    assert.equal(snap.overall.title, "Some systems could not be checked");
  });

  it("treats /health answering but not healthy as background processing down", async () => {
    const { fetch } = fakeFetch({ [UR]: () => json(allMonitors({ apiKeyword: 9 })), [API]: refused });
    const s = statuses(await getSnapshot(ENV, { fetch, now: NOW, incidents: [] }));
    assert.equal(s.api, "operational");
    assert.equal(s["background-processing"], "major_outage");
  });

  it("counts a timeout, a 500 and a malformed body as unreachable", async () => {
    for (const respond of [
      () => json({ error: "x" }, 500),
      () => json({ unexpected: true }),
      () => new Response("<html>502</html>", { status: 200 }),
      () => {
        throw new DOMException("The operation was aborted due to timeout", "TimeoutError");
      },
    ]) {
      const { fetch } = fakeFetch({ [UR]: () => json(allMonitors()), [API]: respond });
      const snap = await getSnapshot(ENV, { fetch, now: NOW, incidents: [] });
      assert.equal(snap.sources.backend, "unreachable");
      assert.equal(snap.components.find((c) => c.id === "ai-features")!.status, "unknown");
    }
  });

  it("passes a 5-second timeout signal to the backend fetch", async () => {
    const { fetch, calls } = fakeFetch({ [UR]: () => json(allMonitors()), [API]: () => json(backendBody()) });
    await getSnapshot(ENV, { fetch, now: NOW, incidents: [] });
    const call = calls.find((c) => c.url.startsWith(API))!;
    assert.ok(call.init?.signal instanceof AbortSignal);
  });
});

describe("UptimeRobot key missing (drill b)", () => {
  it("renders the status-data-unavailable banner without calling UptimeRobot", async () => {
    const { fetch, calls } = fakeFetch({ [API]: () => json(backendBody()) });
    const snap = await getSnapshot({ LEADPILOT_API_URL: API }, { fetch, now: NOW, incidents: [] });
    assert.equal(snap.sources.uptimeRobot, "missing_key");
    assert.equal(snap.dataNotice?.title, STATUS_DATA_UNAVAILABLE);
    assert.ok(!calls.some((c) => c.url.includes("uptimerobot")));
    const s = statuses(snap);
    assert.equal(s.website, "unknown"); // only UptimeRobot measures it
    assert.equal(s.api, "operational"); // our own check still reports
    assert.ok(snap.components.every((c) => c.uptime === null));
    assert.equal(snap.overall.title, "Some systems could not be checked");
  });

  it("with nothing configured at all, still builds (the `npm run build` case)", async () => {
    const { fetch, calls } = fakeFetch({});
    const snap = await getSnapshot({}, { fetch, now: NOW, incidents: [] });
    assert.equal(calls.length, 0);
    assert.equal(snap.dataNotice?.title, STATUS_DATA_UNAVAILABLE);
    assert.ok(snap.components.every((c) => c.status === "unknown"));
    assert.equal(snap.overall.title, "Current status unknown");
  });

  it("an UptimeRobot error is a banner, not a crash", async () => {
    for (const respond of [() => json({ stat: "fail", error: { type: "invalid_parameter" } }), () => json({}, 503), refused]) {
      const { fetch } = fakeFetch({ [UR]: respond, [API]: () => json(backendBody()) });
      const snap = await getSnapshot(ENV, { fetch, now: NOW, incidents: [] });
      assert.equal(snap.sources.uptimeRobot, "error");
      assert.equal(snap.dataNotice?.title, STATUS_DATA_UNAVAILABLE);
    }
  });
});

describe("the API key stays server-side", () => {
  it("never appears in the snapshot", async () => {
    const { fetch, calls } = fakeFetch({ [UR]: () => json(allMonitors()), [API]: () => json(backendBody()) });
    const snap = await getSnapshot(ENV, { fetch, now: NOW, incidents: [] });
    assert.ok(!JSON.stringify(snap).includes(KEY));
    // ...and is only ever sent to UptimeRobot, in a POST body, never a URL.
    for (const c of calls) {
      assert.ok(!c.url.includes(KEY));
      if (!c.url.startsWith(UR)) assert.ok(!String(c.init?.body ?? "").includes(KEY));
    }
    const ur = calls.find((c) => c.url === UR)!;
    assert.equal(ur.init?.method, "POST");
    assert.ok(String(ur.init?.body).includes(`api_key=${KEY}`));
  });
});

describe("incidents on top of measured status", () => {
  const healthy = () => fakeFetch({ [UR]: () => json(allMonitors()), [API]: () => json(backendBody()) }).fetch;

  it("an unresolved major incident shows its components as partial outage", async () => {
    const inc = incident(
      "2026-10-11-sends-delayed.md",
      "title: Sends delayed\nimpact: major\ncomponents: [background-processing]\nupdates:\n  - status: investigating\n    at: 2026-10-11T11:00:00Z\n    text: Looking.",
    );
    const snap = await getSnapshot(ENV, { fetch: healthy(), now: NOW, incidents: [inc] });
    const bg = snap.components.find((c) => c.id === "background-processing")!;
    assert.equal(bg.status, "partial_outage");
    assert.equal(bg.source, "incident");
    assert.equal(snap.overall.title, "Partial outage");
  });

  it("a resolved incident changes nothing", async () => {
    const inc = incident(
      "2026-10-11-sends-delayed.md",
      "title: Sends delayed\nimpact: critical\ncomponents: [api]\nupdates:\n  - status: investigating\n    at: 2026-10-11T10:00:00Z\n    text: Looking.\n  - status: resolved\n    at: 2026-10-11T11:00:00Z\n    text: Fixed.",
    );
    const snap = await getSnapshot(ENV, { fetch: healthy(), now: NOW, incidents: [inc] });
    assert.equal(snap.overall.title, "All systems operational");
  });

  it("maintenance applies only over operational and never hides an outage", async () => {
    const inc = incident(
      "2026-10-11-db-upgrade.md",
      "title: Database upgrade\nimpact: maintenance\ncomponents: [api, background-processing]\nupdates:\n  - status: identified\n    at: 2026-10-11T11:30:00Z\n    text: Upgrading.",
    );
    const { fetch } = fakeFetch({
      [UR]: () => json(allMonitors()),
      [API]: () => json(backendBody({ "background-processing": "major_outage" })),
    });
    const s = statuses(await getSnapshot(ENV, { fetch, now: NOW, incidents: [inc] }));
    assert.equal(s.api, "maintenance");
    assert.equal(s["background-processing"], "major_outage");
  });

  it("an incident never makes a component look better", async () => {
    const inc = incident(
      "2026-10-11-minor.md",
      "title: Slow\nimpact: minor\ncomponents: [api]\nupdates:\n  - status: monitoring\n    at: 2026-10-11T11:30:00Z\n    text: Slow.",
    );
    const { fetch } = fakeFetch({ [UR]: () => json(allMonitors()), [API]: () => json(backendBody({ api: "major_outage" })) });
    assert.equal(statuses(await getSnapshot(ENV, { fetch, now: NOW, incidents: [inc] })).api, "major_outage");
  });
});

describe("uptime bars", () => {
  it("Website & app takes the worst of its two monitors per day", async () => {
    const body = allMonitors();
    const login = body.monitors.find((m) => m.friendly_name === "Vectorae - App login")!;
    login.custom_uptime_ranges = Array.from({ length: 90 }, (_, i) => (i === 89 ? "50.000" : "100.000")).join("-");
    const { fetch } = fakeFetch({ [UR]: () => json(body), [API]: () => json(backendBody()) });
    const web = (await getSnapshot(ENV, { fetch, now: NOW, incidents: [] })).components.find((c) => c.id === "website")!;
    assert.equal(web.uptime!.days[89]!.uptime, 50);
    assert.equal(web.uptime!.days[88]!.uptime, 100);
    assert.equal(web.uptime!.days[89]!.date, "2026-10-11");
  });
});

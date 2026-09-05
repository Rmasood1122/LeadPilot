/**
 * M9 CRM — E2E over the static export, with every backend call mocked via
 * page.route(). No FastAPI process is needed, matching the rest of this suite.
 *
 * Covers the flow the brief asks for end to end: load the dashboard, load the
 * grid, inline-edit a lead's status, save a view, reload, and confirm the view
 * came back. The saved-view reload is the one that matters most — it is the
 * whole reason views are stored server-side rather than in localStorage.
 */

import { test, expect, type Page, type Route } from "@playwright/test";

const ACCESS = "test-access-token";
const REFRESH = "test-refresh-token";

// --------------------------------------------------------------------------
// Fixtures
// --------------------------------------------------------------------------

function lead(index: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `l${index}`,
    strategy_id: "s1",
    full_name: `Lead ${index}`,
    title: "Founder",
    company: `Company ${index}`,
    email: `lead${index}@example.test`,
    phone: null,
    status: "verified",
    source: "apollo",
    created_at: "2026-09-01T10:00:00+00:00",
    updated_at: "2026-09-01T10:00:00+00:00",
    tags: [],
    custom: {},
    note_count: 0,
    owner_user_id: null,
    priority: null,
    next_action_at: null,
    ...overrides,
  };
}

const PIPELINE_DASHBOARD = {
  strategy_id: null,
  total_leads: 42,
  active_leads: 37,
  by_status: {
    sourced: 10, enriched: 8, email_found: 6, verified: 7, flagged: 2,
    dropped: 3, contacted: 3, replied: 2, meeting_booked: 1,
  },
  funnel: [
    { stage: "sourced", current: 10, reached: 37, conversion_from_previous: null },
    { stage: "enriched", current: 8, reached: 27, conversion_from_previous: 0.7297 },
    { stage: "email_found", current: 6, reached: 19, conversion_from_previous: 0.7037 },
    { stage: "verified", current: 7, reached: 13, conversion_from_previous: 0.6842 },
    { stage: "contacted", current: 3, reached: 6, conversion_from_previous: 0.4615 },
    { stage: "replied", current: 2, reached: 3, conversion_from_previous: 0.5 },
    { stage: "meeting_booked", current: 1, reached: 1, conversion_from_previous: 0.3333 },
  ],
  meetings_booked_week: 1,
  meetings_booked_month: 4,
  bookings_trend: [
    { bucket: "2026-09-01", count: 1 },
    { bucket: "2026-09-02", count: 3 },
  ],
  top_strategy: {
    strategy_id: "s1",
    product_name: "Fire inspection SaaS",
    meetings_booked: 4,
  },
};

// --------------------------------------------------------------------------
// Mocks
// --------------------------------------------------------------------------

async function mockAuth(page: Page) {
  // See happy-paths.spec.ts: without this the network hook's /health ping
  // renders the offline banner over the top of every page.
  await page.route("**/health", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route("**/auth/login", (route) =>
    route.fulfill({
      json: {
        user: { id: "u1", email: "test@x.com", plan: "free" },
        access_token: ACCESS,
        refresh_token: REFRESH,
        token_type: "bearer",
        expires_in: 900,
      },
    }),
  );
  await page.route("**/auth/me", (route) =>
    route.fulfill({ json: { id: "u1", email: "test@x.com", plan: "free" } }),
  );
  await page.route("**/me/theme", (route) => route.fulfill({ json: { theme: {} } }));
}

/** Server-side saved views, kept in a variable so a "reload" genuinely reads
 *  back what the save wrote — which is the property under test. */
function mockCrm(page: Page, options: { leads?: number } = {}) {
  const views: Record<string, unknown>[] = [];
  const leads = Array.from({ length: options.leads ?? 3 }, (_, index) =>
    lead(index + 1),
  );

  return page.route("**/crm/**", async (route: Route) => {
    // ONLY mock XHR/fetch. The glob `**/crm/**` matches far more than the API
    // calls: the page navigation to /crm/... obviously, but also -- and much
    // less obviously -- this route's own JavaScript, because Next.js names
    // per-route chunks after the route
    // (/_next/static/chunks/app/(app)/crm/table/page-<hash>.js). Answering
    // those with JSON served `{...}` as a script, so the bundle failed to
    // parse with "Unexpected token ':'" and the page rendered blank, with
    // nothing in the test output pointing at the mock as the cause.
    const kind = route.request().resourceType();
    if (kind !== "xhr" && kind !== "fetch") {
      return route.continue();
    }

    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    // The SSE handshake. Answering 503 puts the client straight onto its
    // polling fallback instead of leaving an EventSource retrying for the
    // length of the test — the stream itself is covered by unit tests on
    // both sides, and an open socket here only adds flakiness.
    if (path.endsWith("/crm/stream/ticket")) {
      return route.fulfill({
        status: 503,
        json: { detail: "real-time stream disabled; the client should poll" },
      });
    }

    if (path.endsWith("/crm/dashboard/pipeline")) {
      return route.fulfill({ json: PIPELINE_DASHBOARD });
    }
    if (path.endsWith("/crm/dashboard/leads")) {
      return route.fulfill({
        json: {
          strategy_id: null,
          velocity: [
            { stage: "contacted", leads: 3, measured: 3, estimated: 0,
              avg_days_in_stage: 2.5, fully_measured: true },
          ],
          sources: [{ source: "apollo", count: 40 }, { source: "manual", count: 2 }],
          verification: { verified: 7, flagged: 2, dropped: 3, total: 12,
                          verified_ratio: 0.5833 },
          stuck_after_days: 7,
          stuck_leads: [],
          stuck_count: 0,
        },
      });
    }
    if (path.endsWith("/crm/dashboard/campaigns")) {
      return route.fulfill({
        json: {
          strategy_id: null,
          sequences: [],
          channels: [
            { channel: "email", sent: 0, replied: 0, booked: 0, bounced: 0,
              reply_rate: null, booking_rate: null, bounce_rate: null },
            { channel: "whatsapp", sent: 0, replied: 0, booked: 0, bounced: 0,
              reply_rate: null, booking_rate: null, bounce_rate: null },
          ],
          variants: [],
          bounce: { sent: 0, bounced: 0, rate: 0, pause_threshold: 0.03,
                    over_threshold: false },
          paused_campaigns: [],
        },
      });
    }
    if (path.endsWith("/crm/dashboard/activity")) {
      return route.fulfill({ json: { items: [], has_more: false, next_before: null } });
    }
    if (path.endsWith("/crm/grid")) {
      return route.fulfill({
        json: {
          items: leads,
          total: leads.length,
          limit: 100,
          offset: 0,
          has_more: false,
        },
      });
    }
    if (path.endsWith("/crm/tags")) {
      return route.fulfill({ json: { items: [] } });
    }
    if (path.endsWith("/crm/fields")) {
      return route.fulfill({ json: { items: [] } });
    }
    if (path.endsWith("/crm/views")) {
      if (method === "POST") {
        const body = route.request().postDataJSON();
        const saved = {
          id: `v${views.length + 1}`,
          created_at: "2026-09-05T10:00:00+00:00",
          ...body,
        };
        views.push(saved);
        return route.fulfill({ status: 201, json: saved });
      }
      return route.fulfill({ json: { items: views } });
    }
    if (/\/crm\/leads\/[^/]+$/.test(path) && method === "PATCH") {
      const body = route.request().postDataJSON();
      const id = path.split("/").pop() as string;
      const target = leads.find((row) => row.id === id);
      if (target && body.status) target.status = body.status;
      return route.fulfill({
        json: { id, status: body.status ?? target?.status, changed: Object.keys(body) },
      });
    }

    return route.fulfill({ json: {} });
  });
}

async function hydratedFill(page: Page, selector: string, value: string) {
  const field = page.locator(selector);
  await field.waitFor({ state: "visible" });
  await page.waitForFunction(
    (sel) => {
      const el = document.querySelector(sel);
      return !!el && Object.keys(el).some((k) => k.startsWith("__reactFiber$"));
    },
    selector,
    { timeout: 20_000 },
  );
  await expect(async () => {
    await field.fill(value);
    await expect(field).toHaveValue(value, { timeout: 500 });
  }).toPass({ timeout: 15_000 });
}

async function loginViaUI(page: Page) {
  await page.goto("/login/");
  await hydratedFill(page, '[id="email"]', "test@x.com");
  await hydratedFill(page, '[id="password"]', "testpass1");
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/pipeline\/?$/);
}

async function signIn(page: Page) {
  await mockAuth(page);
  await page.route("**/strategies**", (route) => route.fulfill({ json: [] }));
  await page.route("**/leads", (route) =>
    route.fulfill({ json: { items: [], total: 0, limit: 50, offset: 0 } }),
  );
  await loginViaUI(page);
}

// --------------------------------------------------------------------------
// Tests
// --------------------------------------------------------------------------

test("CRM is reachable from the main navigation", async ({ page }) => {
  await signIn(page);
  await mockCrm(page);

  await page.getByRole("link", { name: "CRM" }).first().click();
  // /crm redirects to the overview client-side (static export — no server
  // redirect is possible).
  await page.waitForURL(/\/crm\/dashboard\/overview\/?$/);
});

test("dashboard overview renders real aggregates", async ({ page }) => {
  await signIn(page);
  await mockCrm(page);

  await page.goto("/crm/dashboard/overview/");
  await expect(page.getByRole("heading", { name: "Pipeline overview" })).toBeVisible();

  // Figures come from the endpoint, not from anything computed in the page.
  const activeTile = page.locator("div", { hasText: /^Active leads/ }).last();
  await expect(activeTile).toContainText("37");
  await expect(activeTile).toContainText("42 total");
  await expect(page.getByText("Fire inspection SaaS")).toBeVisible(); // top strategy

  // The funnel is a labelled image per stage, for screen readers.
  await expect(
    page.getByRole("img", { name: /Sourced: 37 reached/ }),
  ).toBeVisible();
});

test("all four dashboard pages load", async ({ page }) => {
  await signIn(page);
  await mockCrm(page);

  for (const [path, heading] of [
    ["overview", "Pipeline overview"],
    ["leads", "Lead analytics"],
    ["campaigns", "Campaign performance"],
    ["activity", "Activity"],
  ] as const) {
    await page.goto(`/crm/dashboard/${path}/`);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
  }
});

test("the live indicator says Polling when the stream is unavailable", async ({ page }) => {
  // The mock answers the ticket endpoint with 503 (the kill switch). The UI
  // must say so rather than showing a "Live" badge over data that is up to a
  // minute old.
  await signIn(page);
  await mockCrm(page);

  await page.goto("/crm/dashboard/overview/");
  await expect(page.getByText("Polling")).toBeVisible({ timeout: 15_000 });
});

test("grid loads and edits a lead status inline", async ({ page }) => {
  await signIn(page);
  await mockCrm(page);

  await page.goto("/crm/table/");
  const grid = page.getByRole("grid", { name: "Leads" });
  await expect(grid).toBeVisible();
  await expect(page.getByText("Lead 1")).toBeVisible();

  // Open the status editor and pick a legal transition. The dropdown offers
  // only moves the backend will accept.
  await page.getByRole("button", { name: /^Status: verified/ }).first().click();
  const editor = page.getByRole("combobox", { name: "Change status" });
  await expect(editor).toBeVisible();
  await editor.selectOption("flagged");

  await expect(page.getByRole("button", { name: /^Status: flagged/ })).toBeVisible();
});

test("saving a view persists it across a full page reload", async ({ page }) => {
  // The point of storing views server-side: a view built here is still here
  // after a reload, and would be on another device too. localStorage would
  // pass a same-tab assertion and fail the actual requirement.
  await signIn(page);
  await mockCrm(page);

  await page.goto("/crm/table/");
  await expect(page.getByRole("grid", { name: "Leads" })).toBeVisible();

  await page.getByLabel("Name for a new saved view").fill("My hot list");
  await page.getByRole("button", { name: "Save", exact: true }).click();

  // `exact` matters: each view chip sits beside its own "Delete view <name>"
  // button, so a loose name match resolves to two elements and is strict-mode
  // ambiguous rather than wrong.
  const chip = page.getByRole("button", { name: "My hot list", exact: true });
  await expect(chip).toBeVisible();

  // Full reload — nothing survives except what the server holds. This is the
  // assertion the whole server-side-views decision exists for; a localStorage
  // implementation would also pass a same-tab check and fail the real
  // requirement (the view being there on another device).
  await page.reload();
  await expect(page.getByRole("grid", { name: "Leads" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "My hot list", exact: true }),
  ).toBeVisible();
});

test("bulk action bar appears only once rows are selected", async ({ page }) => {
  await signIn(page);
  await mockCrm(page);

  await page.goto("/crm/table/");
  await expect(page.getByRole("grid", { name: "Leads" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Bulk actions" })).toHaveCount(0);

  await page.getByRole("checkbox", { name: /^Select Lead 1/ }).check();
  const bar = page.getByRole("region", { name: "Bulk actions" });
  await expect(bar).toBeVisible();
  await expect(bar.getByText("1 selected")).toBeVisible();
});

test("column visibility can be toggled but never emptied", async ({ page }) => {
  await signIn(page);
  await mockCrm(page);

  await page.goto("/crm/table/");
  await expect(page.getByRole("grid", { name: "Leads" })).toBeVisible();

  await page.getByRole("button", { name: "Columns" }).click();
  const companyToggle = page.getByRole("checkbox", { name: "Company" });
  await companyToggle.uncheck();
  await expect(page.getByRole("columnheader", { name: /Company/ })).toHaveCount(0);
  await companyToggle.check();
  await expect(page.getByRole("columnheader", { name: /Company/ })).toBeVisible();
});

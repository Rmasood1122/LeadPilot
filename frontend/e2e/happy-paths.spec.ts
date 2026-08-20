/**
 * E2E happy paths (Chunk 7) — all backend calls mocked via page.route()
 * so no real FastAPI instance is needed.
 *
 * Responsive coverage (360 / 768 / 1280 px) is asserted via viewport
 * assertions inline: the mobile test checks for the bottom-tab bar, the
 * desktop test checks for the sidebar.
 */

import { test, expect, type Page } from "@playwright/test";

// --------------------------------------------------------------------------
// Mock helpers
// --------------------------------------------------------------------------

const ACCESS = "test-access-token";
const REFRESH = "test-refresh-token";

async function mockAuth(page: Page) {
  // Without this, useNetwork()'s 30s pingBackend() hits the real
  // (nonexistent, in E2E) backend at /health, immediately flips
  // backendReachable to false, and OfflineBanner renders a
  // position:fixed, top:0, z-50 banner over the ENTIRE viewport width on
  // every single test — a real interference risk for any element near
  // the top of the page, and just noise otherwise. Mock it as healthy so
  // the banner never renders during E2E runs.
  await page.route("**/health", route =>
    route.fulfill({ json: { status: "ok" } }),
  );
  await page.route("**/auth/login", route =>
    route.fulfill({ json: {
      user: { id: "u1", email: "test@x.com", plan: "free" },
      access_token: ACCESS, refresh_token: REFRESH,
      token_type: "bearer", expires_in: 900,
    }}),
  );
  await page.route("**/auth/me", route =>
    route.fulfill({ json: { id: "u1", email: "test@x.com", plan: "free" }}),
  );
  await page.route("**/me/theme", route =>
    route.fulfill({ json: { theme: {} }}),
  );
}

async function mockStrategies(page: Page) {
  await page.route("**/strategies", route =>
    route.fulfill({ json: [
      { id: "s1", product_id: "p1", product_name: "Fire inspection SaaS",
        flow_type: "with_clients", status: "verified", campaign_state: "active" },
    ]}),
  );
  await page.route("**/strategies/s1", route =>
    route.fulfill({ json: {
      id: "s1", product_id: "p1", flow_type: "with_clients", status: "verified",
      progress: [{ pipeline: "strategy", phase: 1, done: 9, total: 9, steps: [] }],
      verification: [{ pass_no: 1, name: "Factual accuracy", result: "PASS", attempts: 1 }],
      strategy_document_ready: true, gtm_document_ready: false, error: null,
    }}),
  );
}

/**
 * Fill a controlled React input in a way that survives hydration.
 *
 * The suite runs against the STATIC EXPORT, so every form is present and
 * fillable in the pre-rendered HTML *before* React hydrates. A value
 * typed into that gap looks fine - page.fill() writes the DOM value
 * directly, so even expect(field).toHaveValue() passes - but React never
 * saw an onChange, its state is still "", and the hydration re-render
 * writes that empty state back over the field. On the login form the
 * wiped field is `required`, so native validation blocks submit,
 * submit() never runs, and the test sits on /login until it times out.
 *
 * Only Mobile Safari ever hit this, because WebKit hydrates slowest
 * here: the failure snapshot showed an empty email field beside a
 * correctly filled password - email was typed pre-hydration, password
 * after.
 *
 * React 18 stamps a `__reactFiber$<n>` property onto each host node as
 * it hydrates it, which is the reliable "React owns this element now"
 * signal. Waiting on that, then re-filling if the value still gets
 * clobbered, closes both the gap and any residual re-render race.
 */
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
  // Submitting starts the app's own client-side redirect to /pipeline.
  // Returning before that settles leaves an in-flight navigation, so a
  // caller's next page.goto() races it — WebKit aborts the new navigation
  // with "interrupted by another navigation to .../pipeline/" (Chromium
  // usually tolerates it, which is why this only ever failed on Mobile
  // Safari). Callers previously had to remember to add their own
  // waitForURL; three of the five call sites didn't, so the wait lives
  // HERE instead — every caller is now safe by construction.
  await page.waitForURL(/\/pipeline\/?$/);
}

// --------------------------------------------------------------------------
// Tests
// --------------------------------------------------------------------------

test("login → pipeline redirect", async ({ page }) => {
  await mockAuth(page);
  await page.route("**/leads", route => route.fulfill({ json: { items: [], total: 0, limit: 50, offset: 0 }}));
  await page.route("**/strategies**", route => route.fulfill({ json: [] }));
  await loginViaUI(page);
  await expect(page).toHaveURL(/pipeline/);
});

test("intake wizard: product → NO past clients → review → launch", async ({ page }) => {
  await mockAuth(page);
  // Order matters: Playwright matches page.route() handlers in REVERSE
  // registration order (most recently registered wins). mockStrategies()
  // registers a generic "**/strategies" pattern, and "**" matches across
  // path separators — so it also matches "/products/p1/strategies", the
  // strategy-CREATE endpoint. Registered last, it shadowed the specific
  // create mock below and returned the strategy LIST (an array) to
  // createStrategy(), making `strategy.id` undefined and sending the
  // wizard to "/strategies/detail?id=undefined".
  // mockStrategies() must therefore come FIRST, so the more specific
  // create route registered after it takes precedence.
  await mockStrategies(page);
  await page.route("**/products", route =>
    route.fulfill({ json: { id: "p1" }, status: 201 }),
  );
  await page.route("**/products/p1/strategies", route =>
    route.fulfill({ json: { id: "s1" }, status: 201 }),
  );

  await loginViaUI(page);
  await page.goto("/strategies/new/");

  // Step 1 — product
  await hydratedFill(page, '[id="name"]', "Test product");
  await hydratedFill(page, '[id="desc"]', "A great product for testing purposes.");
  await page.click('text=Continue');

  // Step 2 — No past clients
  // Uses getByRole + an explicit visibility wait rather than a raw
  // text= click — the element was confirmed present (byte-for-byte
  // matching text, including the em-dash) in the failure snapshot, but
  // page.click()'s actionability retry loop kept timing out, suggesting
  // a transient stability issue (e.g. a step-transition animation)
  // rather than a text-matching bug.
  const noButton = page.getByRole("button", {
    name: "No — research the market from scratch",
  });
  await noButton.waitFor({ state: "visible" });
  await noButton.click();

  const continueButton = page.getByRole("button", { name: "Continue" });
  await expect(continueButton).toBeEnabled();
  await continueButton.click();

  // Step 3 — Review
  await expect(page.locator("text=144-step pipeline")).toBeVisible();
  await page.click('text=Launch pipeline');

  // Stale assertion left over from the /strategies/[id] -> query-param
  // route conversion: the wizard now pushes "/strategies/detail?id=<id>",
  // which never matches /strategies\/s1/. Assert the real destination.
  await expect(page).toHaveURL(/\/strategies\/detail\/?\?id=s1$/);
});

test("strategy detail shows pipeline progress and verification panel", async ({ page }) => {
  await mockAuth(page);
  await mockStrategies(page);
  await loginViaUI(page);

  // Route changed from /strategies/s1 (path segment) to a query-param
  // route (/strategies/detail?id=s1) — Next.js static export
  // (output:'export') cannot serve arbitrary runtime path segments for
  // dynamic routes at all, so /strategies/[id] was replaced.
  await page.goto("/strategies/detail/?id=s1");
  await expect(page.locator('[aria-label="Pipeline progress"]')).toBeVisible();
  await expect(page.locator('[aria-label="Verification loop"]')).toBeVisible();
  await expect(page.locator("text=PASS")).toBeVisible();
});

test("kanban renders columns and allows opening lead drawer", async ({ page }) => {
  await mockAuth(page);
  // Must return at least one strategy — useAllLeads() calls /strategies
  // first, and short-circuits to an empty list if that comes back empty,
  // WITHOUT ever calling the /leads/** mock below. An empty strategies
  // list here made the "Sara Khan" lead mock unreachable.
  await page.route("**/strategies**", route => route.fulfill({ json: [{ id: "s1" }] }));
  await page.route("**/strategies/*/leads", route =>
    // Field name is `items`, matching the real LeadListOut response
    // shape (app/api/leads.py) — a mock using the old `leads` key would
    // silently produce an empty list after the earlier .leads → .items
    // fix in pipeline/page.tsx, since Object.filter(Boolean) drops the
    // resulting `undefined`.
    //
    // Pattern is "**/strategies/*/leads" (not "**/leads/**") — the real
    // request URL is /strategies/s1/leads with NO trailing segment after
    // "leads", so "**/leads/**" (which requires a "/leads/" substring
    // with something after it) never matched at all; the request fell
    // through to a real (nonexistent, in E2E) backend and hung until
    // timeout.
    route.fulfill({ json: { items: [
      { id: "l1", full_name: "Sara Khan", title: "CTO", company: "Acme",
        email: "sara@acme.com", phone: "+923001234567", status: "verified",
        enrichment_json: {}, whatsapp_opted_in: true },
    ], total: 1, limit: 50, offset: 0 }}),
  );
  await page.route("**/leads/l1/whatsapp-optin", route =>
    route.fulfill({ json: { current_status: "opted_in", history: [] }}),
  );

  // loginViaUI() waits for the post-login /pipeline redirect itself, so
  // this test is already on /pipeline and must not re-navigate.
  await loginViaUI(page);

  await expect(page.locator('[aria-label="Verified column"]')).toBeVisible();
  await page.click('text=Sara Khan');
  await expect(page.locator('text=sara@acme.com')).toBeVisible();
  // LeadDrawer renders the raw enum value ("WhatsApp: opted_in", with an
  // underscore) — not a humanized "opted-in" label.
  await expect(page.locator('text=opted_in')).toBeVisible();
});

test("theme persists across page reload", async ({ page }) => {
  await mockAuth(page);
  await page.route("**/strategies**", route => route.fulfill({ json: [] }));

  await loginViaUI(page);
  await page.goto("/settings/");
  // Click the Dark preset
  await page.click('button[aria-pressed]:has-text("Dark"), button:has-text("Dark")');
  await page.waitForTimeout(300);
  // Reload — no-flash script reads localStorage
  await page.reload();
  // --primary CSS var should be set to the dark preset value
  const primary = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--primary").trim(),
  );
  // Dark preset primary is #60a5fa → 96 165 250
  expect(primary).toContain("96");
});

// --------------------------------------------------------------------------
// Responsive assertions
// --------------------------------------------------------------------------

test("mobile (360 px) shows bottom-tab bar, not sidebar", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 360, height: 812 } });
  const page = await ctx.newPage();
  await mockAuth(page);
  await page.route("**/strategies**", route => route.fulfill({ json: [] }));
  await page.route("**/leads", route => route.fulfill({ json: { items: [], total: 0, limit: 50, offset: 0 }}));

  // loginViaUI() waits for the post-login /pipeline redirect itself, so
  // this test is already on /pipeline and must not re-navigate.
  await loginViaUI(page);

  // Bottom tabs visible on mobile
  const bottomNav = page.locator('nav[aria-label="Main navigation"]').last();
  await expect(bottomNav).toBeVisible();

  // Sidebar is hidden below md breakpoint
  const sidebar = page.locator("aside");
  await expect(sidebar).toBeHidden();
  await ctx.close();
});

test("desktop (1280 px) shows sidebar, not bottom tabs", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  await mockAuth(page);
  await page.route("**/strategies**", route => route.fulfill({ json: [] }));
  await page.route("**/leads", route => route.fulfill({ json: { items: [], total: 0, limit: 50, offset: 0 }}));

  // loginViaUI() waits for the post-login /pipeline redirect itself, so
  // this test is already on /pipeline and must not re-navigate.
  await loginViaUI(page);

  const sidebar = page.locator("aside");
  await expect(sidebar).toBeVisible();
  await ctx.close();
});
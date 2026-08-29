/**
 * E2E — Feature 1, email verification on signup.
 *
 * Covers the browser half of the flow, which the pytest suite cannot reach:
 * where signup sends the user, what the check-email screen does, how the
 * login page renders each /auth/verify outcome, and the Shell gate that
 * catches a bookmarked dashboard URL.
 *
 * All backend calls are mocked with page.route(), matching the convention in
 * happy-paths.spec.ts — no FastAPI process is required. The BACKEND
 * behaviour those mocks stand in for is separately proven for real in
 * tests/test_email_verification.py (28 tests) and by the live HTTP run
 * recorded in docs/features/email-verification.md.
 *
 * Runs against the STATIC EXPORT in ./out, like the rest of this directory,
 * so what is under test is the artifact that actually ships. Note that
 * next.config.js sets trailingSlash:true — hence the /?$/ in URL assertions.
 */

import { test, expect, type Page } from "@playwright/test";

/**
 * WebKit needs more than Playwright's 30s default here.
 *
 * These tests run against the static export, so every assertion about a
 * useEffect-driven notice has to wait for React to hydrate first. On
 * Mobile Safari at workers:2 that hydration regularly takes 5-15s per
 * navigation, and a test doing a form fill plus two navigations exceeded 30s
 * -- non-deterministically, so a DIFFERENT test failed on each run while all
 * of them passed in isolation.
 *
 * This is slowness, not breakage, and the suite is configured with retries:0,
 * so the honest fix is to give the slow browser a budget it can actually meet
 * rather than to retry until it looks green. Measured: the whole file
 * completes in ~50s when the machine is idle.
 */
test.beforeEach(({}, testInfo) => {
  testInfo.setTimeout(90_000);
});

const ACCESS = "test-access-token";
const REFRESH = "test-refresh-token";
const EMAIL = "newuser@example.com";
const PASSWORD = "hunter22!";

/** Keep OfflineBanner from covering the top of every page — see mockAuth()
 *  in happy-paths.spec.ts for the full explanation. */
async function mockHealth(page: Page) {
  await page.route("**/health", (route) => route.fulfill({ json: { status: "ok" } }));
}

function userJson(emailVerified: boolean) {
  return { id: "u1", email: EMAIL, plan: "free", is_admin: false,
           email_verified: emailVerified };
}

function bundle(emailVerified: boolean, extra: Record<string, unknown> = {}) {
  return {
    user: userJson(emailVerified),
    access_token: ACCESS, refresh_token: REFRESH,
    token_type: "bearer", expires_in: 900,
    ...extra,
  };
}

/**
 * Fill a controlled React input in a way that survives hydration.
 *
 * Lifted verbatim from happy-paths.spec.ts, where the full reasoning lives:
 * against a static export a form is fillable BEFORE React hydrates, and a
 * value typed into that gap is silently wiped by the hydration re-render.
 * Only WebKit was ever slow enough to hit it, and the symptom is a test that
 * sits on the current URL until it times out.
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

/**
 * Wait until React has hydrated the page body.
 *
 * The ?verified= / ?error= notices are set inside a useEffect, so they simply
 * do not exist in the pre-rendered HTML -- they appear only after hydration.
 * expect()'s 5s default is enough for Chromium but NOT for WebKit running
 * against 2 parallel workers: every one of these assertions passed in
 * isolation and failed in the full run. Waiting on the hydration signal
 * instead of on a longer arbitrary timeout fixes the cause rather than
 * papering over it.
 */
async function waitForHydration(page: Page) {
  await page.waitForFunction(
    () =>
      Object.keys(document.body).some((k) => k.startsWith("__reactFiber$")) ||
      !!document.querySelector("form"),
    undefined,
    { timeout: 20_000 },
  );
}

/**
 * The page's OWN alert/status paragraphs.
 *
 * NOT getByRole("alert"): Next.js renders its route announcer as
 * <div role="alert" id="__next-route-announcer__"> on every page, and it wins
 * the match, so the assertion checked an empty div forever. Every notice this
 * app renders is a <p>, which makes the element name a reliable discriminator.
 */
const alertText = (page: Page) => page.locator('p[role="alert"]');
const statusText = (page: Page) => page.locator('p[role="status"]');

/**
 * Put a valid session in storage WITHOUT driving the login form.
 *
 * The two Shell-gate tests below are about what happens when an already
 * signed-in browser lands on a dashboard URL -- the bookmark / second tab /
 * restored session case. Reaching that state through the login UI made each
 * test perform two hydrated form fills and two navigations before the subject
 * under test even began, which on WebKit at 2 workers blew the 30s test
 * timeout (both passed in isolation). Seeding storage skips the irrelevant
 * prelude; login routing itself is covered by its own tests above.
 *
 * Keys mirror KEYS in src/lib/auth-session.ts. On web, storage.ts uses
 * sessionStorage -- deliberately, so tokens die with the tab.
 */
async function seedSession(page: Page) {
  await page.addInitScript(
    ([access, refresh]) => {
      window.sessionStorage.setItem("ch_access_token", access);
      window.sessionStorage.setItem("ch_refresh_token", refresh);
    },
    [ACCESS, REFRESH],
  );
}


// --------------------------------------------------------------------------
// Signup
// --------------------------------------------------------------------------

test("signup sends the user to check-email, NOT to the dashboard", async ({ page }) => {
  await mockHealth(page);
  await page.route("**/auth/signup", (route) =>
    route.fulfill({
      status: 201,
      json: bundle(false, { email_verification_required: true,
                            verification_email_sent: true }),
    }),
  );

  await page.goto("/signup/");
  await hydratedFill(page, '[id="email"]', EMAIL);
  await hydratedFill(page, '[id="password"]', PASSWORD);
  await page.click('button[type="submit"]');

  await page.waitForURL(/\/check-email\/?\?/);
  // The address is carried in the query string so the screen still works on a
  // cold load in a new tab.
  expect(page.url()).toContain(`email=${encodeURIComponent(EMAIL)}`);
  await expect(page.getByRole("heading", { name: /check your email/i })).toBeVisible();
  await expect(page.getByText(EMAIL)).toBeVisible();
});

test("signup whose email failed to send leads with resend, not 'check your inbox'",
  async ({ page }) => {
    await mockHealth(page);
    await page.route("**/auth/signup", (route) =>
      route.fulfill({
        status: 201,
        // The account WAS created; only the mail transport failed.
        json: bundle(false, { email_verification_required: true,
                              verification_email_sent: false }),
      }),
    );

    await page.goto("/signup/");
    await hydratedFill(page, '[id="email"]', EMAIL);
    await hydratedFill(page, '[id="password"]', PASSWORD);
    await page.click('button[type="submit"]');

    await page.waitForURL(/\/check-email\/?\?/);
    expect(page.url()).toContain("sent=false");
    await waitForHydration(page);
    await expect(alertText(page))
      .toContainText(/could not send the verification email/i, { timeout: 15_000 });
  });

test("a rejected signup stays on the page and shows the reason", async ({ page }) => {
  await mockHealth(page);
  await page.route("**/auth/signup", (route) =>
    route.fulfill({ status: 409, json: { detail: "account already exists" } }),
  );

  await page.goto("/signup/");
  await hydratedFill(page, '[id="email"]', EMAIL);
  await hydratedFill(page, '[id="password"]', PASSWORD);
  await page.click('button[type="submit"]');

  await expect(alertText(page)).toContainText("account already exists",
                                              { timeout: 15_000 });
  await expect(page).toHaveURL(/\/signup\/?$/);
});

// --------------------------------------------------------------------------
// Check-email screen
// --------------------------------------------------------------------------

test("resend button calls the API and confirms without leaking account existence",
  async ({ page }) => {
    await mockHealth(page);
    let resendBody: unknown = null;
    await page.route("**/auth/resend-verification", async (route) => {
      resendBody = route.request().postDataJSON();
      await route.fulfill({
        status: 202,
        json: { status: "accepted",
                detail: "If that address has an unverified account, a verification email has been sent." },
      });
    });

    await page.goto(`/check-email/?email=${encodeURIComponent(EMAIL)}`);
    await waitForHydration(page);
    await expect(page.locator('[id="email"]')).toHaveValue(EMAIL, { timeout: 15_000 });
    await page.click('button[type="submit"]');

    const status = statusText(page);
    await expect(status).toBeVisible({ timeout: 15_000 });
    // Hedged wording on purpose: the backend answers 202 whether or not the
    // address has an account, so a definite "sent!" would turn this screen
    // into an account-existence oracle.
    await expect(status).toContainText(/if that address has an unverified account/i);
    expect(resendBody).toEqual({ email: EMAIL });
  });

test("resend surfaces a rate limit as a wait instruction, not a raw error",
  async ({ page }) => {
    await mockHealth(page);
    await page.route("**/auth/resend-verification", (route) =>
      route.fulfill({ status: 429, json: { detail: { error: "rate_limit_exceeded" } } }),
    );

    await page.goto(`/check-email/?email=${encodeURIComponent(EMAIL)}`);
    await waitForHydration(page);
    await expect(page.locator('[id="email"]')).toHaveValue(EMAIL, { timeout: 15_000 });
    await page.click('button[type="submit"]');
    await expect(alertText(page)).toContainText(/too many requests/i, { timeout: 15_000 });
  });

test("check-email works on a cold load with no query string", async ({ page }) => {
  await mockHealth(page);
  await page.goto("/check-email/");
  await waitForHydration(page);
  await expect(page.getByRole("heading", { name: /check your email/i })).toBeVisible();
  // Nothing to prefill, so the form's own input is the fallback and the
  // submit button stays disabled until an address is typed.
  await expect(page.locator('[id="email"]')).toHaveValue("");
  await expect(page.locator('button[type="submit"]')).toBeDisabled();
});

// --------------------------------------------------------------------------
// The redirect back from GET /auth/verify
// --------------------------------------------------------------------------

test("login shows a success notice after ?verified=true", async ({ page }) => {
  await mockHealth(page);
  await page.goto("/login/?verified=true");
  await waitForHydration(page);
  await expect(statusText(page)).toContainText(/email verified/i);
});

test("login explains ?verified=already", async ({ page }) => {
  await mockHealth(page);
  await page.goto("/login/?verified=already");
  await waitForHydration(page);
  await expect(statusText(page)).toContainText(/already verified/i);
});

test("login offers a way out on ?error=expired", async ({ page }) => {
  await mockHealth(page);
  await page.goto("/login/?error=expired");
  await waitForHydration(page);
  const alert = alertText(page);
  await expect(alert).toContainText(/expired/i);
  // Must point at the fix, not just state the problem.
  await expect(alert).toContainText(/new one/i);
});

test("login explains ?error=invalid", async ({ page }) => {
  await mockHealth(page);
  await page.goto("/login/?error=invalid");
  await waitForHydration(page);
  await expect(alertText(page)).toContainText(/not valid/i);
});

// --------------------------------------------------------------------------
// Login routing
// --------------------------------------------------------------------------

test("logging in with an UNVERIFIED account goes to check-email", async ({ page }) => {
  await mockHealth(page);
  // Login SUCCEEDS while unverified, on purpose — otherwise there is no
  // session from which to press resend. The routing decision is the client's.
  await page.route("**/auth/login", (route) => route.fulfill({ json: bundle(false) }));

  await page.goto("/login/");
  await hydratedFill(page, '[id="email"]', EMAIL);
  await hydratedFill(page, '[id="password"]', PASSWORD);
  await page.click('button[type="submit"]');

  await page.waitForURL(/\/check-email\/?\?/);
  await expect(page.getByRole("heading", { name: /check your email/i })).toBeVisible();
});

test("logging in with a VERIFIED account reaches the dashboard", async ({ page }) => {
  await mockHealth(page);
  await page.route("**/auth/login", (route) => route.fulfill({ json: bundle(true) }));
  await page.route("**/auth/me", (route) => route.fulfill({ json: userJson(true) }));
  await page.route("**/me/theme", (route) => route.fulfill({ json: { theme: {} } }));
  await page.route("**/leads**", (route) =>
    route.fulfill({ json: { items: [], total: 0, limit: 50, offset: 0 } }));
  await page.route("**/strategies**", (route) => route.fulfill({ json: [] }));

  await page.goto("/login/");
  await hydratedFill(page, '[id="email"]', EMAIL);
  await hydratedFill(page, '[id="password"]', PASSWORD);
  await page.click('button[type="submit"]');

  await page.waitForURL(/\/pipeline\/?$/);
});

// --------------------------------------------------------------------------
// The Shell gate — a bookmarked dashboard URL
// --------------------------------------------------------------------------

test("a valid session whose account is unverified cannot sit on the dashboard",
  async ({ page }) => {
    await mockHealth(page);
    await seedSession(page);
    await page.route("**/me/theme", (route) => route.fulfill({ json: { theme: {} } }));
    await page.route("**/leads**", (route) =>
      route.fulfill({ json: { items: [], total: 0, limit: 50, offset: 0 } }));
    await page.route("**/strategies**", (route) => route.fulfill({ json: [] }));
    // The backend answers the way it does for an unverified account.
    await page.route("**/auth/me", (route) =>
      route.fulfill({ status: 403, json: { detail: "EMAIL_NOT_VERIFIED" } }));

    await page.goto("/pipeline/");

    await page.waitForURL(/\/check-email\/?/, { timeout: 20_000 });
    await expect(page.getByRole("heading", { name: /check your email/i })).toBeVisible();
  });

test("403 EMAIL_NOT_VERIFIED must NOT log the user out", async ({ page }) => {
  await mockHealth(page);
  await seedSession(page);
  await page.route("**/me/theme", (route) => route.fulfill({ json: { theme: {} } }));
  await page.route("**/leads**", (route) =>
    route.fulfill({ json: { items: [], total: 0, limit: 50, offset: 0 } }));
  await page.route("**/strategies**", (route) => route.fulfill({ json: [] }));

  // Count refresh attempts. A 401 would drive client.ts into
  // refresh-then-retry and end with a cleared session; a 403 must not.
  let refreshCalls = 0;
  await page.route("**/auth/refresh", async (route) => {
    refreshCalls += 1;
    await route.fulfill({ status: 401, json: { detail: "invalid token" } });
  });
  await page.route("**/auth/me", (route) =>
    route.fulfill({ status: 403, json: { detail: "EMAIL_NOT_VERIFIED" } }));

  await page.goto("/pipeline/");
  await page.waitForURL(/\/check-email\/?/, { timeout: 20_000 });

  expect(refreshCalls).toBe(0);
  // The session survived: still in storage, ready to work the instant the
  // emailed link is clicked -- no second login.
  const stored = await page.evaluate(() =>
    window.sessionStorage.getItem("ch_access_token"));
  expect(stored).toBe("test-access-token");
});

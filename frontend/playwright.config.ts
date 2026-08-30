import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for M5 E2E tests.
 *
 * The backend is mocked via page.route() inside each test — no running
 * FastAPI process is required during CI.
 *
 * Running locally with a real backend:
 *   1. Start the backend:  uvicorn app.main:app --port 8000
 *   2. Set NEXT_PUBLIC_API_URL=http://localhost:8000 in .env.local
 *   3. Start the frontend: npm run dev
 *   4. Run E2E: npm run e2e
 *
 * Note: Playwright browsers cannot download files in the sandbox
 * environment used for development. To run E2E tests that involve file
 * downloads, install browsers locally:
 *   npx playwright install chromium
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: 0,
  workers: 2,
  // 90s, not Playwright's default 30s.
  //
  // The default was never consistent with this suite's own login helper.
  // happy-paths.spec.ts::hydratedFill budgets 20s waiting for React to stamp
  // __reactFiber$ onto the field, then up to 15s of fill-and-verify retries --
  // 35s for ONE field. loginViaUI fills two, so login alone could legitimately
  // want 70s before the test body even starts. Against a 30s test timeout the
  // helper's retry logic could never actually run to completion: the test was
  // killed mid-retry and reported as a login failure.
  //
  // It only ever bit Mobile Safari, and only in a full parallel run: WebKit
  // hydrating the static export with 2 workers competing is the slow case.
  // Measured over two full runs before this change -- 104 passed / 2 failed
  // both times, with a DIFFERENT pair failing each time, and every one of them
  // passing in isolation. That is the signature of a budget overrun, not of a
  // broken assertion.
  //
  // Raising this weakens nothing. None of these are performance tests, and
  // every assertion inside them is unchanged; a test that is slow under load
  // is worth far more than one that is flaky, because a suite that cries wolf
  // stops being read at all.
  timeout: 90_000,
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    // "on-first-retry" never fires since retries:0 above — no retry ever
    // happens, so no trace/screenshot was ever actually captured on any
    // failure. Fixed to always retain diagnostics for failed tests.
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "Mobile Safari",
      use: { ...devices["iPhone 14"] },
    },
  ],
  // Serve the STATIC EXPORT (./out), not `next dev`.
  //
  // The app ships as output:'export' (Capacitor bundles the export into
  // the APK), so this tests the artifact that actually ships. It also
  // removes two dev-server-only failure classes that produced most of
  // this suite's historical flakiness:
  //   1. `next dev` compiles routes on demand; with workers:2 competing
  //      for one dev server, the first navigation to /pipeline exceeded
  //      expect()'s 5s timeout. The App Router holds the previous URL
  //      until the destination is ready, so the test saw the URL stuck at
  //      /login and reported a "login redirect" failure that was really
  //      compile latency. (Reproduced: passes at --workers=1, fails at 2.)
  //   2. Fast Refresh reloading pages mid-test when Playwright wrote into
  //      test-results/ (see next.config.js webpack.watchOptions.ignored).
  // Neither exists when serving pre-built static files.
  //
  // `npm run test:e2e` runs `next build` first, so ./out is always fresh.
  // Set PLAYWRIGHT_DEV_SERVER=1 to run against `next dev` instead (useful
  // when iterating on a component without rebuilding); expect the
  // compile-latency flakiness above if you do.
  webServer: process.env.PLAYWRIGHT_SKIP_SERVER
    ? undefined
    : {
        command: process.env.PLAYWRIGHT_DEV_SERVER
          ? "npm run dev"
          : "node scripts/static-server.js",
        url: "http://localhost:3000",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
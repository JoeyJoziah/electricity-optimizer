/**
 * Playwright E2E Configuration — RateShift
 *
 * Database migration coverage (Task 4.6 audit finding):
 * E2E tests do NOT use a real database. All backend API calls are intercepted
 * by Playwright route mocks registered in e2e/helpers/api-mocks.ts. The
 * webServer target is the Next.js dev server (port 3000); the FastAPI backend
 * is never started during E2E runs. Therefore applying database migrations
 * before E2E tests is NOT required and this task is N/A for this project.
 *
 * If a future test mode adds a real-backend integration mode, migrations
 * should be applied via `alembic upgrade head` in the webServer.command or
 * a globalSetup script before the E2E suite runs.
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  timeout: 30_000,
  expect: {
    timeout: 10_000,
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.02,
    },
  },
  outputDir: "./test-results",
  reporter: process.env.CI
    ? [
        ["html", { open: "never" }],
        ["junit", { outputFile: "test-results/e2e-results.xml" }],
        ["list"],
      ]
    : "html",
  metadata: {
    project: "rateshift",
    environment: process.env.CI ? "ci" : "local",
  },
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: process.env.CI ? "retain-on-failure" : "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
    {
      name: "Mobile Chrome",
      use: { ...devices["Pixel 5"] },
    },
    {
      name: "Mobile Safari",
      use: { ...devices["iPhone 12"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
  },
});

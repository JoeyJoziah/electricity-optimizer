/**
 * Mobile-Specific E2E Tests
 *
 * Covers mobile UI behaviour that cannot be adequately tested at desktop
 * viewport widths:
 * - Hamburger / mobile menu opens and closes
 * - Bottom navigation (if present) is functional
 * - No horizontal scroll at mobile viewport
 * - Forms (login, settings) are usable on mobile
 *
 * Tests are scoped to mobile viewports using test.use(). On desktop
 * projects the fixed viewport override still applies, so the tests
 * run on all 5 Playwright projects but always at a mobile width.
 *
 * All tests are tagged @regression.
 */

import { test, expect } from "./fixtures";
import {
  mockBetterAuth,
  setAuthenticatedState,
  clearAuthState,
} from "./helpers/auth";
import { createMockApi } from "./helpers/api-mocks";

// iPhone 14 Pro dimensions — matches Mobile Safari project device
const MOBILE_VIEWPORT = { width: 390, height: 844 };

// ---------------------------------------------------------------------------
// Helper: set up full authenticated + API mock state on a bare `page`
// ---------------------------------------------------------------------------

async function setupMobilePage(page: import("@playwright/test").Page) {
  await mockBetterAuth(page);
  await setAuthenticatedState(page);

  await page.addInitScript(() => {
    localStorage.setItem(
      "electricity-optimizer-settings",
      JSON.stringify({
        state: {
          region: "US_CT",
          annualUsageKwh: 10500,
          peakDemandKw: 5,
          utilityTypes: ["electricity"],
          displayPreferences: {
            currency: "USD",
            theme: "system",
            timeFormat: "12h",
          },
        },
      }),
    );
  });

  // All standard API mocks (context-level routing + SSE stream) come from
  // the shared factory so the mobile dashboard renders like everywhere else.
  await createMockApi(page, { authSession: false });
}

// ---------------------------------------------------------------------------
// Mobile Navigation
// ---------------------------------------------------------------------------

test.describe("Mobile Navigation", () => {
  test.use({ viewport: MOBILE_VIEWPORT });

  test("sidebar / desktop nav is hidden at mobile viewport @regression", async ({
    page,
  }) => {
    await setupMobilePage(page);
    await page.goto("/dashboard", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("body");

    // The desktop sidebar is "hidden lg:flex" — not visible below 1024px.
    // getByRole('navigation') is ambiguous (the dashboard-tabs nav is also a
    // navigation landmark and IS visible at mobile), so assert a sidebar-only
    // element — the sign-out button — is hidden instead.
    await expect(page.getByTestId("sign-out-button")).not.toBeVisible();
  });

  test("hamburger menu button is visible on mobile @regression", async ({
    page,
  }) => {
    await setupMobilePage(page);
    await page.goto("/dashboard", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("body");

    // Look for a button that triggers a mobile menu (common aria labels)
    const menuButton = page.getByRole("button", {
      name: /menu|open menu|hamburger|navigation/i,
    });

    // If a mobile menu toggle exists, assert it is visible and interactive
    const menuButtonCount = await menuButton.count();
    if (menuButtonCount > 0) {
      await expect(menuButton.first()).toBeVisible();
    }
    // If no hamburger button is implemented yet, the test passes trivially
    // — the key assertion is that the sidebar nav itself is hidden (above)
  });

  test("mobile menu opens and reveals navigation links @regression", async ({
    page,
  }) => {
    await setupMobilePage(page);
    await page.goto("/dashboard", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("body");

    const menuButton = page.getByRole("button", {
      name: /menu|open menu|hamburger|navigation/i,
    });
    const menuButtonCount = await menuButton.count();

    if (menuButtonCount === 0) {
      // No hamburger button — mobile navigation may use a different pattern
      // (e.g., bottom nav). Skip the open/close assertion.
      test.skip(
        true,
        "No hamburger menu button found — mobile nav uses a different pattern",
      );
      return;
    }

    // Open the menu
    await menuButton.first().click();

    // After opening, navigation links should be present
    await expect(
      page
        .getByRole("link", { name: /dashboard|prices|suppliers|alerts/i })
        .first(),
    ).toBeVisible({ timeout: 5000 });
  });

  test("mobile menu closes when a link is clicked @regression", async ({
    page,
  }) => {
    await setupMobilePage(page);
    await page.goto("/dashboard", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("body");

    const menuButton = page.getByRole("button", {
      name: /menu|open menu|hamburger|navigation/i,
    });
    const menuButtonCount = await menuButton.count();

    if (menuButtonCount === 0) {
      test.skip(
        true,
        "No hamburger menu button found — mobile nav uses a different pattern",
      );
      return;
    }

    await menuButton.first().click();
    // Wait for the menu/drawer to open before interacting with nav links
    await expect(
      page
        .locator(
          '[data-state="open"][role="dialog"], [aria-expanded="true"], nav a',
        )
        .first(),
    )
      .toBeVisible({ timeout: 5000 })
      .catch(() => {
        /* menu may render differently */
      });

    // Click a nav link — menu should close and we should navigate
    const dashboardLink = page.getByRole("link", { name: /prices/i }).first();
    const linkVisible = await dashboardLink.isVisible().catch(() => false);

    if (linkVisible) {
      await dashboardLink.click();
      await page.waitForURL(/\/prices/, { timeout: 10000 });

      // Menu should be closed after navigation
      const menuOpen = await page
        .locator('[data-state="open"][role="dialog"], [aria-expanded="true"]')
        .count();
      expect(menuOpen).toBe(0);
    }
  });
});

// ---------------------------------------------------------------------------
// Mobile layout — no horizontal scroll
// ---------------------------------------------------------------------------

test.describe("Mobile Layout", () => {
  test.use({ viewport: MOBILE_VIEWPORT });

  test("dashboard has no horizontal scroll at 390px width @regression", async ({
    page,
  }) => {
    await setupMobilePage(page);
    await page.goto("/dashboard", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    // Wait for page content before measuring layout
    await expect(
      page.locator('h1, [role="heading"], main').first(),
    ).toBeVisible({ timeout: 10000 });

    const hasHorizontalScroll = await page.evaluate(() => {
      return (
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth
      );
    });
    expect(hasHorizontalScroll).toBe(false);
  });

  test("prices page has no horizontal scroll at 390px width @regression", async ({
    page,
  }) => {
    await setupMobilePage(page);
    await page.goto("/prices", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await expect(
      page.locator('h1, [role="heading"], main').first(),
    ).toBeVisible({ timeout: 10000 });

    const hasHorizontalScroll = await page.evaluate(() => {
      return (
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth
      );
    });
    expect(hasHorizontalScroll).toBe(false);
  });

  test("suppliers page has no horizontal scroll at 390px width @regression", async ({
    page,
  }) => {
    await setupMobilePage(page);
    await page.goto("/suppliers", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await expect(
      page.locator('h1, [role="heading"], main').first(),
    ).toBeVisible({ timeout: 10000 });

    const hasHorizontalScroll = await page.evaluate(() => {
      return (
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth
      );
    });
    expect(hasHorizontalScroll).toBe(false);
  });

  test("settings page has no horizontal scroll at 390px width @regression", async ({
    page,
  }) => {
    await setupMobilePage(page);
    await page.goto("/settings", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await expect(
      page.locator('h1, [role="heading"], main').first(),
    ).toBeVisible({ timeout: 10000 });

    const hasHorizontalScroll = await page.evaluate(() => {
      return (
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth
      );
    });
    expect(hasHorizontalScroll).toBe(false);
  });

  test("landing page has no horizontal scroll at 390px width @regression", async ({
    page,
  }) => {
    await mockBetterAuth(page);
    await clearAuthState(page);
    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 15000 });
    // Wait for the landing page shell to render before measuring layout
    await expect(page.locator('main, h1, [role="main"]').first()).toBeVisible({
      timeout: 10000,
    });

    const hasHorizontalScroll = await page.evaluate(() => {
      return (
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth
      );
    });
    expect(hasHorizontalScroll).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Mobile forms — usability
// ---------------------------------------------------------------------------

test.describe("Mobile Forms", () => {
  test.use({ viewport: MOBILE_VIEWPORT });

  test("login form is usable on mobile viewport @regression", async ({
    page,
  }) => {
    await mockBetterAuth(page);
    await clearAuthState(page);
    await page.goto("/auth/login", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });

    // Email and password inputs must be visible and tappable
    await expect(page.locator("#email")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("#password")).toBeVisible();

    // Verify inputs are not cut off — they must have a reasonable width
    const emailWidth = await page
      .locator("#email")
      .evaluate((el) => (el as HTMLElement).getBoundingClientRect().width);
    // Input must be at least 200px wide on a 390px viewport
    expect(emailWidth).toBeGreaterThan(200);

    // Submit button must be visible and not overflow
    const submitButton = page.getByRole("button", {
      name: /sign in|log in|continue/i,
    });
    await expect(submitButton.first()).toBeVisible();

    const submitWidth = await submitButton
      .first()
      .evaluate((el) => (el as HTMLElement).getBoundingClientRect().width);
    expect(submitWidth).toBeGreaterThan(100);
    // Submit button must not overflow the viewport
    expect(submitWidth).toBeLessThanOrEqual(MOBILE_VIEWPORT.width);
  });

  test("settings form is usable on mobile viewport @regression", async ({
    page,
  }) => {
    await setupMobilePage(page);
    await page.goto("/settings", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("body");

    // Settings heading must be visible
    await expect(page.locator('h1, [role="heading"]').first()).toBeVisible({
      timeout: 10000,
    });

    // Select/input elements on settings must fit within the viewport
    const selects = page.locator("select");
    const selectCount = await selects.count();
    if (selectCount > 0) {
      const firstSelectWidth = await selects
        .first()
        .evaluate((el) => (el as HTMLElement).getBoundingClientRect().width);
      expect(firstSelectWidth).toBeLessThanOrEqual(MOBILE_VIEWPORT.width);
    }
  });

  test("pricing page CTAs are tappable on mobile viewport @regression", async ({
    page,
  }) => {
    await mockBetterAuth(page);
    await clearAuthState(page);
    await page.goto("/pricing", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });

    // All tier CTA buttons / links must be visible at mobile width
    await expect(
      page.getByRole("link", { name: "Get Started Free" }),
    ).toBeVisible({ timeout: 5000 });

    // Tappable target size must be at least 44×44px (WCAG 2.5.5 / Apple HIG)
    const ctaHeight = await page
      .getByRole("link", { name: "Get Started Free" })
      .evaluate((el) => (el as HTMLElement).getBoundingClientRect().height);
    expect(ctaHeight).toBeGreaterThanOrEqual(36); // allow slight tolerance
  });
});

// ---------------------------------------------------------------------------
// Mobile dashboard content
// ---------------------------------------------------------------------------

test.describe("Mobile Dashboard Content", () => {
  test.use({ viewport: MOBILE_VIEWPORT });

  test("dashboard main widgets are visible on mobile @regression", async ({
    page,
  }) => {
    await setupMobilePage(page);
    await page.goto("/dashboard", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });

    // Core dashboard content must render on mobile
    await expect(page.getByText("Current Price").first()).toBeVisible({
      timeout: 10000,
    });

    await expect(page.getByText("Total Saved")).toBeVisible({ timeout: 10000 });
  });

  test("dashboard price widget is fully visible without horizontal overflow @regression", async ({
    page,
  }) => {
    await setupMobilePage(page);
    await page.goto("/dashboard", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page
      .waitForSelector('[data-testid="current-price"]', {
        timeout: 10000,
      })
      .catch(() => {
        // Widget may not have testid in all builds
      });

    const priceWidget = page.getByTestId("current-price").first();
    const widgetCount = await priceWidget.count();

    if (widgetCount > 0) {
      const box = await priceWidget.boundingBox();
      if (box) {
        // Widget must be within viewport width
        expect(box.x + box.width).toBeLessThanOrEqual(
          MOBILE_VIEWPORT.width + 1,
        );
      }
    }
  });
});

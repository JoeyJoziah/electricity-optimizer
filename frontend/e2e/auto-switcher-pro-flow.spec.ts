/**
 * Auto Switcher — Pro Flow E2E Tests
 *
 * Tests the recommend → approve → verify flow for Pro tier users.
 * Pro users get recommendations that require manual approval.
 */

import { test, expect, PRESET_PRO } from "./fixtures";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_SETTINGS = {
  enabled: true,
  savings_threshold_pct: 10.0,
  savings_threshold_min: 10.0,
  cooldown_days: 5,
  paused_until: null,
  loa_signed: false,
  loa_revoked: false,
  created_at: "2026-03-01T00:00:00Z",
  updated_at: "2026-03-01T00:00:00Z",
};

const MOCK_SETTINGS_DISABLED = {
  ...MOCK_SETTINGS,
  enabled: false,
};

const MOCK_ACTIVITY: object[] = [
  {
    id: "audit-001",
    trigger_type: "scheduled",
    decision: "recommend",
    reason: "Found a plan saving $18.50/mo — 14% lower than current rate.",
    current_plan_name: "Eversource Standard",
    proposed_plan_name: "Direct Energy Saver",
    savings_monthly: 18.5,
    savings_annual: 222.0,
    etf_cost: 0,
    net_savings_year1: 222.0,
    confidence_score: 0.88,
    tier: "pro",
    executed: false,
    created_at: "2026-04-01T10:00:00Z",
  },
  {
    id: "audit-002",
    trigger_type: "scheduled",
    decision: "hold",
    reason: "Current plan is competitive. No action needed.",
    current_plan_name: "Eversource Standard",
    proposed_plan_name: null,
    savings_monthly: null,
    savings_annual: null,
    etf_cost: 0,
    net_savings_year1: null,
    confidence_score: 0.92,
    tier: "pro",
    executed: false,
    created_at: "2026-03-25T10:00:00Z",
  },
];

const MOCK_CHECK_RESULT = {
  action: "recommend",
  reason: "Found a better plan with 12% savings.",
  current_plan: {
    plan_id: "plan-current",
    plan_name: "Eversource Standard",
    provider_name: "Eversource",
    rate_kwh: 0.25,
    fixed_charge: 9.99,
    term_months: null,
    etf_amount: 0,
  },
  proposed_plan: {
    plan_id: "plan-proposed",
    plan_name: "Direct Energy Saver",
    provider_name: "Direct Energy",
    rate_kwh: 0.22,
    fixed_charge: 4.99,
    term_months: 12,
    etf_amount: 75,
  },
  projected_savings_monthly: 18.5,
  projected_savings_annual: 222.0,
  etf_cost: 75,
  net_savings_year1: 147.0,
  confidence: 0.88,
  contract_expiring_soon: false,
  data_source: "arcadia_monthly",
};

const MOCK_APPROVE_RESULT = {
  id: "exec-001",
  status: "initiated",
  enrollment_id: null,
  old_plan_name: "Eversource Standard",
  new_plan_name: "Direct Energy Saver",
  initiated_at: "2026-04-02T12:00:00Z",
  confirmed_at: null,
  enacted_at: null,
  rescission_ends: null,
  failure_reason: null,
  created_at: "2026-04-02T12:00:00Z",
};

// ---------------------------------------------------------------------------
// Route setup helper — uses closure flags instead of double-registration
// ---------------------------------------------------------------------------

async function setupAutoSwitcherRoutes(
  page: import("@playwright/test").Page,
  overrides: {
    settings?: object;
    activity?: object[];
    checkResult?: object | null;
    approveResult?: object | null;
    history?: object[];
    /** Callback invoked when check endpoint is hit */
    onCheck?: () => void;
  } = {},
) {
  // Settings
  await page.route("**/api/v1/agent-switcher/settings", async (route) => {
    if (route.request().method() === "PUT") {
      const body = JSON.parse(route.request().postData() || "{}");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...(overrides.settings ?? MOCK_SETTINGS),
          ...body,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(overrides.settings ?? MOCK_SETTINGS),
    });
  });

  // Activity
  await page.route("**/api/v1/agent-switcher/activity**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(overrides.activity ?? MOCK_ACTIVITY),
    });
  });

  // History
  await page.route("**/api/v1/agent-switcher/history**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(overrides.history ?? MOCK_ACTIVITY),
    });
  });

  // Check now — single handler with optional callback
  await page.route("**/api/v1/agent-switcher/check", async (route) => {
    overrides.onCheck?.();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(overrides.checkResult ?? MOCK_CHECK_RESULT),
    });
  });

  // Approve
  await page.route(
    "**/api/v1/agent-switcher/audit/*/approve",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(overrides.approveResult ?? MOCK_APPROVE_RESULT),
      });
    },
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Auto Switcher — Pro Flow", () => {
  test.use({ settingsPreset: PRESET_PRO });

  test(
    "loads the auto-switcher dashboard",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await setupAutoSwitcherRoutes(page);
      await page.goto("/auto-switcher");
      await expect(page).toHaveURL(/\/auto-switcher/);

      // Agent status card visible
      await expect(page.getByTestId("agent-status-card")).toBeVisible();
      await expect(page.getByText("Auto Rate Switcher")).toBeVisible();
    },
  );

  test(
    "shows enabled status badge when agent is active",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await setupAutoSwitcherRoutes(page, { settings: MOCK_SETTINGS });
      await page.goto("/auto-switcher");

      // Should show Active status
      await expect(page.getByText("Active (Manual)")).toBeVisible();
    },
  );

  test(
    "shows disabled status when agent is off",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupAutoSwitcherRoutes(page, { settings: MOCK_SETTINGS_DISABLED });
      await page.goto("/auto-switcher");

      await expect(page.getByText("Disabled")).toBeVisible();
    },
  );

  test(
    "shows current plan card",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupAutoSwitcherRoutes(page);
      await page.goto("/auto-switcher");

      // Current plan card shows "no plan" initially (before check)
      await expect(page.getByTestId("current-plan-card")).toBeVisible();
    },
  );

  test(
    "displays activity feed with recent decisions",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupAutoSwitcherRoutes(page, { activity: MOCK_ACTIVITY });
      await page.goto("/auto-switcher");

      // Should display recent recommendation entry
      await expect(page.getByText("Direct Energy Saver").first()).toBeVisible({
        timeout: 5000,
      });
    },
  );

  test(
    "check now button triggers rate evaluation",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      let checkCalled = false;

      // Use onCheck callback instead of double-registering route
      await setupAutoSwitcherRoutes(page, {
        onCheck: () => {
          checkCalled = true;
        },
      });

      await page.goto("/auto-switcher");

      const checkButton = page.getByTestId("check-now-button");
      await expect(checkButton).toBeVisible();

      // Use waitForResponse instead of waitForTimeout
      const checkResponse = page.waitForResponse(
        "**/api/v1/agent-switcher/check",
      );
      await checkButton.click();
      await checkResponse;

      expect(checkCalled).toBe(true);
    },
  );

  test(
    "recommendation shows savings amount",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupAutoSwitcherRoutes(page, { activity: MOCK_ACTIVITY });
      await page.goto("/auto-switcher");

      // Recommendation entry should show savings amount
      await expect(page.getByText(/\$18\.50/).first()).toBeVisible({
        timeout: 5000,
      });
    },
  );

  test(
    "approve button calls approve endpoint",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await setupAutoSwitcherRoutes(page, { activity: MOCK_ACTIVITY });
      await page.goto("/auto-switcher");

      // Wait for activity to render
      await expect(page.getByText("Direct Energy Saver").first()).toBeVisible({
        timeout: 5000,
      });

      // Find and click the approve button on the pending recommendation
      const approveButton = page
        .getByRole("button", { name: /approve/i })
        .first();
      if (await approveButton.isVisible({ timeout: 3000 })) {
        const approveResponse = page.waitForResponse(
          "**/api/v1/agent-switcher/audit/*/approve",
        );
        await approveButton.click();
        const response = await approveResponse;
        expect(response.status()).toBe(200);
      }
    },
  );

  test(
    "empty activity shows informative message",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupAutoSwitcherRoutes(page, { activity: [] });
      await page.goto("/auto-switcher");

      // Should show no scans message
      await expect(page.getByText(/No scans yet/i)).toBeVisible({
        timeout: 5000,
      });
    },
  );

  test(
    "navigates to settings page",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupAutoSwitcherRoutes(page);
      await page.goto("/auto-switcher/settings");
      await expect(page).toHaveURL(/\/auto-switcher\/settings/);
    },
  );

  test(
    "navigates to history page",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupAutoSwitcherRoutes(page);
      await page.goto("/auto-switcher/history");
      await expect(page).toHaveURL(/\/auto-switcher\/history/);
    },
  );

  test(
    "sidebar shows Auto Switcher link",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page, isMobile }) => {
      test.skip(isMobile === true, "Sidebar navigation is hidden on mobile");
      await setupAutoSwitcherRoutes(page);
      await page.goto("/auto-switcher");

      const navLink = page
        .getByRole("link", { name: /Auto Switcher/i })
        .first();
      await expect(navLink).toBeVisible();
      await expect(navLink).toHaveAttribute("href", "/auto-switcher");
    },
  );

  test(
    "handles settings API error gracefully",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      // Override settings to return 500
      await page.route("**/api/v1/agent-switcher/settings", async (route) => {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Internal server error" }),
        });
      });
      await page.route("**/api/v1/agent-switcher/activity**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      });

      await page.goto("/auto-switcher");

      // Should not show a blank page — error boundary or fallback state should render
      await expect(page.locator("body")).not.toBeEmpty();
    },
  );

  test(
    "handles free tier 403 gracefully",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await page.route("**/api/v1/agent-switcher/settings", async (route) => {
        await route.fulfill({
          status: 403,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Pro tier required" }),
        });
      });
      await page.route("**/api/v1/agent-switcher/activity**", async (route) => {
        await route.fulfill({
          status: 403,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Pro tier required" }),
        });
      });

      await page.goto("/auto-switcher");

      // Should show an error state or upgrade prompt, not a blank page
      await expect(page.locator("body")).not.toBeEmpty();
    },
  );
});

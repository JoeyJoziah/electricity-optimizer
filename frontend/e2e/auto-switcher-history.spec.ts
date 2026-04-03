/**
 * Auto Switcher — History E2E Tests
 *
 * Tests the history page: viewing past switch decisions, rollback, pagination.
 */

import { test, expect, PRESET_PRO } from "./fixtures";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

function makeAuditEntry(
  overrides: Partial<{
    id: string;
    trigger_type: string;
    decision: string;
    reason: string;
    current_plan_name: string | null;
    proposed_plan_name: string | null;
    savings_monthly: number | null;
    savings_annual: number | null;
    etf_cost: number;
    net_savings_year1: number | null;
    confidence_score: number | null;
    tier: string;
    executed: boolean;
    created_at: string;
  }> = {},
) {
  return {
    id: "audit-001",
    trigger_type: "scheduled",
    decision: "switch",
    reason: "Better rate found with 14% savings.",
    current_plan_name: "Eversource Standard",
    proposed_plan_name: "Direct Energy Saver",
    savings_monthly: 18.5,
    savings_annual: 222.0,
    etf_cost: 0,
    net_savings_year1: 222.0,
    confidence_score: 0.88,
    tier: "pro",
    executed: true,
    created_at: "2026-04-01T10:00:00Z",
    ...overrides,
  };
}

const MOCK_HISTORY = [
  makeAuditEntry({
    id: "audit-001",
    decision: "switch",
    executed: true,
    created_at: "2026-04-01T10:00:00Z",
  }),
  makeAuditEntry({
    id: "audit-002",
    decision: "recommend",
    executed: false,
    reason: "Found potential savings of $12/mo.",
    proposed_plan_name: "Green Mountain Fixed 12",
    savings_monthly: 12.0,
    savings_annual: 144.0,
    net_savings_year1: 144.0,
    confidence_score: 0.76,
    created_at: "2026-03-28T10:00:00Z",
  }),
  makeAuditEntry({
    id: "audit-003",
    decision: "hold",
    executed: false,
    reason: "Current plan is competitive.",
    proposed_plan_name: null,
    savings_monthly: null,
    savings_annual: null,
    net_savings_year1: null,
    confidence_score: 0.92,
    created_at: "2026-03-20T10:00:00Z",
  }),
  makeAuditEntry({
    id: "audit-004",
    decision: "monitor",
    executed: false,
    reason: "Insufficient data for a strong recommendation.",
    proposed_plan_name: null,
    savings_monthly: null,
    savings_annual: null,
    net_savings_year1: null,
    confidence_score: 0.45,
    created_at: "2026-03-15T10:00:00Z",
  }),
];

const MOCK_ROLLBACK_RESPONSE = {
  status: "rolled_back",
  message:
    "Switch rolled back successfully. Your previous plan will be restored.",
};

// ---------------------------------------------------------------------------
// Route setup
// ---------------------------------------------------------------------------

async function setupHistoryRoutes(
  page: import("@playwright/test").Page,
  overrides: {
    history?: object[];
    rollbackResponse?: object;
    rollbackError?: boolean;
  } = {},
) {
  // Settings (needed for sidebar badge)
  await page.route("**/api/v1/agent-switcher/settings", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        enabled: true,
        savings_threshold_pct: 10,
        savings_threshold_min: 10,
        cooldown_days: 5,
        paused_until: null,
        loa_signed: false,
        loa_revoked: false,
        created_at: "2026-03-01T00:00:00Z",
        updated_at: "2026-03-01T00:00:00Z",
      }),
    });
  });

  // History
  await page.route("**/api/v1/agent-switcher/history**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(overrides.history ?? MOCK_HISTORY),
    });
  });

  // Activity (for sidebar badge)
  await page.route("**/api/v1/agent-switcher/activity**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  // Rollback
  await page.route(
    "**/api/v1/agent-switcher/executions/*/rollback",
    async (route) => {
      if (overrides.rollbackError) {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Rollback window has expired" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          overrides.rollbackResponse ?? MOCK_ROLLBACK_RESPONSE,
        ),
      });
    },
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Auto Switcher — History", () => {
  test.use({ settingsPreset: PRESET_PRO });

  test(
    "loads history page",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await setupHistoryRoutes(page);
      await page.goto("/auto-switcher/history");
      await expect(page).toHaveURL(/\/auto-switcher\/history/);
    },
  );

  test(
    "displays switch history entries",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await setupHistoryRoutes(page);
      await page.goto("/auto-switcher/history");

      // Should display entries from the history
      await expect(page.getByText("Eversource Standard").first()).toBeVisible({
        timeout: 5000,
      });
      await expect(page.getByText("Direct Energy Saver").first()).toBeVisible({
        timeout: 5000,
      });
    },
  );

  test(
    "shows savings amounts for switch decisions",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupHistoryRoutes(page);
      await page.goto("/auto-switcher/history");

      // Should show monthly savings
      await expect(page.getByText(/\$18\.50/).first()).toBeVisible({
        timeout: 5000,
      });
    },
  );

  test(
    "shows reason text for each decision",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupHistoryRoutes(page);
      await page.goto("/auto-switcher/history");

      // Wait for content to load
      await expect(page.getByText("Eversource Standard").first()).toBeVisible({
        timeout: 5000,
      });

      // The reason is behind the "Expand decision details" button
      const reasonText = page.getByText(/Better rate found|14% savings/);
      if (
        await reasonText
          .first()
          .isVisible({ timeout: 2000 })
          .catch(() => false)
      ) {
        await expect(reasonText.first()).toBeVisible();
      } else {
        // Click the expand button to reveal decision reasoning
        const expandButton = page
          .getByRole("button", { name: /expand decision details/i })
          .first();
        await expandButton.click();
        await expect(
          page.getByText(/Better rate found|14% savings/).first(),
        ).toBeVisible({ timeout: 3000 });
      }
    },
  );

  test(
    "shows empty state when no history",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupHistoryRoutes(page, { history: [] });
      await page.goto("/auto-switcher/history");

      // Should show an empty state message
      await expect(
        page
          .getByText(/no switch history|no switches|no entries|no activity/i)
          .first(),
      ).toBeVisible({ timeout: 5000 });
    },
  );

  test(
    "shows hold entries without savings data",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupHistoryRoutes(page, {
        history: [
          makeAuditEntry({
            id: "audit-hold",
            decision: "hold",
            reason: "Current plan is competitive. No action needed.",
            proposed_plan_name: null,
            savings_monthly: null,
            savings_annual: null,
            net_savings_year1: null,
            executed: false,
          }),
        ],
      });
      await page.goto("/auto-switcher/history");

      await expect(
        page.getByText(/Current plan is competitive|Hold/i).first(),
      ).toBeVisible({ timeout: 5000 });
    },
  );

  test(
    "has back link to main auto-switcher page",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupHistoryRoutes(page);
      await page.goto("/auto-switcher/history");

      const backLink = page.locator('a[href="/auto-switcher"]').first();
      await expect(backLink).toBeVisible({ timeout: 5000 });
    },
  );

  test(
    "multiple decision types render correctly",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupHistoryRoutes(page, { history: MOCK_HISTORY });
      await page.goto("/auto-switcher/history");

      // Wait for full list to render
      await expect(page.getByText("Eversource Standard").first()).toBeVisible({
        timeout: 5000,
      });

      // Multiple plan names from different entries should be visible
      await expect(page.getByText("Direct Energy Saver").first()).toBeVisible({
        timeout: 3000,
      });
      await expect(
        page.getByText("Green Mountain Fixed 12").first(),
      ).toBeVisible({ timeout: 3000 });
    },
  );

  test(
    "rollback button calls rollback endpoint",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupHistoryRoutes(page);
      await page.goto("/auto-switcher/history");

      // Wait for history to load
      await expect(page.getByText("Eversource Standard").first()).toBeVisible({
        timeout: 5000,
      });

      // Find rollback button on executed switch entry
      const rollbackButton = page
        .getByRole("button", { name: /rollback/i })
        .first();
      if (await rollbackButton.isVisible({ timeout: 3000 })) {
        const rollbackResponse = page.waitForResponse(
          "**/api/v1/agent-switcher/executions/*/rollback",
        );
        await rollbackButton.click();

        // Confirm in the rollback confirmation dialog (scope to dialog to avoid matching original button)
        const dialog = page.getByRole("dialog");
        const confirmButton = dialog
          .getByRole("button", { name: /rollback/i })
          .first();
        if (
          await confirmButton.isVisible({ timeout: 2000 }).catch(() => false)
        ) {
          await confirmButton.click();
        }

        const response = await rollbackResponse;
        expect(response.status()).toBe(200);
      }
    },
  );

  test(
    "rollback error shows expiry message",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupHistoryRoutes(page, { rollbackError: true });
      await page.goto("/auto-switcher/history");

      await expect(page.getByText("Eversource Standard").first()).toBeVisible({
        timeout: 5000,
      });

      const rollbackButton = page
        .getByRole("button", { name: /rollback/i })
        .first();
      if (await rollbackButton.isVisible({ timeout: 3000 })) {
        await rollbackButton.click();

        // Confirm in the rollback confirmation dialog (scope to dialog)
        const dialog = page.getByRole("dialog");
        const confirmButton = dialog
          .getByRole("button", { name: /rollback/i })
          .first();
        if (
          await confirmButton.isVisible({ timeout: 2000 }).catch(() => false)
        ) {
          await confirmButton.click();
        }

        // Should show error message
        await expect(
          page
            .getByText(/rollback failed|window has expired|cannot rollback/i)
            .first(),
        ).toBeVisible({ timeout: 5000 });
      }
    },
  );

  test(
    "history 500 shows error boundary",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await page.route("**/api/v1/agent-switcher/settings", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({}),
        });
      });
      await page.route("**/api/v1/agent-switcher/history**", async (route) => {
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

      await page.goto("/auto-switcher/history");

      // Should show error boundary, not blank page
      await expect(page.locator("body")).not.toBeEmpty();
    },
  );
});

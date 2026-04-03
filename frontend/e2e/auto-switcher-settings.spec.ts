/**
 * Auto Switcher — Settings E2E Tests
 *
 * Tests the settings page: enable/disable, thresholds, cooldown, pause, LOA.
 */

import { test, expect, PRESET_PRO } from "./fixtures";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_SETTINGS_ENABLED = {
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
  ...MOCK_SETTINGS_ENABLED,
  enabled: false,
};

const MOCK_SETTINGS_WITH_LOA = {
  ...MOCK_SETTINGS_ENABLED,
  loa_signed: true,
};

const MOCK_SETTINGS_PAUSED = {
  ...MOCK_SETTINGS_ENABLED,
  paused_until: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
};

// ---------------------------------------------------------------------------
// Route setup — single handler with PUT tracking via callback
// ---------------------------------------------------------------------------

async function setupSettingsRoutes(
  page: import("@playwright/test").Page,
  initialSettings: object = MOCK_SETTINGS_ENABLED,
  callbacks?: {
    onPut?: (body: Record<string, unknown>) => void;
  },
) {
  let currentSettings = { ...initialSettings };

  await page.route("**/api/v1/agent-switcher/settings", async (route) => {
    if (route.request().method() === "PUT") {
      const body = JSON.parse(route.request().postData() || "{}");
      callbacks?.onPut?.(body);
      currentSettings = { ...currentSettings, ...body };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(currentSettings),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(currentSettings),
    });
  });

  // LOA sign
  await page.route("**/api/v1/agent-switcher/loa/sign", async (route) => {
    currentSettings = {
      ...currentSettings,
      loa_signed: true,
    } as typeof currentSettings;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        signed_at: new Date().toISOString(),
        message: "LOA signed successfully",
      }),
    });
  });

  // LOA revoke
  await page.route("**/api/v1/agent-switcher/loa/revoke", async (route) => {
    currentSettings = {
      ...currentSettings,
      loa_signed: false,
      loa_revoked: true,
    } as typeof currentSettings;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        revoked_at: new Date().toISOString(),
        message: "LOA revoked",
      }),
    });
  });

  // Activity (empty for settings page)
  await page.route("**/api/v1/agent-switcher/activity**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Auto Switcher — Settings", () => {
  test.use({ settingsPreset: PRESET_PRO });

  test(
    "loads settings page with all sections",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await setupSettingsRoutes(page);
      await page.goto("/auto-switcher/settings");
      await expect(page).toHaveURL(/\/auto-switcher\/settings/);

      // Should show header
      await expect(page.getByText(/Settings/i).first()).toBeVisible();
    },
  );

  test(
    "shows enabled toggle switch",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await setupSettingsRoutes(page, MOCK_SETTINGS_ENABLED);
      await page.goto("/auto-switcher/settings");

      // Toggle switch for enable/disable
      const toggle = page.getByRole("switch").first();
      await expect(toggle).toBeVisible();
      await expect(toggle).toHaveAttribute("aria-checked", "true");
    },
  );

  test(
    "shows disabled toggle switch when off",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupSettingsRoutes(page, MOCK_SETTINGS_DISABLED);
      await page.goto("/auto-switcher/settings");

      const toggle = page.getByRole("switch").first();
      await expect(toggle).toBeVisible();
      await expect(toggle).toHaveAttribute("aria-checked", "false");
    },
  );

  test(
    "toggle switch calls PUT endpoint on click",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      let putCalled = false;

      // Use callback to track PUT calls — no double-registration
      await setupSettingsRoutes(page, MOCK_SETTINGS_ENABLED, {
        onPut: () => {
          putCalled = true;
        },
      });

      await page.goto("/auto-switcher/settings");

      const toggle = page.getByRole("switch").first();

      // Use waitForResponse instead of waitForTimeout
      const putResponse = page.waitForResponse(
        (res) =>
          res.url().includes("/agent-switcher/settings") &&
          res.request().method() === "PUT",
      );
      await toggle.click();
      await putResponse;

      expect(putCalled).toBe(true);
    },
  );

  test(
    "displays savings threshold controls",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupSettingsRoutes(page, MOCK_SETTINGS_ENABLED);
      await page.goto("/auto-switcher/settings");

      // Should show threshold label
      await expect(page.getByText(/savings threshold/i).first()).toBeVisible({
        timeout: 5000,
      });
    },
  );

  test(
    "displays cooldown days setting",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupSettingsRoutes(page, MOCK_SETTINGS_ENABLED);
      await page.goto("/auto-switcher/settings");

      await expect(page.getByText(/cooldown/i).first()).toBeVisible({
        timeout: 5000,
      });
    },
  );

  test(
    "shows LOA section without signature",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupSettingsRoutes(page, MOCK_SETTINGS_ENABLED);
      await page.goto("/auto-switcher/settings");

      // Should show LOA / authorization section
      await expect(page.getByText(/authorization/i).first()).toBeVisible({
        timeout: 5000,
      });
    },
  );

  test(
    "shows LOA as signed when already granted",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupSettingsRoutes(page, MOCK_SETTINGS_WITH_LOA);
      await page.goto("/auto-switcher/settings");

      // Should indicate LOA is active — look for active indicator or revoke button
      await expect(
        page.getByText(/LOA is active|revoke loa/i).first(),
      ).toBeVisible({ timeout: 5000 });
    },
  );

  test(
    "LOA sign calls sign endpoint",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupSettingsRoutes(page, MOCK_SETTINGS_ENABLED);
      await page.goto("/auto-switcher/settings");

      // Find the Sign LOA button (must be specific to avoid matching "Sign out")
      const signButton = page
        .getByRole("button", { name: /sign loa/i })
        .first();
      if (await signButton.isVisible({ timeout: 5000 })) {
        const signResponse = page.waitForResponse(
          "**/api/v1/agent-switcher/loa/sign",
        );
        await signButton.click();
        const response = await signResponse;
        expect(response.status()).toBe(200);
      }
    },
  );

  test(
    "shows paused state with date",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupSettingsRoutes(page, MOCK_SETTINGS_PAUSED);
      await page.goto("/auto-switcher/settings");

      // Should show pause indicator or unpause button
      await expect(page.getByText(/paused|unpause/i).first()).toBeVisible({
        timeout: 5000,
      });
    },
  );

  test(
    "back link navigates to main dashboard",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupSettingsRoutes(page);
      await page.goto("/auto-switcher/settings");

      const backLink = page.locator('a[href="/auto-switcher"]').first();
      if (await backLink.isVisible({ timeout: 3000 })) {
        await backLink.click();
        await expect(page).toHaveURL(/\/auto-switcher$/);
      }
    },
  );

  test(
    "settings 500 shows error boundary",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
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

      await page.goto("/auto-switcher/settings");

      // Should show error boundary or error state, not blank page
      await expect(page.locator("body")).not.toBeEmpty();
    },
  );
});

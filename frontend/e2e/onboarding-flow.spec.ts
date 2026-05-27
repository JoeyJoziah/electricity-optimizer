import { test, expect } from "./fixtures";

/**
 * Onboarding Wizard E2E Tests
 *
 * Tests the multi-step onboarding flow: state -> utility types -> supplier -> dashboard.
 *
 * All tests here represent a new user (region: null, onboarding_completed: false).
 * The profile mock is registered inline per test since it requires per-method
 * handling (GET returns the new-user profile; PUT echoes back the submitted body).
 * The shared factory's userProfile mock is disabled via apiMockConfig to avoid
 * conflicts with the onboarding-specific version.
 */

test.describe("Onboarding Wizard Flow", () => {
  // Disable the shared factory's userProfile mock so the inline onboarding
  // profile mock (which handles both GET and PUT) is not shadowed.
  test.use({
    apiMockConfig: {
      userProfile: false,
    },
    // New user has no settings yet — use the empty preset
    settingsPreset: {},
  });

  /** Register the new-user profile mock (GET + PUT) and other onboarding-relevant routes. */
  async function setupOnboardingMocks(page: import("@playwright/test").Page) {
    // Profile: GET = new user; PUT = echo body back as updated profile
    await page.route("**/api/v1/users/profile", async (route, request) => {
      if (request.method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            email: "test@example.com",
            name: "Test User",
            region: null,
            utility_types: null,
            current_supplier_id: null,
            annual_usage_kwh: null,
            onboarding_completed: false,
          }),
        });
      } else {
        // PUT — return updated profile
        const body = request.postDataJSON();
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            email: "test@example.com",
            name: "Test User",
            region: body.region || null,
            utility_types: body.utility_types || null,
            current_supplier_id: body.current_supplier_id || null,
            annual_usage_kwh: body.annual_usage_kwh || null,
            onboarding_completed: body.onboarding_completed || false,
          }),
        });
      }
    });

    // Suppliers: TXU and Green Mountain for Texas deregulated flow
    await page.route("**/api/v1/suppliers**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          suppliers: [
            {
              id: "sup_1",
              name: "TXU Energy",
              avgPricePerKwh: 0.12,
              greenEnergy: false,
              rating: 4.2,
              estimatedAnnualCost: 1200,
              tariffType: "variable",
            },
            {
              id: "sup_2",
              name: "Green Mountain Energy",
              avgPricePerKwh: 0.14,
              greenEnergy: true,
              rating: 4.5,
              estimatedAnnualCost: 1400,
              tariffType: "fixed",
            },
          ],
          total: 2,
        }),
      });
    });
  }

  // NOTE: onboarding was simplified to a SINGLE region-selection step
  // (OnboardingWizard auto-sets electricity and goes straight to the
  // dashboard). The former utility-types and supplier steps were removed —
  // additional utilities are now discovered post-signup on the dashboard.
  test(
    "shows the onboarding wizard with state selection",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      await expect(page.getByText("Select your state")).toBeVisible();
      await expect(page.getByPlaceholder("Search states...")).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Continue to Dashboard" }),
      ).toBeVisible();
    },
  );

  test(
    "regulated state selection completes onboarding and lands on dashboard",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      // Select Florida (regulated state), then complete straight to the dashboard.
      await page.fill('[placeholder="Search states..."]', "Florida");
      await page.click("text=Florida");
      await page.getByRole("button", { name: "Continue to Dashboard" }).click();

      await page.waitForURL(/\/dashboard/, { timeout: 10000 });
    },
  );

  test(
    "deregulated state selection completes onboarding and lands on dashboard",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      // Select Texas (deregulated state). The simplified wizard still goes
      // straight to the dashboard — supplier choice happens later in-app.
      await page.fill('[placeholder="Search states..."]', "Texas");
      await page.click("text=Texas");
      await page.getByRole("button", { name: "Continue to Dashboard" }).click();

      await page.waitForURL(/\/dashboard/, { timeout: 10000 });
    },
  );

  test(
    "Continue is disabled until a state is selected",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      const continueBtn = page.getByRole("button", {
        name: "Continue to Dashboard",
      });
      await expect(continueBtn).toBeDisabled();

      await page.fill('[placeholder="Search states..."]', "Connecticut");
      await page.click("text=Connecticut");
      await expect(continueBtn).toBeEnabled();
    },
  );

  test(
    "search filters the state list and shows an empty state",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      await page.fill('[placeholder="Search states..."]', "Texas");
      await expect(
        page.getByText("Texas", { exact: false }).first(),
      ).toBeVisible();

      await page.fill('[placeholder="Search states..."]', "zzzznotastate");
      await expect(page.getByText(/No states match/)).toBeVisible();
    },
  );
});

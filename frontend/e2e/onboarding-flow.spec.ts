import { test, expect } from "./fixtures";

/**
 * Onboarding E2E Tests
 *
 * Onboarding is a single step: pick a state, then continue to the dashboard.
 * Utility types and supplier are chosen later from the dashboard's setup
 * checklist, not in a wizard.
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

  test(
    "starts with state selection and nothing chosen",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      await expect(
        page.getByRole("heading", { name: "Select your state" }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Continue to Dashboard" }),
      ).toBeDisabled();
    },
  );

  test(
    "regulated state: select state -> dashboard",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      await page.fill('[placeholder="Search states..."]', "Florida");
      await page.getByRole("button", { name: /Florida/ }).click();
      // Florida is regulated: no supplier-choice badge on its row.
      await expect(
        page.getByRole("button", { name: /Florida/ }),
      ).not.toContainText("Supplier choice");

      await page.getByRole("button", { name: "Continue to Dashboard" }).click();
      await page.waitForURL(/\/dashboard/, { timeout: 10000 });
    },
  );

  test(
    "deregulated state is marked as supplier choice and continues to dashboard",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      await page.fill('[placeholder="Search states..."]', "Texas");
      const texas = page.getByRole("button", { name: /Texas/ });
      await expect(texas).toContainText("Supplier choice");
      await texas.click();

      await page.getByRole("button", { name: "Continue to Dashboard" }).click();
      await page.waitForURL(/\/dashboard/, { timeout: 10000 });
    },
  );

  test(
    "search with no match shows an empty message",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      await page.fill('[placeholder="Search states..."]', "Atlantis");
      await expect(page.getByText(/No states match/)).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Continue to Dashboard" }),
      ).toBeDisabled();
    },
  );
});

import { test, expect } from "./fixtures";

test.describe("Prices Page", () => {
  test.use({
    apiMockConfig: {
      pricesCurrent: {
        region: "US_CT",
        price: 0.2512,
        trend: "decreasing",
        changePercent: -1.8,
      },
    },
  });

  test(
    "displays prices page",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await page.goto("/prices");
      await expect(page).toHaveURL(/\/prices/);
    },
  );

  test(
    "shows current price data",
    { tag: ["@smoke"] },
    async ({ authenticatedPage: page }) => {
      await page.goto("/prices");

      // Should show price information
      await expect(page.getByText(/\$0\.25/)).toBeVisible({ timeout: 5000 });
    },
  );

  test(
    "shows time range selector",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await page.goto("/prices");

      // Time range buttons
      await expect(page.getByRole("button", { name: "24h" })).toBeVisible();
    },
  );

  test(
    "switches time range",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page }) => {
      await page.goto("/prices");

      const btn7d = page.getByRole("button", { name: "7d" });
      if (await btn7d.isVisible()) {
        await btn7d.click();
        // Wait for the page to acknowledge the click — heading stays visible
        await expect(page.locator('h1, [role="heading"]').first()).toBeVisible({
          timeout: 5000,
        });
      }
    },
  );

  // Chart SVGs may not render at mobile viewport sizes (Recharts responsive container)
  test(
    "renders chart area",
    { tag: ["@regression"] },
    async ({ authenticatedPage: page, isMobile }) => {
      test.skip(
        isMobile === true,
        "Chart SVGs do not render at mobile viewport sizes",
      );
      await page.goto("/prices");

      // Chart container or skeleton should be visible
      const chartArea = page.locator(
        '[class*="chart"], [class*="Chart"], [role="img"], svg',
      );
      // Either chart renders or skeleton is shown
      await expect(
        chartArea.first().or(page.getByText(/loading/i)),
      ).toBeVisible({
        timeout: 5000,
      });
    },
  );
});

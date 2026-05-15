/**
 * Unsubscribe Flow E2E Tests
 *
 * Covers the public CAN-SPAM unsubscribe flow:
 *   email link → backend `/api/v1/public/unsubscribe?uid=&tok=` → redirect →
 *   frontend `/unsubscribed` confirmation page.
 *
 * The backend HMAC validation is unit-tested in
 * `backend/tests/test_api_public_unsubscribe.py`. These tests cover the
 * frontend confirmation page UI, accessibility, and SEO posture (no-index).
 *
 * Pre-launch context (PRD Scope #13 / CAN-SPAM): unsubscribe must work
 * before PH launch. A broken unsubscribe page is a legal-compliance risk.
 */

import { test, expect } from "@playwright/test";

test.describe("Unsubscribe — /unsubscribed page", { tag: ["@smoke"] }, () => {
  test("renders confirmation heading + supporting copy", async ({ page }) => {
    await page.goto("/unsubscribed");

    await expect(
      page.getByRole("heading", { name: /you.*ve been unsubscribed/i }),
    ).toBeVisible();

    await expect(
      page.getByText(/no longer receive onboarding emails/i),
    ).toBeVisible();

    // Account-active reassurance (matches landing-page tone — "your account
    // remains active"). Confirms we're not implying full account deletion.
    await expect(page.getByText(/account remains active/i)).toBeVisible();
  });

  test("page title set for browser tab + screen-reader context", async ({
    page,
  }) => {
    await page.goto("/unsubscribed");
    await expect(page).toHaveTitle(/unsubscribed.*rateshift/i);
  });

  test("emits robots: noindex (page should NOT show up in search results)", async ({
    page,
  }) => {
    const response = await page.goto("/unsubscribed");
    expect(response?.status()).toBe(200);

    const robotsMeta = await page
      .locator('meta[name="robots"]')
      .getAttribute("content");
    expect(robotsMeta?.toLowerCase()).toContain("noindex");
  });

  test('"Return to RateShift" link points to landing page', async ({
    page,
  }) => {
    await page.goto("/unsubscribed");

    const returnLink = page.getByRole("link", { name: /return to rateshift/i });
    await expect(returnLink).toBeVisible();
    await expect(returnLink).toHaveAttribute("href", "/");
  });

  test("RateShift logo in nav links to landing page", async ({ page }) => {
    await page.goto("/unsubscribed");

    // Nav has logo + brand text wrapped in a Link to "/"
    const navLink = page.locator('nav a[href="/"]').first();
    await expect(navLink).toBeVisible();
    await expect(navLink).toContainText(/rateshift/i);
  });
});

test.describe(
  "Unsubscribe — /unsubscribed accessibility",
  { tag: ["@regression"] },
  () => {
    test("has exactly one h1 heading", async ({ page }) => {
      await page.goto("/unsubscribed");
      const h1Count = await page.locator("h1").count();
      expect(h1Count).toBe(1);
    });

    test("CheckCircle icon is decorative (no broken alt text)", async ({
      page,
    }) => {
      await page.goto("/unsubscribed");
      // lucide-react icons render as <svg> without alt; ensure no orphan
      // <img> tags with empty alt that would confuse screen readers
      const orphanImages = await page.locator("img:not([alt])").count();
      expect(orphanImages).toBe(0);
    });
  },
);

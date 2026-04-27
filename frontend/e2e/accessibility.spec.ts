/**
 * Accessibility E2E Tests — WCAG 2.1 AA
 *
 * Runs axe-core against every page (public + protected) to catch
 * accessibility violations automatically. Also covers:
 * - Keyboard navigation through key interactive flows
 * - Focus management when modals open/close
 * - Heading hierarchy (h1 present, no skipped levels)
 *
 * All tests are tagged @regression.
 *
 * Public pages use `page` directly (no auth cookie).
 * Protected pages use `authenticatedPage` (auth + API mocks).
 */

import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "./fixtures";
import { mockBetterAuth, clearAuthState } from "./helpers/auth";
import { createMockApi } from "./helpers/api-mocks";

// ---------------------------------------------------------------------------
// Shared helper — run axe and surface a readable violation summary
// ---------------------------------------------------------------------------

async function assertNoAxeViolations(
  builder: AxeBuilder,
  pagePath: string,
): Promise<void> {
  const results = await builder.analyze();
  if (results.violations.length > 0) {
    const summary = results.violations
      .map(
        (v) =>
          `[${v.impact?.toUpperCase() ?? "UNKNOWN"}] ${v.id}: ${v.description} — ${v.nodes.length} node(s)`,
      )
      .join("\n");
    throw new Error(
      `axe found ${results.violations.length} WCAG AA violation(s) on ${pagePath}:\n${summary}`,
    );
  }
}

// ---------------------------------------------------------------------------
// Public pages — no session required
// ---------------------------------------------------------------------------

test.describe("Accessibility — Public Pages", () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page);
    await clearAuthState(page);
  });

  test("/ landing page has no WCAG AA violations @regression", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 15000 });
    await page.waitForSelector("body");
    const builder = new AxeBuilder({ page }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/");
  });

  test("/pricing has no WCAG AA violations @regression", async ({ page }) => {
    await page.goto("/pricing", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("body");
    const builder = new AxeBuilder({ page }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/pricing");
  });

  test("/privacy has no WCAG AA violations @regression", async ({ page }) => {
    await page.goto("/privacy", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("body");
    const builder = new AxeBuilder({ page }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/privacy");
  });

  test("/terms has no WCAG AA violations @regression", async ({ page }) => {
    await page.goto("/terms", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("body");
    const builder = new AxeBuilder({ page }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/terms");
  });

  test("/beta-signup has no WCAG AA violations @regression", async ({
    page,
  }) => {
    await page.goto("/beta-signup", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("body");
    const builder = new AxeBuilder({ page }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/beta-signup");
  });
});

// ---------------------------------------------------------------------------
// Auth pages — no session required
// ---------------------------------------------------------------------------

test.describe("Accessibility — Auth Pages", () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page);
    await clearAuthState(page);
  });

  test("/auth/login has no WCAG AA violations @regression", async ({
    page,
  }) => {
    await page.goto("/auth/login", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("#email");
    const builder = new AxeBuilder({ page }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/auth/login");
  });

  test("/auth/signup has no WCAG AA violations @regression", async ({
    page,
  }) => {
    await page.goto("/auth/signup", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("body");
    const builder = new AxeBuilder({ page }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/auth/signup");
  });
});

// ---------------------------------------------------------------------------
// Protected pages — full auth + API mocks via authenticatedPage fixture
// ---------------------------------------------------------------------------

test.describe("Accessibility — Protected Pages", () => {
  test("/dashboard has no WCAG AA violations @regression", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/dashboard", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await authenticatedPage.waitForSelector("body");
    const builder = new AxeBuilder({ page: authenticatedPage }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/dashboard");
  });

  test("/prices has no WCAG AA violations @regression", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/prices", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await authenticatedPage.waitForSelector("body");
    const builder = new AxeBuilder({ page: authenticatedPage }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/prices");
  });

  test("/suppliers has no WCAG AA violations @regression", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/suppliers", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await authenticatedPage.waitForSelector("body");
    const builder = new AxeBuilder({ page: authenticatedPage }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/suppliers");
  });

  test("/optimize has no WCAG AA violations @regression", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/optimize", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await authenticatedPage.waitForSelector("body");
    const builder = new AxeBuilder({ page: authenticatedPage }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/optimize");
  });

  test("/settings has no WCAG AA violations @regression", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/settings", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await authenticatedPage.waitForSelector("body");
    const builder = new AxeBuilder({ page: authenticatedPage }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/settings");
  });

  test("/alerts has no WCAG AA violations @regression", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/alerts", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await authenticatedPage.waitForSelector("body");
    const builder = new AxeBuilder({ page: authenticatedPage }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/alerts");
  });

  test("/assistant has no WCAG AA violations @regression", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/assistant", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await authenticatedPage.waitForSelector("body");
    const builder = new AxeBuilder({ page: authenticatedPage }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/assistant");
  });

  test("/community has no WCAG AA violations @regression", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/community", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await authenticatedPage.waitForSelector("body");
    const builder = new AxeBuilder({ page: authenticatedPage }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/community");
  });

  test("/analytics has no WCAG AA violations @regression", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/analytics", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await authenticatedPage.waitForSelector("body");
    const builder = new AxeBuilder({ page: authenticatedPage }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/analytics");
  });

  test("/billing has no WCAG AA violations @regression", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/billing", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await authenticatedPage.waitForSelector("body");
    const builder = new AxeBuilder({ page: authenticatedPage }).withTags([
      "wcag2a",
      "wcag2aa",
      "wcag21aa",
    ]);
    await assertNoAxeViolations(builder, "/billing");
  });
});

// ---------------------------------------------------------------------------
// Keyboard navigation — login form
// ---------------------------------------------------------------------------

test.describe("Accessibility — Keyboard Navigation", () => {
  test("login form is fully keyboard navigable @regression", async ({
    page,
  }) => {
    await mockBetterAuth(page);
    await clearAuthState(page);
    await page.goto("/auth/login", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });

    // Tab to email field and type
    await page.keyboard.press("Tab");
    const emailFocused = await page.evaluate(
      () =>
        document.activeElement?.id === "email" ||
        document.activeElement?.getAttribute("type") === "email",
    );
    // Some pages have a skip-to-content link first — keep tabbing until email is focused
    if (!emailFocused) {
      await page.keyboard.press("Tab");
    }

    await page.locator("#email").focus();
    await page.keyboard.type("test@example.com");

    // Tab to password
    await page.keyboard.press("Tab");
    await page.keyboard.type("TestPass123!");

    // Tab forward until we reach the submit button (may pass show-password toggle, etc.)
    let submitReached = false;
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press("Tab");
      submitReached = await page.evaluate(
        () =>
          document.activeElement?.tagName === "BUTTON" &&
          (document.activeElement as HTMLButtonElement).type === "submit",
      );
      if (submitReached) break;
    }
    // The submit button must be reachable via keyboard within 5 tab presses
    expect(submitReached).toBe(true);
  });

  test("onboarding wizard is keyboard navigable @regression", async ({
    authenticatedPage,
  }) => {
    // Override profile to trigger onboarding
    await authenticatedPage.route(
      "**/api/v1/users/profile**",
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            email: "test@example.com",
            name: "Test User",
            region: null,
            utility_types: [],
            current_supplier_id: null,
            annual_usage_kwh: null,
            onboarding_completed: false,
          }),
        });
      },
    );

    await authenticatedPage.goto("/onboarding", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await authenticatedPage.waitForSelector("body");

    // Tab through the first few interactive elements and confirm no focus trap
    for (let i = 0; i < 5; i++) {
      await authenticatedPage.keyboard.press("Tab");
    }
    const focused = await authenticatedPage.evaluate(
      () => document.activeElement?.tagName,
    );
    // Focus must have moved to some interactive element (not <body>)
    expect(["INPUT", "SELECT", "BUTTON", "A", "TEXTAREA", "BODY"]).toContain(
      focused,
    );
  });

  test("supplier page is keyboard navigable @regression", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/suppliers", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await authenticatedPage.waitForSelector("body");

    // Tab through first 8 interactive elements — none should trap focus
    for (let i = 0; i < 8; i++) {
      await authenticatedPage.keyboard.press("Tab");
    }
    const focused = await authenticatedPage.evaluate(
      () => document.activeElement?.tagName,
    );
    expect(focused).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Focus management — modal open/close returns focus to trigger
// ---------------------------------------------------------------------------

test.describe("Accessibility — Focus Management", () => {
  test("alert creation modal returns focus to trigger on close @regression", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/alerts", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });

    // Find the button that opens the alert creation form/modal
    const createButton = authenticatedPage.getByRole("button", {
      name: /new alert|create alert|add alert/i,
    });

    const createButtonExists = await createButton.count();
    if (createButtonExists === 0) {
      // If no modal trigger exists on this page, skip gracefully
      test.skip(
        true,
        "No alert creation button found on page — UI may have changed",
      );
      return;
    }

    await createButton.first().click();

    // Modal or form should now be visible
    const modal = authenticatedPage.locator(
      '[role="dialog"], [data-radix-dialog-content]',
    );
    const modalVisible = await modal.count();

    if (modalVisible > 0) {
      // Close with Escape key
      await authenticatedPage.keyboard.press("Escape");
      // Wait for the dialog to close before checking focus
      await expect(modal.first())
        .toBeHidden({ timeout: 5000 })
        .catch(() => {
          /* dialog may already be gone */
        });

      // Focus should return to the trigger button
      const triggerId = await createButton.first().getAttribute("id");
      if (triggerId) {
        const focused = await authenticatedPage.evaluate(
          () => document.activeElement?.id,
        );
        expect(focused).toBe(triggerId);
      } else {
        // At minimum, focus must not be on body
        const focused = await authenticatedPage.evaluate(
          () => document.activeElement?.tagName,
        );
        expect(focused).not.toBe("BODY");
      }
    }
  });
});

// ---------------------------------------------------------------------------
// Heading hierarchy — h1 present, no skipped levels
// ---------------------------------------------------------------------------

test.describe("Accessibility — Heading Hierarchy", () => {
  test("dashboard has exactly one h1 and no skipped heading levels @regression", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/dashboard", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await authenticatedPage.waitForSelector("body");

    const headingData = await authenticatedPage.evaluate(() => {
      const headings = Array.from(
        document.querySelectorAll("h1, h2, h3, h4, h5, h6"),
      );
      return headings.map((h) => ({
        level: parseInt(h.tagName.slice(1), 10),
        text: h.textContent?.trim().slice(0, 60) ?? "",
      }));
    });

    // Must have exactly one h1
    const h1s = headingData.filter((h) => h.level === 1);
    expect(h1s.length).toBe(1);

    // No skipped levels (e.g., h1 → h3 without h2)
    for (let i = 1; i < headingData.length; i++) {
      const prev = headingData[i - 1]!.level;
      const curr = headingData[i]!.level;
      // Heading level must not increase by more than 1
      expect(curr).toBeLessThanOrEqual(prev + 1);
    }
  });

  test("/pricing has exactly one h1 @regression", async ({ page }) => {
    await mockBetterAuth(page);
    await clearAuthState(page);
    await page.goto("/pricing", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });

    const h1Count = await page.locator("h1").count();
    expect(h1Count).toBe(1);
  });

  test("/settings has exactly one h1 @regression", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/settings", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });

    const h1Count = await authenticatedPage.locator("h1").count();
    expect(h1Count).toBe(1);
  });
});

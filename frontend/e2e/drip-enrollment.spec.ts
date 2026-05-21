/**
 * Drip Enrollment Flow E2E Tests
 *
 * The drip enrollment is a server-to-server fire-and-forget call from the
 * Better Auth `databaseHooks.user.create.after` hook to
 * `POST /api/v1/internal/drip/enroll` (see `lib/auth/drip-enroll.ts`).
 * Per design (drip-enroll.ts:21-28), any failure is swallowed so signup
 * is never blocked.
 *
 * What E2E CAN verify:
 *   - The signup UI flow completes successfully (no user-visible regression)
 *   - Server-side hook failures don't surface to the user
 *   - The drip-enrollment HTTP contract (request shape) — when reachable
 *
 * What's covered ELSEWHERE:
 *   - Backend `DripService` behavior: 18 tests in
 *     `backend/tests/test_drip_service.py`
 *   - Backend `/api/v1/internal/drip/enroll` endpoint: 5 tests in
 *     `backend/tests/test_drip_endpoint.py`
 *   - The `enrollUserInDrip` helper unit test (Jest):
 *     `frontend/lib/auth/__tests__/drip-enroll.test.ts` (if present)
 *
 * Pre-launch context (PRD Scope #5): drip emails are part of the activation
 * funnel. A silent enrollment failure (like the X-Internal-API-Key bug Loki
 * fixed 2026-05-12) means users never get the welcome email — caught only
 * via Sentry post-launch. These tests provide a thin pre-launch tripwire.
 */

import { test, expect } from "@playwright/test";

test.describe(
  "Drip Enrollment — signup resilience",
  { tag: ["@regression"] },
  () => {
    test("signup page loads without errors", async ({ page }) => {
      const response = await page.goto("/auth/signup");
      expect(response?.status()).toBe(200);

      // Form is present (signup name field is the unique-to-signup element)
      await expect(page.locator("#email")).toBeVisible();
      await expect(page.locator("#password")).toBeVisible();
    });

    test("signup form remains functional even when drip endpoint would fail", async ({
      page,
    }) => {
      // The drip enrollment fetches BACKEND_URL from process.env at
      // server-side runtime; we cannot directly mock it from Playwright.
      // What we CAN verify is that the signup PAGE renders + the form
      // doesn't depend on drip enrollment client-side. The actual
      // resilience invariant ("signup never blocks on drip") is enforced
      // by the try/catch in lib/auth/drip-enroll.ts:21-28.
      await page.goto("/auth/signup");

      // No client-side fetch to /internal/drip/* should ever happen
      // (it's a server hook, not a client call). If it does, that's a bug.
      const internalDripCalls: string[] = [];
      page.on("request", (req) => {
        const url = req.url();
        if (url.includes("/internal/drip")) {
          internalDripCalls.push(url);
        }
      });

      // Browse the signup form briefly — no network calls to /internal/drip
      // should fire from the browser.
      await page.locator("#email").click();
      await page.locator("#email").fill("test@example.com");
      await page.waitForTimeout(200);

      expect(
        internalDripCalls,
        "Browser should never call /internal/drip/* directly — it's a server-side hook",
      ).toHaveLength(0);
    });
  },
);

test.describe(
  "Drip Enrollment — public endpoint isolation",
  { tag: ["@regression"] },
  () => {
    test("internal drip endpoint is NOT reachable without API key from browser", async ({
      page: _page,
      request,
    }) => {
      // The /internal/drip/enroll endpoint requires X-API-Key (verified by
      // the parent /internal router). A browser request without the key
      // must NOT succeed (defense-in-depth: even if exposed, it's gated).
      //
      // We hit the proxied path through the frontend (which routes
      // /api/v1/* via Next.js rewrites to the CF Worker → Render origin).
      // Without the internal API key header, the backend should reject.

      const apiBaseUrl = "/api/v1/internal/drip/enroll";

      const response = await request.post(apiBaseUrl, {
        data: {
          user_id: "test-user-id",
          email: "test@example.com",
          name: "Test User",
        },
        // No X-API-Key header on purpose
        failOnStatusCode: false,
      });

      // Expected: 401 Unauthorized, 403 Forbidden, or 404 if not exposed.
      // What we MUST NOT see: 200 (would mean key check is bypassed).
      expect(
        [401, 403, 404, 422],
        `Internal drip endpoint returned ${response.status()} without auth — should be 401/403/404`,
      ).toContain(response.status());
    });
  },
);

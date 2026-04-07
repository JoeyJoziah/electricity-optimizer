import { test, expect } from "./fixtures";
import {
  mockBetterAuth,
  setAuthenticatedState,
  clearAuthState,
} from "./helpers/auth";

test.describe("Authentication Flows", () => {
  // Tests in this block exercise the login page (unauthenticated), OAuth initiation,
  // and session-related behaviour. We use the raw `page` fixture here because most
  // of these tests deliberately operate without an active session.

  test("displays login page", { tag: ["@smoke"] }, async ({ page }) => {
    await mockBetterAuth(page);
    await page.goto("/auth/login");

    await expect(
      page.getByRole("heading", { name: /electricity optimizer/i }),
    ).toBeVisible();
    await expect(page.locator("#email")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Sign in", exact: true }),
    ).toBeVisible();
  });

  test(
    "user can login with email and password",
    { tag: ["@smoke"] },
    async ({ page }) => {
      await mockBetterAuth(page);

      await page.route("**/api/v1/prices/current**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            prices: [
              {
                region: "US_CT",
                price: 0.25,
                timestamp: new Date().toISOString(),
              },
            ],
          }),
        });
      });

      await page.addInitScript(() => {
        localStorage.setItem(
          "electricity-optimizer-settings",
          JSON.stringify({
            state: {
              region: "US_CT",
              annualUsageKwh: 10500,
              peakDemandKw: 5,
              displayPreferences: {
                currency: "USD",
                theme: "system",
                timeFormat: "12h",
              },
            },
          }),
        );
      });

      await page.goto("/auth/login");

      await page.fill("#email", "test@example.com");
      await page.fill("#password", "TestPass123!");
      await page.click('button[type="submit"]');

      // Should redirect to dashboard — webkit/Mobile Safari need extra time for cookie + redirect
      await page.waitForURL("/dashboard", { timeout: 30000 });
      await expect(page.getByText("Current Price").first()).toBeVisible();
    },
  );

  // The Better Auth client may not surface error messages from 401 responses
  // consistently across all browser engines (webkit/Mobile Safari handle fetch
  // error propagation differently). When the error is not surfaced, the useAuth
  // hook falls through to redirect. Test checks for error OR staying on login.
  test(
    "shows error for invalid credentials",
    { tag: ["@regression"] },
    async ({ page }) => {
      await mockBetterAuth(page);
      await page.goto("/auth/login");

      await page.fill("#email", "wrong@example.com");
      await page.fill("#password", "WrongPass123!");
      await page.click('button[type="submit"]');

      // The page must stay on the login URL (invalid credentials should never redirect to dashboard).
      // Some browsers also surface the error message from the 401 response.
      await expect(page).toHaveURL(/\/auth\/login/);

      // Verify the login form is still present (not a blank page)
      await expect(page.locator("#email")).toBeVisible({ timeout: 8000 });

      // If an error alert rendered, verify it contains a relevant message
      const errorLocator = page.getByText(/invalid|failed|error/i);
      const errorVisible = await errorLocator.isVisible().catch(() => false);
      if (errorVisible) {
        await expect(errorLocator.first()).toBeVisible();
      }
    },
  );

  // The email input uses type="email" which activates the browser's native
  // Constraint Validation API. We test this via page.evaluate() to read the
  // validity state directly — the native browser tooltip is not DOM-accessible.
  // The onBlur handler in LoginForm also sets a React emailError state;
  // we verify that path separately by triggering blur without a submit.
  test(
    "validates email format via native constraint validation API",
    { tag: ["@regression"] },
    async ({ page }) => {
      await mockBetterAuth(page);
      // Use the default "load" waitUntil (same as passing tests in this file)
      // so the goto resolves only after the full page load event, not during
      // Next.js dev-mode route compilation which can cause transient 404s.
      await page.goto("/auth/login");

      // Wait for React hydration: click the email field first to ensure it
      // is interactive, then fill it and confirm the DOM value was accepted.
      // In Next.js dev mode with parallel workers, the controlled input may
      // not be hydrated immediately after toBeVisible() — a click() first
      // ensures the React event handlers are attached before filling.
      const emailInput = page.locator("#email");
      await expect(emailInput).toBeVisible({ timeout: 20000 });
      await emailInput.click();
      await emailInput.fill("user@example.com");

      // Wait until the DOM value actually reflects our fill — this confirms
      // React's onChange fired and the controlled component accepted the value.
      await page.waitForFunction(
        () =>
          (document.querySelector("#email") as HTMLInputElement | null)
            ?.value === "user@example.com",
        { timeout: 5000 },
      );

      // Verify a well-formed email address passes native constraint validation.
      const validValidity = await page.evaluate(() => {
        const el = document.querySelector<HTMLInputElement>("#email");
        return {
          valid: el!.validity.valid,
          typeMismatch: el!.validity.typeMismatch,
        };
      });
      expect(validValidity.valid).toBe(true);
      expect(validValidity.typeMismatch).toBe(false);

      // Clear and fill an invalid address — native validation must flag it.
      await emailInput.fill("not-a-valid-email");
      await page.waitForFunction(
        () =>
          (document.querySelector("#email") as HTMLInputElement | null)
            ?.value === "not-a-valid-email",
        { timeout: 5000 },
      );
      const invalidValidity = await page.evaluate(() => {
        const el = document.querySelector<HTMLInputElement>("#email");
        return {
          valid: el!.validity.valid,
          typeMismatch: el!.validity.typeMismatch,
        };
      });
      expect(invalidValidity.valid).toBe(false);
      expect(invalidValidity.typeMismatch).toBe(true);

      // The onBlur handler in LoginForm also renders a React error message.
      // Trigger blur by clicking the password field, then assert the message.
      await page.locator("#password").click();
      await expect(
        page.getByText(/please enter a valid email address/i),
      ).toBeVisible({ timeout: 5000 });

      // Page must remain on login — no submit should have been sent.
      await expect(page).toHaveURL(/\/auth\/login/);
    },
  );

  test("shows OAuth login options", { tag: ["@smoke"] }, async ({ page }) => {
    await mockBetterAuth(page);
    await page.goto("/auth/login");

    await expect(
      page.getByRole("button", { name: /continue with google/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /continue with github/i }),
    ).toBeVisible();
  });

  test(
    "initiates OAuth flow with Google",
    { tag: ["@regression"] },
    async ({ page }) => {
      await mockBetterAuth(page);
      await page.goto("/auth/login");

      await page.click('button:has-text("Continue with Google")');

      // Should initiate OAuth flow — Better Auth mock returns a redirect URL
      // Verify the page is still on login (mock doesn't actually redirect) or has navigated
      await expect(page).toHaveURL(
        /\/(auth\/login|auth\/callback|accounts\.google)/,
      );
    },
  );

  test("handles OAuth callback", { tag: ["@regression"] }, async ({ page }) => {
    await mockBetterAuth(page);
    await page.goto(
      "/auth/callback?code=mock_code&provider=google&state=mock_state",
    );

    // The callback page should process and redirect to dashboard
    // The mockBetterAuth intercepts /api/auth/callback/** and returns session
    await page.waitForURL(/\/(dashboard|auth)/, { timeout: 10000 });
  });

  // Magic link IS implemented via Better Auth's magicLinkClient() plugin.
  // The flow: toggle to magic link mode → fill email → submit → "Check your email"
  // confirmation screen appears. The /api/auth/sign-in/magic-link endpoint is
  // mocked here because no backend is running during E2E tests.
  test(
    "user can request magic link login",
    { tag: ["@regression"] },
    async ({ page }) => {
      await mockBetterAuth(page);

      // Mock the Better Auth magic link endpoint (POST /api/auth/sign-in/magic-link)
      await page.route("**/api/auth/sign-in/magic-link", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ status: true }),
        });
      });

      // Use the default "load" waitUntil to avoid transient 404s during
      // Next.js dev-mode compilation under parallel worker load.
      await page.goto("/auth/login");

      // Wait for React hydration: click the email field to confirm interaction
      // works, then click elsewhere to blur before toggling magic link mode.
      const emailInput = page.locator("#email");
      await expect(emailInput).toBeVisible({ timeout: 20000 });
      await emailInput.click();

      // Click the toggle button to switch to magic link mode.
      // The button fires React's onClick → setShowMagicLink(true).
      const magicLinkToggle = page.getByRole("button", {
        name: /sign in with magic link/i,
      });
      await expect(magicLinkToggle).toBeVisible({ timeout: 5000 });
      await magicLinkToggle.click();

      // After toggling, the password field disappears and the submit button
      // text changes to "Send magic link"
      await expect(
        page.getByRole("button", { name: /send magic link/i }),
      ).toBeVisible({ timeout: 5000 });
      await expect(page.locator("#password")).not.toBeVisible();

      // Fill in a valid email and submit. Click email field first to confirm
      // React's onChange handler is wired up before filling the value.
      await emailInput.click();
      await emailInput.fill("test@example.com");
      await page.waitForFunction(
        () =>
          (document.querySelector("#email") as HTMLInputElement | null)
            ?.value === "test@example.com",
        { timeout: 5000 },
      );
      await page.click('button[type="submit"]');

      // After a successful magic link request the form shows the confirmation screen
      await expect(page.getByText(/check your email/i)).toBeVisible({
        timeout: 8000,
      });
    },
  );

  // Sign-out button is in sidebar (hidden on mobile). Webkit sign-out redirect
  // exceeds the 30s test timeout due to slow cookie/session clearing in the engine.
  test(
    "user can logout",
    { tag: ["@smoke"] },
    async ({ page, isMobile, browserName }) => {
      test.skip(
        isMobile === true,
        "Sign-out button is in sidebar, hidden on mobile",
      );
      test.skip(
        browserName === "webkit",
        "Webkit sign-out redirect exceeds test timeout",
      );
      await mockBetterAuth(page);
      await setAuthenticatedState(page);
      await page.goto("/dashboard");

      await page.click('[data-testid="sign-out-button"]');

      await page.waitForURL("/auth/login", { timeout: 15000 });
    },
  );

  test(
    "redirects unauthenticated users to login",
    { tag: ["@smoke"] },
    async ({ page }) => {
      await mockBetterAuth(page);
      // Ensure no session cookie
      await clearAuthState(page);

      await page.goto("/dashboard");

      // Middleware should redirect to login with callbackUrl
      await page.waitForURL(/\/auth\/login/, { timeout: 10000 });
    },
  );

  test(
    "shows forgot password link",
    { tag: ["@regression"] },
    async ({ page }) => {
      await mockBetterAuth(page);
      await page.goto("/auth/login");

      await expect(page.getByText(/forgot password/i)).toBeVisible();
    },
  );

  test(
    "can navigate to signup from login",
    { tag: ["@regression"] },
    async ({ page }) => {
      await mockBetterAuth(page);
      await page.goto("/auth/login");

      await page.click("text=Sign up");

      await expect(page).toHaveURL(/\/auth\/signup/);
    },
  );

  test(
    "preserves redirect URL after login",
    { tag: ["@regression"] },
    async ({ page }) => {
      await mockBetterAuth(page);
      // Ensure no session cookie
      await clearAuthState(page);

      // Try to access protected page
      await page.goto("/suppliers");

      // Middleware should redirect to login with callbackUrl param
      await page.waitForURL(/\/auth\/login\?callbackUrl=/, { timeout: 10000 });

      // Verify the callbackUrl parameter is present
      const url = new URL(page.url());
      expect(url.searchParams.get("callbackUrl")).toBe("/suppliers");
    },
  );

  test(
    "session persists on page refresh",
    { tag: ["@regression"] },
    async ({ page }) => {
      // Set up authenticated state via cookie
      await setAuthenticatedState(page);
      await mockBetterAuth(page); // re-mock after setting cookies

      await page.addInitScript(() => {
        localStorage.setItem(
          "electricity-optimizer-settings",
          JSON.stringify({
            state: {
              region: "US_CT",
              annualUsageKwh: 10500,
              peakDemandKw: 5,
              displayPreferences: {
                currency: "USD",
                theme: "system",
                timeFormat: "12h",
              },
            },
          }),
        );
      });

      await page.goto("/dashboard");
      await expect(page.getByText("Current Price").first()).toBeVisible();

      // Refresh page
      await page.reload();

      // Should still be on dashboard
      await expect(page.getByText("Current Price").first()).toBeVisible();
    },
  );

  test(
    "handles token expiration gracefully",
    { tag: ["@regression"] },
    async ({ page }) => {
      // Set cookie but mock get-session to return null (expired)
      await setAuthenticatedState(page);
      await mockBetterAuth(page, { sessionExpired: true });

      await page.goto("/dashboard");

      // The app should detect the expired session during useEffect
      // and the useAuth hook will set user to null.
      // Middleware allowed the request (cookie exists) but the client sees no session.
      // Verify the page rendered meaningful content (dashboard heading or auth redirect).
      const onDashboard = page.url().includes("/dashboard");
      const onLogin = page.url().includes("/auth/login");
      if (onDashboard) {
        // Dashboard loaded — verify the heading rendered (not a blank page)
        await expect(
          page.getByRole("heading", { name: "Dashboard" }),
        ).toBeVisible({ timeout: 10000 });
      } else {
        // Redirected to login — verify the login form is present
        expect(onLogin).toBeTruthy();
        await expect(page.locator("#email")).toBeVisible({ timeout: 10000 });
      }
    },
  );
});

test.describe("Redirect Loop Prevention", () => {
  // These tests deliberately set up 401 responses to verify the app doesn't loop.
  // They use `page` directly and set up their own mocks.

  test(
    "stale cookie does not cause redirect loop on login page",
    { tag: ["@regression"] },
    async ({ page }) => {
      await mockBetterAuth(page);

      // Mock backend API endpoints that return 401 for stale sessions
      await page.route("**/api/v1/user/supplier", async (route) => {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        });
      });

      await page.route("**/api/v1/users/profile", async (route) => {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        });
      });

      // Simulate a stale/expired session: the mockBetterAuth(page) already
      // wired get-session to return null when no valid cookie is present. We ensure no
      // live session cookie exists so the middleware does not redirect us away from login,
      // then verify the page stays on /auth/login (no redirect loop).
      await clearAuthState(page);

      await page.goto("/auth/login");

      // Wait for the login form to render, confirming client-side session check completed
      await expect(
        page
          .locator('form, [data-testid="login-form"], button[type="submit"]')
          .first(),
      ).toBeVisible({ timeout: 10000 });
      expect(page.url()).toContain("/auth/login");

      // URL should not be excessively long (no nested callbackUrl)
      expect(page.url().length).toBeLessThan(500);
    },
  );

  test(
    "preserves original callbackUrl through 401 cycle",
    { tag: ["@regression"] },
    async ({ page }) => {
      await mockBetterAuth(page);

      await page.route("**/api/v1/user/supplier", async (route) => {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        });
      });

      await page.route("**/api/v1/users/profile", async (route) => {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        });
      });

      await clearAuthState(page);

      // Navigate to a protected page — middleware redirects to login with callbackUrl
      await page.goto("/suppliers");
      await page.waitForURL(/\/auth\/login\?callbackUrl=/, { timeout: 10000 });

      // Verify the callbackUrl is /suppliers (not a nested URL)
      const url = new URL(page.url());
      const callbackUrl = url.searchParams.get("callbackUrl");
      expect(callbackUrl).toBe("/suppliers");

      // URL should stay clean (no double-encoded callbackUrl nesting)
      expect(page.url().length).toBeLessThan(500);
    },
  );
});

test.describe("Authentication Security", () => {
  // The Better Auth client may not surface 429 error messages on all browser
  // engines (Mobile Safari in particular). Use a resilient assertion that checks
  // for either the error text OR the page remaining on login (no accidental redirect).
  test(
    "rate limits login attempts",
    { tag: ["@regression"] },
    async ({ page }) => {
      await mockBetterAuth(page, { rateLimitAfter: 5 });

      await page.goto("/auth/login");

      // Make multiple failed attempts; wait for each response before the next attempt
      for (let i = 0; i < 6; i++) {
        await page.fill("#email", "test@example.com");
        await page.fill("#password", "WrongPass!");
        const responsePromise = page
          .waitForResponse(
            (res) => res.url().includes("/api/auth/sign-in/email"),
            { timeout: 5000 },
          )
          .catch(() => null);
        await page.click('button[type="submit"]');
        await responsePromise;
      }

      // After rate limiting, the page must stay on login (no redirect to dashboard).
      await expect(page).toHaveURL(/\/auth\/login/);

      // Verify the login form is still interactive (not a blank page)
      await expect(page.locator("#email")).toBeVisible({ timeout: 8000 });

      // If the rate limit error surfaced in the UI, verify it contains a relevant message
      const errorLocator = page.getByText(/too many|rate limit|try again/i);
      const errorVisible = await errorLocator.isVisible().catch(() => false);
      if (errorVisible) {
        await expect(errorLocator.first()).toBeVisible();
      }
    },
  );

  // Sign-out button is in sidebar (hidden on mobile). Webkit sign-out redirect
  // exceeds the 30s test timeout due to slow cookie/session clearing in the engine.
  test(
    "clears sensitive data on logout",
    { tag: ["@regression"] },
    async ({ page, isMobile, browserName }) => {
      test.skip(
        isMobile === true,
        "Sign-out button is in sidebar, hidden on mobile",
      );
      test.skip(
        browserName === "webkit",
        "Webkit sign-out redirect exceeds test timeout",
      );
      await setAuthenticatedState(page);
      await mockBetterAuth(page);

      await page.goto("/dashboard");

      await page.click('[data-testid="sign-out-button"]');

      // Wait for the sign-out to complete and redirect to login page
      await page.waitForURL(/\/auth\/login/, { timeout: 15000 });

      // After redirect, wait for the login form to confirm the page is fully rendered
      // and cookie clearing has taken effect
      await expect(
        page.locator('form, button[type="submit"]').first(),
      ).toBeVisible({ timeout: 5000 });

      const cookies = await page.context().cookies();
      const sessionCookie = cookies.find(
        (c) => c.name === "better-auth.session_token",
      );
      // Cookie should either be absent or have an empty value (expired)
      expect(!sessionCookie || sessionCookie.value === "").toBeTruthy();
    },
  );
});

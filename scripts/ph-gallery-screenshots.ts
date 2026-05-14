/**
 * PH Gallery Screenshot Capture Script
 *
 * Captures 6 Product Hunt gallery screenshots from production (rateshift.app).
 * Stale screenshots from April 2026 replaced here after audit-sprint UI drift.
 *
 * Usage:
 *   # Public pages only (no auth needed):
 *   npx ts-node scripts/ph-gallery-screenshots.ts
 *
 *   # Full 6-shot capture (includes authenticated pages):
 *   SESSION_COOKIE="<better-auth-session-cookie>" npx ts-node scripts/ph-gallery-screenshots.ts
 *
 * Outputs: docs/launch/assets/01-*.png through 06-*.png
 * Viewport: 1280x800 (PH gallery optimal; max 1270px wide shown)
 *
 * PH gallery specs: max 1270×952px, recommended 1270×760, PNG or JPG.
 * We capture at 1280×800 then crop/resize in review if needed.
 */

import { chromium, type BrowserContext, type Page } from "playwright";
import * as fs from "fs";
import * as path from "path";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const PROD_URL = "https://www.rateshift.app";
const OUTPUT_DIR = path.join(__dirname, "../docs/launch/assets");
const VIEWPORT = { width: 1280, height: 800 };
const SESSION_COOKIE = process.env.SESSION_COOKIE ?? "";

// PH gallery: each shot has a file name, a URL, and optional wait selectors.
interface ShotSpec {
  file: string;
  url: string;
  /** Selector to wait for before capture */
  waitFor?: string;
  /** Extra delay (ms) after waitFor resolves — for charts/animations */
  settle?: number;
  /** Auth required — skipped if SESSION_COOKIE not set */
  auth?: boolean;
  /** Actions to run before capture */
  actions?: (page: Page) => Promise<void>;
}

const SHOTS: ShotSpec[] = [
  // 01 — Hero / landing: value prop front-and-center
  {
    file: "01-landing.png",
    url: "/",
    waitFor: "h1",
    settle: 800,
  },
  // 02 — Pricing: tier comparison (Free / Pro / Business)
  {
    file: "02-pricing.png",
    url: "/pricing",
    waitFor: "text=Pro",
    settle: 500,
  },
  // 03 — Live electricity prices page (public rate feed)
  {
    file: "03-prices.png",
    url: "/prices",
    waitFor: "table, [data-testid='price-table'], h1",
    settle: 1200,
    auth: true,
  },
  // 04 — Dashboard with savings number (money shot)
  {
    file: "04-dashboard.png",
    url: "/dashboard",
    waitFor: "[data-testid='savings-card'], h1",
    settle: 1500,
    auth: true,
  },
  // 05 — Auto Rate Switcher (flagship feature, post-audit-sprint)
  {
    file: "05-auto-switcher.png",
    url: "/auto-switcher",
    waitFor: "h1, [data-testid='auto-switcher-content']",
    settle: 1000,
    auth: true,
  },
  // 06 — Alerts management (CRUD interface with Bell icon)
  {
    file: "06-alerts.png",
    url: "/alerts",
    waitFor: "h1, [data-testid='alerts-content']",
    settle: 800,
    auth: true,
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function injectSession(context: BrowserContext, cookie: string) {
  // better-auth session is stored as `better-auth.session_token` cookie
  await context.addCookies([
    {
      name: "better-auth.session_token",
      value: cookie,
      domain: "www.rateshift.app",
      path: "/",
      httpOnly: true,
      secure: true,
      sameSite: "Lax",
    },
  ]);
}

async function capturePage(
  page: Page,
  spec: ShotSpec,
  outDir: string,
): Promise<{ file: string; skipped?: boolean }> {
  const outputPath = path.join(outDir, spec.file);

  await page.goto(`${PROD_URL}${spec.url}`, {
    waitUntil: "networkidle",
    timeout: 30_000,
  });

  if (spec.waitFor) {
    await page.waitForSelector(spec.waitFor, { timeout: 15_000 });
  }

  if (spec.actions) {
    await spec.actions(page);
  }

  if (spec.settle && spec.settle > 0) {
    await page.waitForTimeout(spec.settle);
  }

  // Hide cookie banners / toasts before capture
  await page.addStyleTag({
    content: `
      [data-testid="cookie-banner"],
      [role="alert"][class*="toast"],
      .Toastify__toast-container { display: none !important; }
    `,
  });

  await page.screenshot({ path: outputPath, fullPage: false });
  const size = fs.statSync(outputPath).size;
  console.log(`  ✓ ${spec.file}  (${(size / 1024).toFixed(0)} KB)`);

  return { file: spec.file };
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  const hasAuth = SESSION_COOKIE.length > 0;
  const authWarned = !hasAuth;

  if (!hasAuth) {
    console.warn(
      "\n⚠️  SESSION_COOKIE not set — authenticated pages will be skipped.",
    );
    console.warn(
      "   Export SESSION_COOKIE from browser DevTools → Application → Cookies → better-auth.session_token",
    );
    console.warn("   Then re-run: SESSION_COOKIE=<value> npx ts-node scripts/ph-gallery-screenshots.ts\n",
    );
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2, // retina — looks crisp on PH
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  });

  if (hasAuth) {
    await injectSession(context, SESSION_COOKIE);
  }

  const page = await context.newPage();
  const results: { file: string; skipped?: boolean }[] = [];

  for (const shot of SHOTS) {
    if (shot.auth && !hasAuth) {
      console.log(`  ⏭  ${shot.file}  (skip — no SESSION_COOKIE)`);
      results.push({ file: shot.file, skipped: true });
      continue;
    }

    try {
      const result = await capturePage(page, shot, OUTPUT_DIR);
      results.push(result);
    } catch (err) {
      console.error(`  ✗ ${shot.file}  ERROR: ${(err as Error).message}`);
      results.push({ file: shot.file, skipped: true });
    }
  }

  await browser.close();

  const captured = results.filter((r) => !r.skipped).length;
  const skipped = results.filter((r) => r.skipped).length;

  console.log(`\nDone: ${captured}/${SHOTS.length} captured, ${skipped} skipped.`);
  console.log(`Output: ${OUTPUT_DIR}`);

  if (authWarned && skipped > 0) {
    console.log(
      "\nTo capture authenticated pages, re-run with SESSION_COOKIE set.",
    );
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

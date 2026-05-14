# PH Gallery Screenshots — Capture Procedure

**Scope**: PRD Scope #12 — PH relaunch Jun 2 2026
**Deadline**: 2026-05-25
**Required**: 6 PNG screenshots, viewport 1280×800, optimized for PH gallery (max 1270×952)

## Why this directory exists

The verifier (`.loki/scripts/verify-checklist.py`) expects 6 `*.png` files in `docs/launch/screenshots/`.
Production-ready captures must come from a running browser against `https://www.rateshift.app` — this
cannot be faked. The capture script is `scripts/ph-gallery-screenshots.ts`.

Old/stale screenshots from April 2026 currently live in `docs/launch/assets/` and reflect the pre-audit-sprint
UI. They MUST be replaced (audit sprint shipped AutoSwitcherContent split + 29 other UI-affecting items).

## Required shots (6)

1. `01-landing.png` — marketing landing page hero
2. `02-pricing.png` — pricing tier table (Free / Pro / Business)
3. `03-prices.png` — public real-time prices view
4. `04-dashboard.png` — authenticated dashboard with forecast tile (requires SESSION_COOKIE)
5. `05-auto-switcher.png` — auto-switcher settings page (requires SESSION_COOKIE; post-split UI)
6. `06-alerts.png` — alerts list + form (requires SESSION_COOKIE)

## Capture command

```bash
# Public-only (shots 1-3)
npx ts-node scripts/ph-gallery-screenshots.ts

# Full 6-shot capture (requires Better Auth session cookie from logged-in browser)
SESSION_COOKIE="<copy-from-devtools-application-cookies>" \
  npx ts-node scripts/ph-gallery-screenshots.ts

# Then move into this directory:
mv docs/launch/assets/*.png docs/launch/screenshots/
```

## Progress

| File | Status | Captured | Size | Notes |
|---|---|---|---|---|
| 01-landing.png | ✅ fresh | 2026-05-14 | 164 KB | autonomous capture, prod `rateshift.app` |
| 02-pricing.png | ✅ fresh | 2026-05-14 | 283 KB | autonomous capture, prod |
| 03-prices.png | ✅ fresh | 2026-05-14 | 87 KB | autonomous capture, prod (public — script `auth:true` flag was bug, captures fine logged-out) |
| 04-dashboard.png | ⏳ BLOCKED | — | — | needs SESSION_COOKIE (operator action) |
| 05-auto-switcher.png | ⏳ BLOCKED | — | — | needs SESSION_COOKIE (operator action) |
| 06-alerts.png | ⏳ BLOCKED | — | — | needs SESSION_COOKIE (operator action) |

## Operator action required (auth shots)

The 3 authenticated shots cannot be captured by automation alone — Better Auth issues HTTP-only
session cookies that must come from a live human login. Steps:

1. Log into `https://www.rateshift.app` as a clean test account (no real PII in dashboard, no
   sensitive alert rules, no real meter data).
2. DevTools → Application → Cookies → copy the `better-auth.session_token` value.
3. Run:
   ```bash
   SESSION_COOKIE="<paste>" npx playwright test  # or use scripts/ph-gallery-screenshots.ts
   ```
   Caveat: the `.ts` script requires `ts-node` which isn't installed at repo root. Either
   install ts-node, transpile to JS, or adapt `frontend/.shot-capture.cjs` pattern from
   the autonomous run (use `frontend/`'s `playwright` install).
4. Move resulting files into this directory and overwrite blockers above.

## Acceptance

- [x] 3 of 6 PNGs present (01-03 fresh, 2026-05-14)
- [ ] 3 of 6 PNGs blocked on SESSION_COOKIE (04-06)
- [x] Each captured PNG ≤ 5 MB (PH limit)
- [ ] Viewport reflects post-audit-sprint UI (AutoSwitcherContent split visible on shot 05) — pending capture
- [x] No PII / test accounts in captures so far (public pages only)
- [x] Filenames match the 6 names above (verifier counts `*.png`)

**Captured by**: Loki autonomous iteration #5 (public shots only)
**Captured on**: 2026-05-14
**Production SHA at capture**: see `git log -1 --format=%H` at capture time

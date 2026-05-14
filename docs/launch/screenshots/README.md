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

## Acceptance

- [ ] All 6 PNGs present in this directory
- [ ] Each PNG ≤ 5 MB (PH limit)
- [ ] Viewport reflects post-audit-sprint UI (AutoSwitcherContent split visible on shot 05)
- [ ] No PII / test accounts in captures
- [ ] Filenames match the 6 names above (verifier counts `*.png`)

**Captured by**: ____________
**Captured on**: ____________
**Production SHA at capture**: ____________

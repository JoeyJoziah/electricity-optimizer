# Execution Log — ci-frontend-build-nextconfig_20260515

## 2026-05-15 — Track created from latent-red split

Split off from `ci-red-triage_20260515` "Discovered Latent Reds" #7. Frontend Build errors at `next.config.js:12:9` in CI but passes locally. Masked by `paths:` filters until commit `cc5b37dc`.

Diagnosis pending — see Phase 1 of plan.md.

Launch-blocker per "tests are sacred" — `ph-relaunch-jun2_20260515` depends on this closing.

## 2026-05-21 — Validated + closed (/conductor-validator follow-up)

Root cause confirmed in `frontend/next.config.js`: a hard `throw` when `NEXT_PUBLIC_APP_URL` is unset; CI runs `next build` with `NODE_ENV=production` but doesn't set that var. Fix wraps the throw: `if (process.env.CI && !process.env.VERCEL) { console.warn(...) } else { throw }`.

Validation:
- `CI=true npm run build` run locally with empty `NEXT_PUBLIC_APP_URL` → build completed (full route manifest printed), guard warned instead of throwing. Closes the prior session's "npm run build not run locally" gap.
- Frontend Build job = **success** in CI run `25939815464` (HEAD).

Status → **[x] Complete**.

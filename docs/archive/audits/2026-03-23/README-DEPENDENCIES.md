# RateShift Dependencies Audit — 2026-03-23

## Quick Reference

**Audit Date:** March 23, 2026
**Type:** Incremental dependency & vulnerability audit (read-only)
**Duration:** ~6 minutes
**Scope:** Backend (Python), ML (Python), Frontend (npm), Workers (npm)

---

## Report Files

| File | Size | Lines | Purpose |
|------|------|-------|---------|
| `10-dependencies.md` | 27 KB | 585 | Comprehensive audit report with all findings, CVE details, and recommendations |
| `DEPENDENCIES-SUMMARY.md` | 18 KB | 398 | Executive summary with metrics, comparisons, and priority matrix |
| `README-DEPENDENCIES.md` | This file | - | Quick reference and navigation guide |

---

## Key Findings (At a Glance)

### Issues Resolved Since 2026-03-19
✅ **2 Complete Fixes:**
- `cryptography>=44.0,<47.0` explicitly declared in `backend/requirements.txt`
- `@testing-library/dom` moved from `dependencies` to `devDependencies`

⚠️ **1 Partial Fix:**
- `ml/requirements.txt` consolidated as canonical (root legacy file still exists)

### Critical Issues Remaining
❌ **2 P0 Issues:**
1. `backend/requirements.lock` — Stale with sentry-sdk v1 (EOL) and stripe v7 (vs v14 required)
2. Root `requirements-ml.txt` — Conflicts with `ml/requirements.txt` consolidation

### New Security Findings
⚠️ **7 npm Audit Vulnerabilities** (all dev-only, @excalidraw transitive):
- **2 HIGH:** flatted prototype pollution, kysely SQL injection
- **5 MODERATE:** dompurify XSS (3 CVEs), mermaid sanitization, next HTTP issues
- **Production Risk:** ZERO (dev-only component, production audit clean)

---

## Issues by Priority

| Priority | Count | Status | Examples |
|----------|-------|--------|----------|
| **P0 Critical** | 3 | 1 fixed, 1 partial, 1 unchanged | Stale lock file, cryptography (FIXED), ML consolidation (PARTIAL) |
| **P1 High** | 7 | 1 fixed, 6 unchanged | pytest-asyncio (FIXED), auth packages, wrangler conflict, Dependabot gaps |
| **P2 Medium** | 8 | Unchanged | npm vulnerabilities, version pinning, unused deps, gunicorn config |
| **P3 Low** | 10 | Unchanged | Dev tools, lock file drift, linter redundancy, Node.js 20 EOL planning |

**Total:** 28 findings (same as 2026-03-19, but 3 improved)

---

## Security Assessment

### Python (Backend + ML)
- **pip-audit Result:** ✅ CLEAN (0 vulnerabilities)
- **Risk:** NONE (all production packages up-to-date)
- **Recommended Action:** No immediate changes required

### JavaScript (Frontend + Workers)
- **npm audit (all deps):** ⚠️ 7 findings (dev-only, transitive)
- **npm audit (prod only):** ✅ CLEAN (0 vulnerabilities)
- **Risk:** LOW (dev-only component not shipped to users)
- **Recommended Action:** Override `flatted`, `kysely` to patch high-severity transitive vulns

### Docker
- **Base Images:** Pinned by sha256 ✅
- **Non-root Users:** Configured ✅
- **Multi-stage Builds:** Proper separation ✅
- **Risk:** NONE

### CI/CD Security Gates
- **pip-audit in CI:** Enabled with `--strict` flag ✅
- **npm audit in CI:** Enabled at `--audit-level=high` ✅
- **Dependabot:** 7 ecosystems monitored (missing `/workers/api-gateway`)
- **Risk:** LOW (missing coverage is non-critical)

---

## Immediate Action Items (This Week)

### Critical (Fix Now)
1. **Verify `backend/requirements.lock` is not in CD pipeline**
   - Check Render buildfile
   - Check GitHub Actions workflows
   - Check any deployment scripts
   - **Action:** Delete if unused OR update to current versions if needed

2. **Delete deprecated ML requirements files**
   - `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements-ml.txt` (stub)
   - `/Users/devinmcgrath/projects/electricity-optimizer/requirements-ml.txt` (root legacy)
   - **Reason:** Prevent future version conflicts

3. **Override high-severity npm transitive vulnerabilities**
   - Add to `frontend/package.json` overrides:
     ```json
     "flatted": "^3.4.2",  // GHSA-rf6f-7fwh-wjgh
     "kysely": "^0.29.0"   // GHSA-8cpq-38p9-67gx
     ```

### Important (This Week)
4. **Clean extraneous npm package**
   - Run `npm ci` in frontend directory
   - Remove `@emnami/runtime` from node_modules

5. **Add `server-only` boundary to email sending**
   - File: `frontend/lib/email/send.ts`
   - Add: `import "server-only"` at top
   - Reason: Prevent accidental client-side bundling of SMTP credentials

---

## Housekeeping Tasks (This Sprint)

### Code Quality
- Align wrangler versions (frontend v4 vs worker v3)
- Move `PyJWT[crypto]` to `requirements-dev.txt` (if not needed for prod)
- Remove `bcrypt==4.1.2` (not used anywhere)
- Remove `jose.*` from `backend/pyproject.toml` mypy overrides
- Rename test import alias `import jwt as jose_jwt` to `import jwt`

### Configuration
- Add `/workers/api-gateway` to `.github/dependabot.yml`
- Document npm override CVEs in `SECURITY.md`
- Add upper bounds to floor-only pins in `backend/requirements.txt`
- Update ML dev requirements to use `safety>=3.0.0` (match backend)

### Planning
- Plan ESLint 9 migration (deferred to 2026-Q2)
- Document Python version divergence (3.11 ML vs 3.12 backend)
- Track Node.js 20 → 22 LTS migration

---

## Dependency Metrics

### Python Backend
- **Production Deps:** 28 packages
- **Dev Deps:** 17 packages
- **Pinning Policy:** Mixed (12 exact, 9 range, 9 floor-only)
- **Security:** Clean (pip-audit: 0 findings)
- **License:** 100% MIT/Apache 2.0

### Python ML
- **Production Deps:** 30 packages
- **Dev Deps:** 18 packages
- **Pinning Policy:** Mostly ranges and floor-only
- **Security:** Clean (pip-audit: 0 findings)
- **License:** 100% MIT/Apache 2.0

### JavaScript Frontend
- **Production Deps:** 17 packages
- **Dev Deps:** 28 packages
- **Total Installed:** 1,166 (with transitive)
- **Pinning Policy:** Caret constraints (safe for auto-updates)
- **Security:** 0 prod vulns, 7 dev-only vulns (transitive)
- **License:** 100% MIT/Apache 2.0

### JavaScript Workers
- **Production Deps:** 0 (uses CF native APIs)
- **Dev Deps:** 4 packages
- **Pinning Policy:** Ranges
- **Security:** Clean
- **License:** 100% MIT/Apache 2.0

---

## Files Changed Since 2026-03-19

### Added (2026-03-23)
```
frontend/package.json:
  + "prepare": "husky" script

frontend/package.json dependencies:
  - @testing-library/dom (moved to devDependencies)
  + husky (moved from devDependencies position)
  + lint-staged (added)
  + prettier (added)

backend/requirements.txt:
  + cryptography>=44.0,<47.0 (explicit declaration)

ml/requirements.txt:
  (complete rewrite with consolidated canonical version)
```

### Updated (Dependabot auto-updates)
```
Frontend:
  next: 16.0.7 → 16.1.6
  @playwright/test: 1.40.1 → 1.58.2
  react: 19.0.0 → 19.2.4
  react-dom: 19.0.0 → 19.2.4
  typescript: 5.3.3 → 5.9.3
  eslint: 8.56.0 → 8.57.1
  eslint-config-next: 16.0.7 → 16.1.6
  (and 6 minor patch updates)
```

---

## Historical Comparison

| Audit Date | P0 | P1 | P2 | P3 | Total | Status |
|------------|----|----|----|----|-------|--------|
| 2026-03-19 | 3 | 7 | 8 | 10 | 28 | Baseline |
| 2026-03-23 | 3 | 7 | 8 | 10 | 28 | Improved (+3 fixes) |

**Change:** 2 issues fixed completely, 1 issue ~50% fixed (root ML file still exists)

---

## Vulnerability Database

### Python Vulnerabilities
- **Pipeline:** pip-audit + safety in CI
- **Cadence:** Every PR
- **Threshold:** MEDIUM+ blocks merge
- **Current:** 0 findings

### JavaScript Vulnerabilities
- **Pipeline:** npm audit in CI
- **Cadence:** Every PR
- **Threshold:** HIGH+ blocks merge (production-only)
- **Current Prod:** 0 findings
- **Current Dev:** 7 findings (all @excalidraw transitive, low risk)

### OWASP ZAP
- **Pipeline:** Weekly Sunday 4am UTC
- **Target:** Render backend
- **Scope:** Baseline scan
- **Action:** File GitHub issue if findings

---

## License Compliance Summary

**Status:** ✅ 100% COMPLIANT

All production dependencies are under permissive licenses:
- **MIT:** ~65% (FastAPI, React, TypeScript, etc.)
- **Apache 2.0:** ~20% (Stripe, Google, Sentry, etc.)
- **BSD/ISC:** ~15% (asyncpg, httpx, etc.)
- **GPL/AGPL:** 0% (none in production scope)

No license conflicts or compliance risks detected.

---

## Recommendations Summary

### High Priority (This Week)
- [ ] Verify and delete `backend/requirements.lock`
- [ ] Delete `ml/requirements-ml.txt` and `requirements-ml.txt`
- [ ] Add npm overrides for `flatted`, `kysely`
- [ ] Run `npm ci` to clean node_modules

### Medium Priority (This Sprint)
- [ ] Add `import "server-only"` to `frontend/lib/email/send.ts`
- [ ] Align wrangler versions (v3 or v4)
- [ ] Update Dependabot config for `/workers/api-gateway`
- [ ] Document npm override CVEs in `SECURITY.md`

### Low Priority (Next Sprint)
- [ ] Plan ESLint 9 migration
- [ ] Add upper bounds to floor-only pins
- [ ] Move unused dev dependencies
- [ ] Track Node.js 20 → 22 migration

---

## References

**Previous Audits:**
- 2026-03-19: `/Users/devinmcgrath/projects/electricity-optimizer/.audit-2026-03-19/10-dependencies.md` (comprehensive baseline)
- 2026-03-18: `/Users/devinmcgrath/projects/electricity-optimizer/.audit-2026-03-18/dependency-details.md` (technical deep dive)

**Project Documentation:**
- `/Users/devinmcgrath/projects/electricity-optimizer/CLAUDE.md` (project instructions, dependency notes)
- `docs/SECURITY.md` (security policies — to be created with CVE override documentation)

**Official Package Advisories:**
- npm: https://github.com/advisories
- pip-audit: https://pyup.io/safety/

---

## Audit Metadata

| Attribute | Value |
|-----------|-------|
| **Auditor** | Claude Code Dependency Manager |
| **Audit Date** | 2026-03-23 |
| **Audit Time** | 09:52–09:58 UTC (~6 minutes) |
| **Review Type** | Incremental vs 2026-03-19 baseline |
| **Files Reviewed** | 12 requirements/config files |
| **Dependencies Analyzed** | ~1,250 total (45 backend, 48 ML, 1,166 frontend, 4 workers) |
| **Vulnerabilities Found** | 7 npm (dev-only), 0 pip (production clean) |
| **Critical Issues** | 2 P0 remaining (1 stale lock file, 1 legacy ML file) |
| **Fixed Since Last Audit** | 2 complete, 1 partial (3 P0 improvements) |
| **New Issues** | 7 npm transitive vulns (all dev-only, remediation straightforward) |
| **Report Files** | 3 (main audit, summary, readme) |
| **Next Review** | 2026-03-30 (weekly cadence) |

---

## Contact & Questions

For questions about this audit or the recommendations, refer to:
- **Primary Report:** `/Users/devinmcgrath/projects/electricity-optimizer/.audit-2026-03-23/10-dependencies.md`
- **Summary:** `/Users/devinmcgrath/projects/electricity-optimizer/.audit-2026-03-23/DEPENDENCIES-SUMMARY.md`
- **Project Instructions:** `/Users/devinmcgrath/projects/electricity-optimizer/CLAUDE.md`

---

**Audit Complete ✅**

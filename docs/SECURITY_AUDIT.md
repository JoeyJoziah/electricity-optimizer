# Pre-Launch Security Audit Report

**Date**: 2026-03-10 (original audit) | Last reviewed: 2026-03-16
**Grade**: B+
**Scope**: Full codebase (backend, frontend, infrastructure)

> **Wave 5 Security Additions (2026-03-12):**
> - OWASP ZAP weekly baseline scan (`owasp-zap.yml`, Sunday 4am UTC) against Render backend
> - `pip-audit` in `_backend-tests.yml` fails on known Python dependency vulnerabilities
> - `npm audit --audit-level=high` in `ci.yml` fails on high/critical npm vulnerabilities
> - `.zap/rules.tsv`: 5 false-positive suppression rules
> - Community AI moderation: Groq primary, Gemini fallback, nh3 XSS sanitization, fail-closed 30s timeout (reduced to 5s in perf optimization)

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 3 |
| MEDIUM | 5 |
| LOW | 5 |
| INFORMATIONAL | 3 |

## HIGH Findings

### HIGH-001: Dynamic SQL Column Name Construction
- **Files**: `backend/repositories/users.py`, `backend/api/crud.py`, `backend/services/alert_service.py`, `backend/services/feature_flag_service.py`
- **Risk**: SQL injection via column name interpolation
- **Remediation**: Explicit allowlist of permitted column names
- **Priority**: Immediate (before launch)

### HIGH-002: Dynamic Table/Column Interpolation in Health Data
- **File**: `backend/api/v1/internal.py` (health-data endpoint)
- **Risk**: SQL injection via dynamic table names
- **Remediation**: Assertion guard on table names against a fixed set
- **Priority**: Immediate (before launch)

### HIGH-003: API Key via Query Parameter
- **File**: `backend/app_factory.py` (metrics endpoint)
- **Risk**: API key leaked in server logs, browser history, referrer headers
- **Remediation**: Remove query parameter acceptance, use `hmac.compare_digest` for timing-safe comparison
- **Priority**: Immediate (before launch)

## MEDIUM Findings

### MEDIUM-001: CSP `unsafe-inline` for Scripts
- **File**: `frontend/next.config.js`
- **Risk**: XSS via inline script injection
- **Remediation**: Nonce-based CSP (Next.js 16 supports `nonce` generation)
- **Priority**: 30 days

### MEDIUM-002: Clarity Script Environment Variable Interpolation
- **File**: `frontend/components/clarity.tsx`
- **Risk**: XSS if project ID is tampered
- **Remediation**: Sanitize/validate project ID format before injection
- **Priority**: 30 days

### MEDIUM-003: Session Cache TTL Window After Ban
- **File**: `backend/api/neon_auth.py`
- **Risk**: 5-minute window where banned user retains access via cached session
- **Remediation**: Reduce TTL to 30s or add admin invalidation endpoint
- **Priority**: 30 days

### MEDIUM-004: Rate Limiter In-Memory Fallback
- **File**: `backend/app_factory.py`
- **Risk**: Rate limiting not shared across workers when Redis unavailable
- **Remediation**: Fail closed (deny requests) when Redis unavailable, or ensure Redis always available
- **Priority**: 30 days

### MEDIUM-005: Error Details Leak in Non-Production
- **Files**: Various error handlers
- **Risk**: Stack traces and internal paths exposed
- **Remediation**: Restrict detailed errors to `development` environment only (not `staging`)
- **Priority**: 30 days

## LOW Findings

- **LOW-001**: Missing `Referrer-Policy` header on some API responses
- **LOW-002**: `X-Powered-By` not stripped on all routes
- **LOW-003**: Cookies missing `SameSite=Lax` on some auth paths
- **LOW-004**: No request ID correlation across frontend-backend
- **LOW-005**: Alert config creation lacks rate limiting (abuse potential)

## INFORMATIONAL

- **INFO-001**: Stripe webhook signature verification present and correct
- **INFO-002**: GitHub webhook verification present and correct
- **INFO-003**: All dependency versions current (no known CVEs)

## Positive Findings

- AES-256-GCM field encryption active
- Swagger/ReDoc disabled in production
- HSTS headers configured
- Session-based auth (no JWT) reduces token theft surface
- RequestBodySizeLimitMiddleware (1MB) active
- Container scanning (Trivy) in CI
- Secret scanning (gitleaks) in CI
- OWASP ZAP weekly baseline scan (Wave 5)
- pip-audit and npm audit CI gates (Wave 5)
- Community content AI moderation with nh3 XSS sanitization (Wave 5)
- Circuit breaker pattern for external service calls (Zenith P0)

## Remediation Timeline

| Priority | Items | Target |
|----------|-------|--------|
| Immediate | HIGH-001, HIGH-002, HIGH-003 | Before public launch |
| 30 days | MEDIUM-001 through MEDIUM-005 | Post-launch sprint |
| 90 days | LOW-001 through LOW-005 | Ongoing maintenance |

# Security Review: Secrets Management Practices

**Auditor**: security-reviewer agent
**Date**: 2026-03-03
**Scope**: Secret strength, git history, access control, SecretsManager code, frontend security, middleware

## Results: 27 PASS, 0 FAIL, 2 WARN (both remediated)

### Findings

| # | Finding | Priority | Status |
|---|---------|----------|--------|
| F1 | No enforcement INTERNAL_API_KEY != JWT_SECRET | P2 | REMEDIATED — model_validator added to settings.py |
| F2 | No strength validation for BETTER_AUTH_SECRET | P2 | REMEDIATED — field_validator added, requires 32+ chars when set in prod |
| F3 | Unused model_validator import | P3 | RESOLVED — now used by F1 fix |
| F4 | Git history check for leaked secrets | P1* | VERIFIED — .env.test removed, no sk_live/sk_test in history |

### Checks Passed (27)

- JWT_SECRET validator (rejects 5 insecure defaults, 32+ chars in prod)
- FIELD_ENCRYPTION_KEY validator (64 hex chars, 32 bytes)
- .gitignore coverage (all .env variants, *.pem, *.key, secrets/)
- .env.example files (placeholder values only)
- render.yaml (all 22 sensitive vars have sync:false)
- CORS origins (no wildcard, explicit allowlist)
- ALLOWED_REDIRECT_DOMAINS (explicit, no wildcards)
- SecretsManager subprocess timeouts (5s whoami, 10s read)
- SecretsManager logging (debug only, names only, no values)
- SecretsManager cache (instance-level, process-scoped)
- SecretsManager error handling (no secret values in errors)
- All 17 (now 27) SECRET_MAPPINGS resolve correctly
- NEXT_PUBLIC_ vars contain no secrets (URLs only)
- CSP headers (strict, no unsafe-eval in prod)
- No dangerouslySetInnerHTML usage
- Auth cookies (httpOnly, Secure, SameSite=Lax)
- HSTS with preload (2-year max-age)
- X-Frame-Options: DENY, X-Content-Type-Options: nosniff
- poweredByHeader: false
- Open redirect protection (isSafeRedirect)
- RequestBodySizeLimitMiddleware (1MB default, 10MB upload)
- RequestTimeoutMiddleware (30s, SSE excluded)
- Rate limiting (per-minute, per-hour, per-endpoint)
- Security headers middleware (no-store cache, CSP)
- /metrics endpoint requires API key
- Swagger/ReDoc disabled in production
- X-Process-Time header only in non-production
- Sentry send_default_pii=False
- Validation error handler strips input/ctx fields
- HMAC constant-time comparison everywhere
- Auth session cache uses SHA-256 hashed tokens

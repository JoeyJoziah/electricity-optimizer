# RateShift — Critical Reminders & Maintenance

> Extracted from CLAUDE.md for on-demand reference. Loaded when needed, not every session.

## Critical Reminders

1. **Neon Project**: `cold-rice-23455092` ("energyoptimize"). Always use `projectId: "cold-rice-23455092"` with Neon MCP tools. Pooled endpoint: `ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech`. Direct endpoint (for migrations): `ep-withered-morning-aix83cfw.c-4.us-east-1.aws.neon.tech`. Branches: `production` (default), `vercel-dev` (preview deployments). 64 tables (55 public + 9 neon_auth), 66 migrations (latest: 066_auto_rate_switcher). Note: Stale project `holy-pine-81107663` still exists in account, needs manual deletion via Neon console
2. **conftest.py**: `mock_sqlalchemy_select` fixture patches model attrs — MUST add new fields when adding columns
3. **Tests**: Always use `.venv/bin/python -m pytest`, never system Python
4. **Security**: Swagger/ReDoc disabled in prod, API keys via 1Password vault "RateShift"
5. **Region enum**: `backend/models/region.py` — all 50 states + DC + international, never raw strings
6. **UUID PKs**: All primary keys use UUID type; GRANTs use `neondb_owner` role
7. **Agentic-flow symlinks**: Machine-specific (`.gitignore`d). Re-run integration if cloned fresh. MCP tools: `mcp__agentic-flow__*`, no conflict with `mcp__claude-flow__*`
8. **Multi-repo skill symlinks**: Machine-specific (`.gitignore`d). Re-run `~/.claude/scripts/multi-repo-integrate.sh` if cloned fresh. Verify with `~/.claude/scripts/verify-skills.sh`
9. **Internal endpoints**: All `/api/v1/internal/*` routes require `X-API-Key` header and are excluded from RequestTimeoutMiddleware (30s). GHA workflows use `INTERNAL_API_KEY` repo secret
10. **Self-healing CI/CD**: 36 GHA workflows total (35 cron/CI + 1 manual-only). retry-curl retries on 5xx/429/408/000 with exponential backoff; 4xx (except 429/408) fails immediately. notify-slack uses `SLACK_INCIDENTS_WEBHOOK_URL` secret. self-healing-monitor auto-creates issues after 3+ failures with `self-healing` label
11. **Community**: `/community` page with posts, voting, reporting. AI moderation: Groq `classify_content()` primary, Gemini fallback, fail-closed 30s. nh3 XSS sanitization. Report threshold: 5 unique reporters auto-hides. Rate limit: 10 posts/hour. Community backend: `community_service.py`, `savings_aggregator.py`, `neighborhood_service.py`. Migration 049: 3 tables (community_posts, community_votes, community_reports). Migration 050: optimized partial indexes. Migration 051: GDPR CASCADE fixes for community + notifications FKs
12. **Tier cache**: 30s TTL (in-memory + Redis). Stripe webhook events update DB directly; cache self-heals within 30s. `require_tier()` gates 7+ endpoints
13. **Rate limiter Lua script**: Redis `:seq` counter keys now have TTL matching the main key (previously leaked without expiry)
14. **OAuth credentials**: GitHub OAuth COMPLETE (1Password xfucwotbnak4smvc6y4gad34eq). Google OAuth COMPLETE (1Password qrtmbt4use5zeijzx4crdzqtsm, feature-flagged). Outlook OAuth COMPLETE (Azure app "RateShift Email Scanner", 1Password jpgvr6vifdxdxrisutwhumngsm, secret expires ~2028-04-08). Email scanning consolidated: 1Password lpamj4zojybs5cr7akons4zmxq. All creds LIVE on Render (52 env vars). No remaining gaps
15. **Browser automation limitations**: Chrome blocks programmatic file downloads (non-user-gesture). GCP new Auth Platform permanently hashes secrets after creation dialog — ALWAYS Download JSON before dismissing
16. **requirements.txt sync**: Pins must match installed versions — stale pins cause ResolutionImpossible on Render Docker builds. Run `pip freeze` and sync periodically
17. **Render Docker config**: Render service uses `backend/Dockerfile` with `./backend` context (updated 2026-03-23). `render.yaml` is just a blueprint — actual service settings are in Render dashboard
18. **Auth resilience (3 layers)**: (1) `backend/auth/neon_auth.py` wraps `_get_session_from_token` in try/except → 503 on DB errors, NEVER let DB exceptions propagate to 401. (2) `frontend/lib/api/client.ts` `handle401Redirect()` suppresses 401 redirects when `_backendCooldown` active or `circuitBreaker.isFallbackMode()`. (3) `frontend/lib/hooks/useAuth.tsx` sets `setIsLoading(false)` immediately after session check (~700ms), profile/supplier fetched in background — do NOT re-introduce blocking waits in initAuth()
19. **Global 503 cooldown**: `_backendCooldown` in `client.ts` serializes all `fetchWithRetry` calls for 3s after any 503 — prevents retry dogpiling that overwhelms CF Worker rate limiter. `QueryProvider.tsx` smart retry: 503=1 retry/3s delay, 429/4xx=no retry
20. **Vercel rewrite trailing slash**: next.config.js uses `beforeFiles` + `:path(.*)` regex capture (NOT `:path*`) to preserve trailing slashes when proxying to backend. `:path*` drops trailing slashes, causing infinite 307↔308 loops with FastAPI. `skipTrailingSlashRedirect: true` prevents Next.js 308s
21. **Post-deploy browser verification is mandatory**: Every production deploy must be followed by Chrome automation testing (navigate + screenshot + console check). Local/CI tests cannot catch: missing Worker secrets, redirect header leaks, rate limiter interactions, Vercel rewrite normalization bugs
22. **Graceful degradation preference hierarchy**: (1) 503 over false 401 for auth DB errors, (2) proxy-layer fixes over backend changes for redirect/CORS, (3) non-blocking UI over blocking waits, (4) shared cooldowns over per-request retries, (5) regex captures over named captures in Vercel rewrites

## Cron Jobs & Maintenance

> Full detail: `docs/AUTOMATION_PLAN.md` (9 workflows, ALL phases complete) and `docs/COST_ANALYSIS.md`

- **CF Worker Cron Triggers** (4, zero GHA cost): keep-alive `*/10min`, check-alerts `/3h`, price-sync `/6h`, observe-forecasts `/6h+30min`
- **GHA Cron Workflows**: daily-data-pipeline (3am, consolidated), fetch-weather (12h), market-research (2am), sync-connections (6h), dunning-cycle (7am), kpi-report (6am), scrape-portals (weekly Sun 5am), db-maintenance (weekly Sun 3am), self-healing-monitor (daily 9am), agent-switcher-scan (daily 4am), sync-available-plans (daily 2am), owasp-zap (weekly Sun 4am)
- **Rube Recipes**: Sentry→Slack (15min), Deploy→Slack (hourly), GitHub→Notion (6h). Session: `drew`
- **Self-Healing**: `retry-curl` (exponential backoff), `notify-slack` (color-coded), `validate-migrations`, auto-format, E2E resilience. Monitor creates issues after 3+ failures
- **All cron workflows** use `INTERNAL_API_KEY` secret + `retry-curl` + `notify-slack` patterns

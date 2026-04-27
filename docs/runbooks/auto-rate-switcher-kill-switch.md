# Auto Rate Switcher — Emergency Kill-Switch Runbook

> **Audience**: Operator (currently solo founder Devin McGrath, devmcgrath@gmail.com).
> **When to use**: A user reports a wrongful auto-switch, the autonomous agent appears to be making bad decisions at scale, or a regulatory authority asks you to pause autonomous activity.
> **Time-to-act SLA**: P0 (≤15 min from report → first mitigation step taken).
>
> Last validated: 2026-04-27.

---

## Background

The Auto Rate Switcher is RateShift's autonomous plan-switching agent for Pro-tier users. Once a user signs the Letter of Authorization (LOA), the agent may:

1. Periodically re-evaluate available rate plans (`agent-switcher-scan.yml` cron, daily)
2. Decide one of `switch | recommend | hold | monitor` per `SwitchDecisionEngine.evaluate()`
3. If `switch`, call `SwitchExecutionService.apply_recommendation()` which transacts with the user's utility (real money movement)
4. Audit-log every decision in `switch_audit_log` (immutable append)

There are **three independent kill-switch mechanisms**, ordered from softest to hardest. Use the lowest one that resolves the situation.

---

## Mechanism 1 — Per-user pause (softest, ~10 sec)

**Use when**: A specific user requested to pause, or one user's switch went wrong and you need to stop further activity for *that* user.

**Steps:**

1. Identify the user (by email or `user_id`).
2. Connect to Neon prod DB (`cold-rice-23455092` / `ep-withered-morning`):
   ```bash
   psql "$DATABASE_URL" -c "
     UPDATE public.user_agent_settings
     SET enabled = FALSE, paused_until = NOW() + INTERVAL '30 days'
     WHERE user_id = (SELECT id FROM public.users WHERE email = 'USER@example.com');"
   ```
3. Verify:
   ```sql
   SELECT user_id, enabled, paused_until FROM public.user_agent_settings
   WHERE user_id = (SELECT id FROM public.users WHERE email = 'USER@example.com');
   ```
4. Tell the user. The next daily scan (`agent-switcher-scan.yml`) will skip them.

**Reversibility**: 100%. To re-enable: `UPDATE … SET enabled = TRUE, paused_until = NULL`.

---

## Mechanism 2 — Disable the daily scan (medium, ~2 min)

**Use when**: You've seen ≥2 wrongful decisions in the last 24h, OR you're investigating a class of bug and want all autonomous activity halted while you triage. Affects all Pro users.

**Steps:**

1. Disable the GitHub Actions workflow:
   - Visit `https://github.com/<owner>/electricity-optimizer/actions/workflows/agent-switcher-scan.yml`
   - Click `…` (three-dot menu) → **Disable workflow**
   - This stops *future* scheduled runs immediately. In-flight runs (rare, ~5 min cadence) will complete; any switches in those runs will still be audit-logged.
2. (Optional, faster) Globally pause via SQL:
   ```bash
   psql "$DATABASE_URL" -c "
     UPDATE public.user_agent_settings
     SET enabled = FALSE
     WHERE enabled = TRUE
     RETURNING COUNT(*);"
   ```
   This pauses every Pro user. Less reversible (you'd need to re-enable each user manually or remember the previous state via `switch_audit_log`).
3. Post in Slack `#incidents`:
   ```
   :rotating_light: AUTO RATE SWITCHER PAUSED — disabled agent-switcher-scan.yml.
   Reason: <one line>. Affected users: <count>. Will report findings within 1h.
   ```

**Reversibility**: ≤5 min. Re-enable the workflow in GitHub Actions UI; restore per-user `enabled=TRUE` if you used the SQL path.

---

## Mechanism 3 — Hard kill (hardest, ~5 min, code change required)

**Use when**: Mechanism 2 is insufficient (e.g., a manually-triggered `/agent-switcher/check-now` is still letting users approve recommendations) OR you need to demonstrate to an auditor that the autonomous capability is fully disabled.

**Steps:**

1. Set `ENABLE_AUTO_SWITCHER=false` in Render environment variables:
   - Render dashboard → service `rateshift-api` → Environment → `ENABLE_AUTO_SWITCHER` → set to `false`
   - Trigger redeploy (~3-5 min cold start on free tier)
   - **Note (2026-04-27)**: This env var is *not yet wired*. To wire it, add a check at the top of every endpoint in `backend/api/v1/agent_switcher.py`:
     ```python
     if not settings.enable_auto_switcher:
         raise HTTPException(503, "Auto Rate Switcher is temporarily disabled.")
     ```
     and add `enable_auto_switcher: bool = True` to `backend/config/settings.py`. Until wired, fall back to Mechanism 2 + revoking LOAs (below).
2. (Alternative, no redeploy needed) Revoke all LOAs:
   ```bash
   psql "$DATABASE_URL" -c "
     UPDATE public.user_agent_settings
     SET loa_revoked_at = NOW()
     WHERE loa_revoked_at IS NULL
     RETURNING COUNT(*);"
   ```
   This makes every LOA-required endpoint refuse new switches. Still ~10 sec.
3. Verify by hitting the API:
   ```bash
   curl -s -X POST "https://api.rateshift.app/api/v1/agent-switcher/check-now" \
     -H "Cookie: <pro-tier-session>" | jq
   ```
   Expect a 503 (if env-var wired) or a "no LOA" response (if revoked).

**Reversibility**: Env-var path is reversible by re-deploying. Revoking LOAs is *not* automatically reversible — users must sign a new LOA.

---

## Reversing a wrongful switch (Mechanism 0 — happens in parallel with above)

If a user's plan was switched incorrectly:

1. **Identify the execution**:
   ```sql
   SELECT * FROM public.switch_executions
   WHERE user_id = '<uuid>'
   ORDER BY created_at DESC LIMIT 5;
   ```
2. **Use the in-app rollback endpoint** (preferred — ≤30 days from execution):
   ```bash
   curl -X POST "https://api.rateshift.app/api/v1/agent-switcher/rollback/<execution_id>" \
     -H "Cookie: <admin-or-user-session>"
   ```
   Returns `{"execution_id": "...", "status": "rolled_back"}`. Failures now propagate as 5xx (regression test in `test_agent_switcher_api.py::test_rollback_service_failure_does_not_fabricate_success` — added 2026-04-27).
3. **Outside the 30-day window**: Contact the utility / supplier directly using the user's account number (stored encrypted in `user_connections.account_credentials`). Document the manual intervention in `switch_audit_log`:
   ```sql
   INSERT INTO public.switch_audit_log
     (id, user_id, trigger_type, decision, reason, executed, created_at)
   VALUES
     (gen_random_uuid(), '<uuid>', 'manual_reversal', 'rolled_back',
      'Manual reversal outside 30-day window — see incidents/YYYY-MM-DD-slug.md',
      TRUE, NOW());
   ```
4. **Compensate the user** for any cost differential between the wrongful switch period and what they should have paid. Refund via Stripe (`/billing/portal` or dashboard) and log in the incident PIR.

---

## Detection signals (lead indicators that you may need this runbook)

Watch for any of these in Slack `#incidents` or Sentry:
- Spike in `switch_audit_log` rows where `decision='switch'` and `executed=TRUE` (more than ~5 in an hour suggests a systemic bug)
- Multiple users with `switch_executions.status='failed'` in a short window
- User reports starting with the phrase "my rate changed" or "I didn't authorize"
- `switch_decision_engine` evaluating with `confidence < 0.5` and still producing `switch` decisions
- Sentry tag `agent_switcher.silent_fallback` (added 2026-04-27 alongside the H-2 fix)

---

## Escalation

- **All paths terminate at Devin** (devmcgrath@gmail.com / Slack DM in `electricityoptimizer.slack.com`).
- **External help**:
  - **Stripe** (billing-side issues): `support.stripe.com` → high-priority for autonomous-agent disputes
  - **Cloudflare** (if edge layer is the cause): `dash.cloudflare.com` → support
  - **Render** (if origin is stuck): `render.com/support`
  - **Anthropic** (if the AI agent — not the auto-switcher — is making bad decisions): `support.anthropic.com`
- **Legal threshold**: If a wrongful switch caused >$100 of user harm OR the user threatens regulatory complaint, escalate to legal counsel (no current retainer; document in `docs/legal/` for future reference).

---

## Post-incident

After mitigation:

1. File a Post-Incident Review (PIR) at `docs/incidents/YYYY-MM-DD-auto-switcher-<slug>.md` using the template in `docs/runbooks/incident-response.md`.
2. Update this runbook if any step proved wrong, slow, or missing.
3. Add a regression test for the failure mode in `backend/tests/test_agent_switcher_api.py`.
4. If Mechanism 3 was used, schedule the env-var wiring (`ENABLE_AUTO_SWITCHER`) to be implemented within 7 days so a future kill-switch is faster.
5. Notify all affected users (use the comms template in `docs/runbooks/incident-response.md`).

---

## Related

- `docs/runbooks/incident-response.md` — severity definitions and SLAs
- `docs/DISASTER_RECOVERY.md` — broader recovery scenarios
- `backend/services/switch_*.py` — the 8 services implementing the agent
- `backend/migrations/066_auto_rate_switcher.sql` — schema
- `auto-rate-switcher-design.md`, `auto-rate-switcher-plan.md`, `auto-rate-switcher-research.md` — design history (will be moved to `docs/specs/` per audit P2-9)
- `.audit-2026-04-27/security.md` H-2 — context for why the silent-fallback fix was P0

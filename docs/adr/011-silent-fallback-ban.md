# ADR-011: Ban Silent `try/except` Fallbacks for Implemented Services

> **Status**: Accepted
> **Date**: 2026-04-27
> **Decision-makers**: Devin McGrath
> **Driven by**: Comprehensive audit 2026-04-27 (security H-2, code-quality P0-1)

## Context

During the launch sprint (Feb–Apr 2026) several services were stubbed before their implementation existed. Routers and webhook handlers were wrapped in defensive `try/except (ImportError, Exception)` blocks that fabricated success responses when the underlying service raised — the original intent was "the service might not be deployed yet, return something sensible."

Once those services were actually implemented, the defensive blocks did not get cleaned up. They now intercept *real* failures (DB lock, billing API outage, programming bugs) and return HTTP 200 with a fake-success payload. Concrete examples surfaced in the 2026-04-27 audit:

- `backend/api/v1/agent_switcher.py:647, 780, 870` — `except (ImportError, Exception)` returning `"status": "rolled_back"` / `"initiated"` even when `SwitchExecutionService` raised. Users see "switch succeeded" while no money moved at the utility. SOC 2 CC6 blocker.
- `backend/services/stripe_service.py::apply_webhook_action` — `if not user_id: return False` early-out that silently dropped `payment_succeeded`, `charge_refunded`, `dispute_created`. Tier never restored after dunning recovery; chargeback ops alerts never fired.
- Five recently-fixed prod bugs (commits ff94ab9..a564b5c) all share this shape.

## Decision

We will ban silent fallback `try/except` clauses for *implemented* services. Specifically:

1. **Catch only `ImportError`** for the "service not yet deployed" case.
2. **Let every other exception propagate** to FastAPI's 500 handler / Sentry.
3. **Do not write success-shaped DB updates from a fallback path** — no `executed = TRUE`, no `status = 'rolled_back'`, no audit-log entries that imply the action happened.
4. **Add a regression test for every fix** that proves the failure surfaces as a 5xx and not a fabricated 200. Pattern: mock the service to raise, assert `pytest.raises` (TestClient re-raises by default) or `response.status_code >= 500`.

## Rationale

- **Trust integrity**: a fabricated success on an autonomous money-movement endpoint is worse than a 5xx. Users can retry a 5xx; they cannot un-trust a "switch succeeded" notification.
- **Compliance**: SOC 2 CC6.1 requires that "operations are completed as authorized." Silent fallbacks make this assertion unverifiable.
- **Debuggability**: a real exception with a stack trace is debuggable. `{"status": "ok"}` with no log line is not.
- **Five prod bugs in 6 weeks** all matched this anti-pattern. The cost of the rule is trivial; the cost of breaking it is recurring incident response.

## Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Keep the broad `except` but log loudly | Logging fixes observability but doesn't fix the user-facing fabricated 200. |
| Use a sentinel value (`SERVICE_NOT_DEPLOYED`) and check at the call site | Adds a new error-handling discipline that's easy to forget. ImportError is already the language-native signal. |
| Feature-flag every service behind a kill-switch | Useful for kill-switch (see ADR-010 / `docs/runbooks/auto-rate-switcher-kill-switch.md`) but doesn't solve the silent-failure pattern. Both are needed. |

## Consequences

### Positive

- Real failures surface as 5xx with stack traces in Sentry — debuggable.
- Audit-log integrity preserved — no `executed = TRUE` rows that don't reflect reality.
- Regression coverage forces explicit handling of the "service raises" path.

### Negative / Tradeoffs

- More 5xx responses during partial outages (e.g., billing API hiccup). Acceptable: clients should retry.
- Existing code with the pattern needs sweeping (~91 bare `except Exception` in `backend/services/` and `backend/api/`). Not all are this anti-pattern, but they need triage. Tracked as a P2 cleanup line.

### Neutral

- Default-allow `except ImportError` keeps deployment-ordering flexibility for genuinely staged rollouts.

## Validation

- New tests in `backend/tests/test_agent_switcher_api.py`:
  `test_rollback_service_failure_does_not_fabricate_success`,
  `test_approve_service_failure_does_not_fabricate_success`. Both confirm a 5xx propagates rather than a fabricated 200.
- Webhook integrity tests in `backend/tests/test_webhook_payment_integrity.py` (already existed; the 2026-04-27 fix made the production code finally reach those assertions).
- Re-evaluate in 90 days (2026-07-27): confirm zero "fabricated success" prod incidents; if the pattern recurs, escalate to a lint rule (custom ruff rule or pre-commit grep).

## Related

- ADR-010: Auto Rate Switcher Architecture (the system most affected by the prior anti-pattern)
- `docs/runbooks/auto-rate-switcher-kill-switch.md` — emergency disable procedure
- `.audit-2026-04-27/security.md` H-2 — original finding
- `.audit-2026-04-27/code-quality.md` P0-1 — original finding
- `.audit-2026-04-27/CONSOLIDATED.md` — full audit context
- `~/.claude/projects/-Users-devinmcgrath-projects-electricity-optimizer/memory/audit-2026-04-27.md` — pattern memory for future Claude sessions

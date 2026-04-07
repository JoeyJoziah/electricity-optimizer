# ADR-010: Auto Rate Switcher Architecture

**Status**: Accepted
**Date**: 2026-04-03
**Decision Makers**: Devin McGrath

## Context

RateShift users in deregulated electricity markets can save money by switching suppliers, but the process requires manual research, plan comparison, and enrollment. Users often miss savings opportunities because they don't continuously monitor rates. We needed an autonomous agent that could:

- Continuously monitor available plans against the user's current plan
- Make switching decisions based on configurable thresholds
- Execute plan switches safely with rollback capability
- Maintain full audit trails for regulatory compliance

Options considered:
1. **Manual recommendations only** — notify users of savings, let them switch manually
2. **Semi-automated** — recommend and pre-fill enrollment, user clicks "confirm"
3. **Fully autonomous** — agent decides and executes switches within user-defined guardrails

## Decision

Implement a **fully autonomous switching agent** with a 7-rule decision engine, adapter pattern executors, and comprehensive safeguards.

### Architecture

**Decision Engine** (`switch_decision_engine.py`):
- 7 sequential rules evaluated per user: savings threshold (%), minimum dollar savings, cooldown period, ETF breakeven analysis, contract term check, LOA validity, tier eligibility
- Each rule produces SWITCH, HOLD, or SKIP with a reason string
- All evaluations logged to `switch_audit_log` (including no-action decisions)

**Execution Layer** (`switch_execution_service.py` + `switch_executor.py`):
- Adapter pattern: `SwitchExecutor` interface with `EnergyBotExecutor` as primary implementation
- State machine: initiating -> submitted -> accepted -> enacted (with failure/rollback branches)
- Idempotency via UUID `idempotency_key` on `switch_executions`
- Rescission window tracking for regulatory compliance

**Data Layer** (migration 066):
- `user_agent_settings` — per-user config (thresholds, cooldown, LOA status), UNIQUE on user_id
- `user_plans` — current and historical plans per user
- `available_plans` — cached marketplace plans per zip/utility (refreshed daily via `sync-available-plans.yml`)
- `meter_readings` — partitioned by month (RANGE partitioning on `reading_time`), 90-day retention
- `switch_audit_log` — every decision engine evaluation
- `switch_executions` — enrollment lifecycle tracking

**Safety Layer** (`switch_safeguards.py`):
- Pro tier required (enforced via `require_tier("pro")`)
- Letter of Authorization (LOA) must be signed and not revoked
- Configurable cooldown period (default 5 days between switches)
- ETF breakeven analysis (won't switch if early termination fee exceeds year-1 net savings)
- Minimum savings thresholds (default: 10% AND $10/mo)

### API Design
- 15 public endpoints at `/agent-switcher/*` (settings CRUD, plan browsing, history, manual triggers)
- 2 internal endpoints (daily scan, plan sync) triggered by GHA cron workflows
- All endpoints behind auth middleware; settings endpoints require Pro tier

### Scheduling
- `agent-switcher-scan.yml`: Daily 4am UTC — evaluates all enrolled users
- `sync-available-plans.yml`: Daily 2am UTC — refreshes available plan cache from EnergyBot
- `db-maintenance.yml`: Weekly — cleans up expired meter reading partitions

## Consequences

### Positive
- Users save money automatically without manual intervention
- Adapter pattern makes it easy to add new enrollment providers beyond EnergyBot
- Partitioned meter_readings table handles high-frequency interval data efficiently
- Full audit trail satisfies regulatory requirements in deregulated markets
- Configurable thresholds give users control over aggressiveness

### Negative
- EnergyBot dependency for enrollment execution (single provider initially)
- State machine complexity in switch_executions requires careful testing
- Partitioned tables require ongoing maintenance (monthly partition creation/cleanup)
- LOA requirement adds friction to user onboarding flow
- Meter readings at 15-minute intervals could generate significant data volume

### Risks
- EnergyBot API changes could break enrollment flow (mitigated by adapter pattern)
- Incorrect savings calculations could lead to bad switches (mitigated by audit log + rollback)
- Regulatory requirements vary by state (mitigated by deregulated-only restriction)

## Related
- Migration 066: `066_auto_rate_switcher.sql`
- Migration 065: `065_utilityapi_addon_billing.sql` (UtilityAPI billing add-on)
- ADR-004: Multi-model AI agent (agent service pattern)
- CLAUDE.md: Auto Rate Switcher section

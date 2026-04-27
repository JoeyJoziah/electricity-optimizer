# Auto Rate Switcher — Final Design Document

**Status:** APPROVED (Multi-Agent Review 2026-04-03)
**Arbiter Verdict:** Approved with 9 revisions (all incorporated below)

---

## 1. Overview

An autonomous electricity rate switching agent for RateShift that continuously monitors market rates across all deregulated US states (~17 + DC), detects savings opportunities via multiple triggers, and automatically switches Business-tier users to cheaper plans. Pro-tier users get recommend + confirm mode.

### Why
RateShift's core value prop is shifting users to lower rates. Today users must act on recommendations manually. This agent closes the loop — it acts on the user's behalf, turning RateShift from a dashboard into an autonomous money-saving service.

### Who
- **Business tier ($14.99/mo):** Full autonomy — agent switches without approval
- **Pro tier ($4.99/mo):** Recommend + confirm — agent finds savings, user approves, agent executes
- **Free tier:** No access

### Non-Goals
- Regulated state switching
- International markets
- Financial guarantees on savings
- Real-time plan monitoring (daily + event-driven is sufficient)

---

## 2. Architecture

### Option Selected: API-First Orchestrator

RateShift is the intelligence layer. Existing APIs handle data and enrollment plumbing.

```
CF Worker Cron (daily 4am UTC)
    |
    v
POST /internal/agent-switcher/scan
    |
    v
For each enrolled user:
    |
    +---> Arcadia / UtilityAPI / Bills (usage data, any source accepted)
    +---> EnergyBot API (available plans, cached per zip/utility)
    +---> Existing price-sync pipeline (market prices)
    |
    v
Decision Engine (7 rules, ML confidence)
    |
    +---> Business tier: execute via SwitchExecutor interface
    |       +---> Adapter 1: EnergyBot enrollment API
    |       +---> Adapter 2: PowerKiosk (future)
    |       +---> Fallback: degrade to advisory-only
    |
    +---> Pro tier: send recommendation via OneSignal + Resend
    |
    v
Log to switch_audit_log + track lifecycle in switch_executions
```

### Key Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | `SwitchExecutor` interface with adapter pattern | Prevents EnergyBot single point of failure (review S1) |
| 2 | Decision engine accepts any data source at varying confidence | Arcadia not required; bills/portal data work with lower confidence (review S2) |
| 3 | Idempotency key written to DB before enrollment API call | Prevents ghost switches on network failure (review C3) |
| 4 | LOA stored in encrypted S3, not DB | Legally binding docs need proper storage (review C5) |
| 5 | 90-day raw interval data retention, daily aggregates for history | Prevents meter_readings table explosion (review C1) |
| 6 | Rollback shows best alternatives when prior plan retired | No false promise of guaranteed revert (review S5) |

---

## 3. Data Layer

### Stream 1: User Meter Data (multi-source, Arcadia preferred)

```
Primary:   Arcadia Arc API (95% US coverage, 125+ utilities)
Fallback:  UtilityAPI (existing connections)
Fallback:  Bill uploads / portal scrapes (existing)
Fallback:  Manual entry

Confidence scoring:
  - 15-min interval data (Arcadia/UtilityAPI) → confidence 0.9+
  - Monthly kWh from bills                     → confidence 0.6
  - Manual entry                               → confidence 0.4
```

Storage: `meter_readings` table, partitioned by month, 90-day raw retention.
Daily aggregates rolled up to `meter_daily_aggregates` (kept indefinitely).

### Stream 2: Available Plans (EnergyBot API)

```
GET /plans?zip={zip}&utility={utility}
  → Cached in available_plans table
  → Refreshed daily per zip/utility (NOT per user)
  → ~500 API calls/day for full coverage (zip-level caching)
```

### Stream 3: Market Prices (Existing)

Existing `price-sync` CF Worker cron (every 6h) + `detect-rate-changes`.
No new integration needed — agent subscribes to these as triggers.

---

## 4. Trigger System

All triggers feed the same decision engine. No separate code paths.

| Trigger | Source | Frequency |
|---------|--------|-----------|
| Market scan | `agent-switcher-scan` cron | Daily 4am UTC |
| Price spike | Existing price-sync pipeline | Every 6h |
| Contract expiry | Contract lifecycle check | Daily (within scan) |
| Rate change | Existing detect-rate-changes | Daily |
| User-initiated | "Check Now" button | On demand |

---

## 5. Decision Engine

### Input/Output

```python
@dataclass
class SwitchDecision:
    action: Literal["switch", "recommend", "hold", "monitor"]
    reason: str                     # human-readable explanation
    current_plan: PlanDetails
    proposed_plan: PlanDetails | None
    projected_savings_monthly: Decimal
    projected_savings_annual: Decimal
    etf_cost: Decimal
    net_savings_year1: Decimal      # annual savings minus ETF
    confidence: float               # 0-1 based on data quality
    cooldown_remaining_days: int
    contract_days_remaining: int
    data_source: str                # arcadia, utilityapi, bills, manual
```

### Decision Rules (evaluated in order)

```
1. KILL SWITCH CHECK
   User disabled agent OR LOA revoked? → HOLD, stop

2. COOLDOWN CHECK
   Switch pending/enacted within cooldown window? → MONITOR
   Within rescission period of last switch? → HOLD

3. PLAN COMPARISON
   Fetch user's usage profile (last 3-6 months)
   Score every available plan against actual usage pattern
   Rank by projected monthly cost (rate_kwh + fixed charges + TOU + tiers)
   Apply confidence multiplier based on data source quality

4. SAVINGS FLOOR
   net_savings_year1 < user threshold? → HOLD
   Default threshold: $120/year ($10/month) or 10%, whichever is greater

5. ETF GUARD
   etf_cost = 0 → proceed
   net_savings_year1 (after ETF) > threshold → proceed with ETF disclosure
   net_savings_year1 (after ETF) < threshold → MONITOR until contract expires
   Contract expires within 45 days → flag "free switch window"

6. CONTRACT WINDOW
   Current contract expiring in < 45 days → BOOST priority

7. TIER GATE
   Business tier → action = "switch"
   Pro tier → action = "recommend"
```

### ML Plan-Fit Scoring

Extends existing ensemble predictor. Uses interval data to score how well each plan's rate structure matches the user's actual consumption pattern. TOU plans score higher for users who naturally consume off-peak. Degrades gracefully with monthly-only data (lower confidence).

---

## 6. Switch Execution

### SwitchExecutor Interface (Adapter Pattern)

```python
class SwitchExecutor(Protocol):
    async def check_plan_available(self, plan_id: str) -> bool: ...
    async def execute_enrollment(self, enrollment: EnrollmentRequest) -> EnrollmentResult: ...
    async def check_enrollment_status(self, enrollment_id: str) -> EnrollmentStatus: ...
    async def cancel_enrollment(self, enrollment_id: str) -> bool: ...
```

Adapters:
- `EnergyBotExecutor` — primary (13 states)
- `PowerKioskExecutor` — future second adapter
- `AdvisoryOnlyFallback` — degrades to recommendation if no executor available

### Business Tier: Autonomous Execution

```
Decision = "switch"
    |
    v
1. PRE-SWITCH VALIDATION
   - Verify LOA is current (not revoked)
   - Verify account still active via data source
   - Confirm plan still available via executor.check_plan_available()
   - Re-run savings calculation (prices may have changed since scan)
    |
    v
2. IDEMPOTENCY GUARD
   - Generate idempotency_key (UUID)
   - Write to switch_executions: status = "initiating", idempotency_key stored
   - This happens BEFORE the enrollment API call
    |
    v
3. EXECUTE ENROLLMENT
   - Call executor.execute_enrollment() with idempotency_key
   - Update status = "initiated", store enrollment_id
   - If API fails: safe to retry using same idempotency_key
    |
    v
4. TRACK LIFECYCLE
   - Poll executor.check_enrollment_status() periodically
   - States: initiating → initiated → submitted → accepted → active → failed
   - If rejected: log reason, mark "failed", alert user
    |
    v
5. POST-SWITCH
   - Update user_plans with new plan (status = "active", old = "switched_away")
   - Start rescission countdown (state-specific: TX=14d, OH=7d, PA=3d)
   - Start cooldown timer
   - Send notification (reassuring tone — see Notification Framework below)
   - Log full decision snapshot to switch_audit_log
```

### Pro Tier: Recommend + Confirm

```
Decision = "recommend"
    |
    v
1. Send notification (push + email) with deep link:
   "Great news — we found a plan that saves you ~$X/month.
    [Plan Name] — [rate] cents/kWh, [term] months
    [Approve Switch] [Dismiss] [Details]"
   Deep link → pre-filled approval screen (one tap to approve)
    |
    v
2. User clicks "Approve Switch"
   → Same execution flow as Business (steps 2-5 above)
    |
    v
3. User dismisses
   → Log dismissal, don't re-recommend same plan for 30 days
    |
    v
4. Plan expires before approval
   → Auto-show next best option (don't dead-end)
```

### Contract Lifecycle State Machine

```
ACTIVE → EXPIRING_SOON (< 45 days)
    → SWITCH_INITIATING (idempotency key written)
    → SWITCH_INITIATED (enrollment API called)
    → SWITCH_PENDING (3-5 days processing)
    → IN_RESCISSION (3-14 days state-specific)
    → COOLDOWN (user-configured, min 3 days)
    → ACTIVE (cycle restarts)

Failed paths:
    SWITCH_INITIATED → FAILED (enrollment rejected)
    Any state → ROLLED_BACK (user-initiated revert)
```

Each state transition logged with timestamp, reason, and full decision snapshot.

---

## 7. Safeguards

### 7.1 Savings Floor
- Configurable per user (default: $10/month or 10%, whichever is greater)
- Calculated against actual usage patterns, not averages
- Net of ETF: savings_annual - etf_cost must still exceed floor
- User can adjust threshold in settings (minimum $5/month)

### 7.2 State-Aware Cooldown
- Tracks switch lifecycle state, not a simple timer
- Minimum 3 days after switch ENACTED (confirmed active)
- Extended if switch still PENDING (agent waits for confirmation)
- Resets on: successful switch, failed switch (immediate retry allowed)
- Also blocks within rescission window of previous switch
- Factors in cancellation fees on new plan if switched too early

### 7.3 ETF Guard
- Reads ETF amount + contract end date from current plan
- Three modes:
  - ETF = $0 or no contract → switch anytime
  - ETF > 0 but net_savings_year1 still exceeds floor → switch with ETF disclosure
  - ETF negates savings → WAIT, auto-trigger at "free switch window" (45 days before contract end)

### 7.4 Kill Switch
- Single toggle: Settings → Auto Rate Switcher → ON/OFF
- OFF = agent stops ALL activity immediately
- Default state: OFF (user must opt-in)
- Business tier: additional "pause for X days" option

### 7.5 Audit Trail
- Every decision engine run logged (including HOLD decisions)
- Stored in: switch_audit_log table
- 1-year hot storage in Neon, archive to S3 after 1 year, 3-year total retention
- User-facing: "Agent Activity" feed showing all scan results including holds
  - Example: "April 3: Scanned 52 plans — your current plan is still the best deal"

### 7.6 Rollback
- Available for 30 days after switch enacted
- One-click from dashboard (prominent "Protected" banner with countdown)
- If prior plan still available → re-enroll via SwitchExecutor
- If prior plan retired → show best available alternatives with comparison
- Rollback counts as a new switch (triggers cooldown)
- Audit logged as rollback with reference to original switch

---

## 8. Database Schema

6 new tables → 58 + 6 = 64 public tables (migration 066).

### user_plans
```sql
CREATE TABLE IF NOT EXISTS user_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_name VARCHAR NOT NULL,
    provider_name VARCHAR NOT NULL,
    rate_kwh DECIMAL(10,6),
    fixed_charge DECIMAL(10,2),
    term_months INTEGER,
    etf_amount DECIMAL(10,2) DEFAULT 0,
    contract_start TIMESTAMP WITH TIME ZONE,
    contract_end TIMESTAMP WITH TIME ZONE,
    status VARCHAR NOT NULL DEFAULT 'active', -- active, expired, switched_away
    source VARCHAR NOT NULL, -- arcadia, manual, energybot
    raw_plan_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
```

### available_plans
```sql
CREATE TABLE IF NOT EXISTS available_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zip_code VARCHAR(10) NOT NULL,
    utility_code VARCHAR(50),
    region region_enum NOT NULL,
    plan_name VARCHAR NOT NULL,
    provider_name VARCHAR NOT NULL,
    rate_kwh DECIMAL(10,6) NOT NULL,
    fixed_charge DECIMAL(10,2) DEFAULT 0,
    term_months INTEGER,
    etf_amount DECIMAL(10,2) DEFAULT 0,
    renewable_pct INTEGER DEFAULT 0,
    plan_url VARCHAR,
    energybot_id VARCHAR,
    raw_plan_data JSONB,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    expires_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_available_plans_zip ON available_plans(zip_code, fetched_at DESC);
```

### meter_readings
```sql
CREATE TABLE IF NOT EXISTS meter_readings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    connection_id UUID REFERENCES user_connections(id),
    reading_time TIMESTAMP WITH TIME ZONE NOT NULL,
    kwh DECIMAL(10,4) NOT NULL,
    interval_minutes INTEGER NOT NULL DEFAULT 60, -- 15, 30, or 60
    source VARCHAR NOT NULL, -- arcadia, utilityapi, manual
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
) PARTITION BY RANGE (reading_time);
CREATE INDEX IF NOT EXISTS idx_meter_readings_user ON meter_readings(user_id, reading_time DESC);
-- 90-day retention policy: automated cleanup job deletes partitions older than 90 days
-- Daily aggregates rolled up before deletion
```

### switch_audit_log
```sql
CREATE TABLE IF NOT EXISTS switch_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trigger_type VARCHAR NOT NULL, -- market_scan, price_spike, contract_expiry, rate_change, manual
    decision VARCHAR NOT NULL, -- switch, recommend, hold, monitor
    reason TEXT NOT NULL,
    current_plan_id UUID REFERENCES user_plans(id),
    proposed_plan_id UUID REFERENCES available_plans(id),
    savings_monthly DECIMAL(10,2),
    savings_annual DECIMAL(10,2),
    etf_cost DECIMAL(10,2) DEFAULT 0,
    net_savings_year1 DECIMAL(10,2),
    confidence_score DECIMAL(3,2),
    data_source VARCHAR, -- arcadia, utilityapi, bills, manual
    tier VARCHAR NOT NULL, -- pro, business
    executed BOOLEAN DEFAULT FALSE,
    enrollment_id VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_switch_audit_user ON switch_audit_log(user_id, created_at DESC);
```

### switch_executions
```sql
CREATE TABLE IF NOT EXISTS switch_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    audit_log_id UUID NOT NULL REFERENCES switch_audit_log(id),
    old_plan_id UUID REFERENCES user_plans(id),
    new_plan_id UUID REFERENCES user_plans(id),
    idempotency_key UUID NOT NULL UNIQUE,
    enrollment_id VARCHAR,
    executor_type VARCHAR NOT NULL DEFAULT 'energybot', -- energybot, powerkiosk
    status VARCHAR NOT NULL DEFAULT 'initiating',
    -- initiating, initiated, submitted, accepted, active, failed, rolled_back
    initiated_at TIMESTAMP WITH TIME ZONE,
    confirmed_at TIMESTAMP WITH TIME ZONE,
    enacted_at TIMESTAMP WITH TIME ZONE,
    rescission_ends TIMESTAMP WITH TIME ZONE,
    cooldown_ends TIMESTAMP WITH TIME ZONE,
    failure_reason TEXT,
    rolled_back_from UUID REFERENCES switch_executions(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_switch_exec_user ON switch_executions(user_id, created_at DESC);
```

### user_agent_settings
```sql
CREATE TABLE IF NOT EXISTS user_agent_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    enabled BOOLEAN DEFAULT FALSE,
    savings_threshold_pct DECIMAL(5,2) DEFAULT 10.0,
    savings_threshold_min DECIMAL(10,2) DEFAULT 10.0,
    cooldown_days INTEGER DEFAULT 5,
    paused_until TIMESTAMP WITH TIME ZONE,
    loa_signed_at TIMESTAMP WITH TIME ZONE,
    loa_document_s3_key VARCHAR, -- encrypted S3, not DB storage
    loa_revoked_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
```

---

## 9. API Endpoints

### User-Facing (require_tier("pro"))
```
GET    /api/v1/agent-switcher/settings         → get agent config
PUT    /api/v1/agent-switcher/settings         → update (enable, thresholds, pause)
POST   /api/v1/agent-switcher/loa              → sign LOA
DELETE /api/v1/agent-switcher/loa              → revoke LOA (kills agent)
GET    /api/v1/agent-switcher/history          → switch executions + timeline
GET    /api/v1/agent-switcher/activity         → agent activity feed (all decisions incl. holds)
GET    /api/v1/agent-switcher/current-plan     → active plan details
POST   /api/v1/agent-switcher/check-now        → trigger on-demand scan
POST   /api/v1/agent-switcher/rollback/{id}    → rollback a switch
POST   /api/v1/agent-switcher/approve/{id}     → Pro tier: approve recommendation
```

### Internal (X-API-Key, excluded from RequestTimeoutMiddleware)
```
POST   /api/v1/internal/agent-switcher/scan         → daily market scan
POST   /api/v1/internal/agent-switcher/sync-plans    → refresh available_plans
POST   /api/v1/internal/agent-switcher/cleanup-meter-data  → 90-day retention job
```

---

## 10. Frontend

### Pages (3 new)
```
/auto-switcher                    → Main dashboard
  - Enable/disable toggle (kill switch)
  - Current plan card with contract countdown
  - Agent status (last scan, next scan, plans checked)
  - "Protected" banner with rollback countdown (after switch)
  - Agent Activity feed (all scans including holds)
  - Quick actions: Check Now, Pause, Settings
  - Pending recommendations (Pro tier, with one-tap approve deep link)

/auto-switcher/settings           → Configuration
  - Savings threshold slider (min $5/month)
  - Cooldown period setting
  - LOA management wizard (multi-step trust-building flow)
  - Kill switch toggle

/auto-switcher/history            → Switch history timeline
  - Each entry: old plan → new plan, savings, date, status
  - Status badges (active, pending, in rescission, rolled back, failed)
  - Rollback button (within 30 days, prominent)
  - Decision reasoning expandable per entry
```

### LOA Onboarding Wizard (multi-step, not a checkbox)
```
Step 1: "How Auto Switcher works" — plain language explanation
Step 2: "Your safeguards" — kill switch, rollback, savings floor, cooldown
Step 3: "Set your preferences" — threshold, cooldown before signing
Step 4: "Sign authorization" — e-signature with clear scope
Step 5: "You're protected" — confirmation with safeguard summary
```

### Sidebar
```
Existing 15 items + 1 new:
  Auto Switcher    (/auto-switcher)
  → Between "Alerts" and "Assistant" in nav
  → Badge: pending recommendation count (Pro tier)
```

### Notification Framework
```
First switch (reassuring tone):
  "Great news — we found you a better rate! You're now on [Plan]
   saving ~$X/month. You have [N] days to reverse this if you
   change your mind. [View Details]"

Recommendation (Pro tier):
  "We found a plan that saves you ~$X/month. [Plan Name] —
   [rate] cents/kWh, [term] months. [Approve Switch] [Details]"

Agent activity (trust-building):
  "Checked 52 plans today — your current plan is still the best deal."

Contract expiring:
  "Your contract with [Provider] ends in 30 days. We're watching
   for the best plan to switch you to. No action needed."
```

---

## 11. Cron Jobs (2 new)

| Job | Frequency | Mechanism | Endpoint |
|-----|-----------|-----------|----------|
| agent-switcher-scan | Daily 4am UTC | CF Worker cron or GHA | POST /internal/agent-switcher/scan |
| sync-available-plans | Daily 2am UTC | CF Worker cron or GHA | POST /internal/agent-switcher/sync-plans |
| cleanup-meter-data | Weekly Sunday 4am UTC | GHA | POST /internal/agent-switcher/cleanup-meter-data |

All use existing `retry-curl` + `notify-slack` patterns.

---

## 12. External Dependencies (new)

| Dependency | Purpose | Status | Action Required |
|------------|---------|--------|-----------------|
| Arcadia Arc API | Meter data (95% US coverage) | Not contracted | API license negotiation |
| EnergyBot API | Plan comparison + enrollment | Not contracted | B2B license + compliance review |
| Texas PUCT | Broker registration | Not started | Legal/regulatory filing |
| AWS S3 | LOA document storage | Not provisioned | Create encrypted bucket |

---

## 13. Testing Strategy

### Backend (~200 tests)
```
test_switch_decision_engine.py      → 7 decision rules, all edge cases (~50 tests)
test_switch_execution_service.py    → lifecycle state machine (~30 tests)
test_arcadia_service.py             → data sync, error handling (~25 tests)
test_energybot_service.py           → plan fetch, enrollment, polling (~25 tests)
test_safeguards.py                  → each safeguard independently (~30 tests)
test_cooldown_state_machine.py      → state transitions, timer logic (~20 tests)
test_switch_executor_adapters.py    → adapter pattern, fallback behavior (~20 tests)
```

### Frontend (~80 tests)
```
AutoSwitcherDashboard.test.tsx      → dashboard rendering, activity feed
SwitchHistory.test.tsx              → timeline, rollback, status badges
LOASigningWizard.test.tsx           → multi-step flow, validation
AgentSettings.test.tsx              → threshold slider, cooldown, kill switch
ApprovalFlow.test.tsx               → Pro tier approve/dismiss
```

### E2E (~3 specs)
```
auto-switcher-pro-flow.spec.ts     → recommend → approve → verify
auto-switcher-settings.spec.ts     → enable, configure, disable, LOA
auto-switcher-history.spec.ts      → view history, rollback flow
```

---

## 14. Assumptions

1. EnergyBot API supports idempotency keys for enrollment (verify during integration)
2. EnergyBot rate limits are manageable with zip-level plan caching (~500 calls/day)
3. Arcadia OAuth flow is similar to UtilityAPI (user authorizes via utility login)
4. Texas PUCT broker registration is achievable within 3-4 months
5. AI-driven autonomous switching does not trigger additional regulatory scrutiny beyond standard broker rules
6. S3 bucket can be provisioned on free/low-cost tier for LOA storage
7. Neon free tier handles 6 new tables + partitioned meter data with 90-day retention

---

## 15. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Regulatory rejection of AI broker model | High | Legal counsel review; design includes "compliance mode" for per-switch confirmation |
| EnergyBot API unavailable/deprecated | High | SwitchExecutor adapter pattern; degrade to advisory-only |
| User trust failure (won't sign LOA) | Medium | Multi-step trust-building wizard; clear safeguard communication |
| UtilityAPI continued coverage shrinkage | Medium | Arcadia as primary; multi-source data support |
| Slamming allegations from providers | Medium | Airtight LOA storage; full audit trail; rescission tracking |
| Meter data storage costs at scale | Low | 90-day retention + daily aggregates; partitioned tables |

---

## 16. Open Questions (resolve before implementation)

1. EnergyBot API pricing and rate limits — need to contact sales
2. Arcadia API pricing and onboarding timeline
3. Texas PUCT broker registration timeline and requirements (legal counsel)
4. S3 bucket vs Cloudflare R2 for LOA storage (cost comparison)
5. Which deregulated states to prioritize after Texas (based on EnergyBot coverage)

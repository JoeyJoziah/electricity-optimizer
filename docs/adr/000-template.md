# ADR-NNN: [Short Title — Decision in Active Voice]

> **Status**: Proposed | Accepted | Deprecated | Superseded by [ADR-XXX](XXX-slug.md)
> **Date**: YYYY-MM-DD
> **Decision-makers**: [Name(s) or role(s)]

## Context

What problem are we solving? What constraints are we operating under?

- Constraint 1 (e.g., "free-tier hosting only")
- Constraint 2 (e.g., "must support EU traffic / GDPR")
- Constraint 3 (e.g., "single-founder team — operational complexity matters")

What forces are at play?

- Force 1 (e.g., "users expect sub-500ms p95")
- Force 2 (e.g., "Stripe webhooks can arrive out-of-order")

## Decision

The decision in 1–3 sentences, in active voice. *We will adopt X.* No hedging.

If the decision has multiple parts, list them:

1. We will use [technology / pattern / approach].
2. We will not use [rejected alternative] because [reason].
3. We will revisit this decision when [trigger condition, e.g., "scaling beyond 10k MAU"].

## Rationale

Why this decision? Reference the constraints and forces above.

- Reason 1 — anchored to a constraint or measurable property
- Reason 2 — typically the deciding tradeoff
- Reason 3 — counter-argument acknowledged

## Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Option A | Concrete reason (cost, complexity, lock-in) |
| Option B | Concrete reason |
| Status quo / do nothing | Concrete reason |

## Consequences

### Positive

- Outcome 1 (capability unlocked, risk reduced, cost saved)
- Outcome 2

### Negative / Tradeoffs

- Cost incurred (e.g., "vendor lock-in", "$X/month", "harder to test")
- Complexity added (e.g., "new failure mode", "new monitoring needed")

### Neutral

- Side-effect that is neither good nor bad (e.g., "API surface changes")

## Validation

How will we know this decision was right or wrong?

- Metric: [e.g., "p95 latency stays under 500ms"]
- Observation window: [e.g., "first 90 days post-launch"]
- Re-evaluation trigger: [e.g., "if traffic exceeds 10k MAU, reassess"]

## Related

- ADR-XXX: [related decision]
- `docs/...`: [related runbook or spec]
- External reference: [link]

---

## How to use this template

1. Copy this file to `docs/adr/NNN-short-slug.md` (use the next available number).
2. Fill in every section. Sections that don't apply: write "N/A — [why]" rather than deleting.
3. Set status to `Proposed` while drafting; flip to `Accepted` once committed and the decision has shipped.
4. **Never edit an Accepted ADR's decision content.** Supersede it with a new ADR that links back. ADRs are append-only history.
5. Keep ADRs short (1–2 pages). If you need more, link to a longer spec in `docs/specs/`.
6. Reference the ADR from any code comment that depends on the decision (`// per ADR-007 …`).

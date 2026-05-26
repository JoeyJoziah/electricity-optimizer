# ADR-012: Adopt a Vendor-Neutral `supplier_offers` Read Model for Supplier Pricing

> **Status**: Accepted
> **Date**: 2026-05-26
> **Decision-makers**: Devin McGrath

## Context

The `GET /suppliers` listing displayed `$0.00` for every supplier because there was no per-supplier pricing to show. The legacy `tariffs` data was empty and never linked to suppliers, so the UI had nothing real to render — a zero-price card is worse than no price at all, since it reads as "free electricity."

A pricing source was needed. The forces and constraints:

- **No first-party rate data**: RateShift does not operate meters and has no contract feed of obtainable, supplier-specific offers.
- **Competitor vs. vendor distinction**: The most convenient API (EnergyBot) is a competitor in the compare/switch space, not a neutral data vendor. Sourcing our core comparison data from a competitor is a strategic and contractual hazard.
- **Honesty requirement**: Per ADR-011 (silent-fallback ban), we will not fabricate values. If a price is a regional estimate rather than an obtainable offer, the API must say so.
- **Single-founder operability**: Whatever we adopt must not lock us into one source we then have to rip out across the API and frontend.

## Decision

We will introduce a vendor-neutral `supplier_offers` read model fronted by a `SupplierOfferSource` adapter layer, and source pricing through that contract instead of the legacy `tariffs` table.

1. **`supplier_offers` read model**: A normalized per-supplier offer shape (price per kWh, estimated annual cost, tariff type, green flag, enroll URL, term, cancellation fee, expiry, `pricing_source`, `is_estimate`) that the API serializes directly.
2. **`SupplierOfferSource` adapter layer**: Every pricing source — `regional_estimate` (the only one live today), and future `ct_rate_board`, `arcadia`, `energybot`, `manual` — plugs in behind the same contract. Adding or swapping a source requires **no change to the API surface or the frontend**.
3. **Honest labeling**: Each offer carries `pricing_source` and `is_estimate`. Derived regional estimates are flagged `is_estimate: true`.
4. **Recommendations gated to real offers**: `POST /suppliers/recommend` produces a recommendation **only** from real (non-estimate) offers that beat the current supplier. When only estimate offers exist, it returns `{ "recommendation": null }` (HTTP 200) — there is no actionable basis to recommend a switch.
5. **Deprecate `tariffs`**: `GET /suppliers/{id}/tariffs` is deprecated. Pricing comes from `GET /suppliers` and `POST /suppliers/recommend`.
6. **We will not source pricing from EnergyBot** at this time, because EnergyBot is a competitor, not a neutral data vendor.

## Rationale

- **No vendor lock-in** — anchored to the single-founder operability constraint. The adapter contract means today's `regional_estimate` can be replaced by a licensed feed or a rate-board scrape without touching callers.
- **Strategic neutrality** — the deciding tradeoff. We deliberately accept weaker initial data (estimates) rather than build our comparison product on a competitor's API.
- **Honesty over coverage** — `is_estimate` makes the gap between "estimate" and "obtainable offer" explicit to both the UI and the recommendation engine, consistent with ADR-011. We would rather show a labeled estimate than a fabricated firm price.
- **Recommend is ready, not blocked** — gating on `is_estimate` means the recommend endpoint ships now and silently strengthens the moment a real-offer source comes online.

## Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| EnergyBot API | EnergyBot competes in the compare/switch space — building our core comparison data on a competitor is a strategic and contractual hazard, not a neutral vendor relationship. |
| Arcadia / Genability licensed data | Real obtainable-offer data, but licensing cost and contract overhead are out of reach for a single-founder pre-revenue stage. Kept as a future `arcadia` adapter behind the same contract. |
| Per-state rate-board scraping (e.g., CT) | Most boards' ToS block automated/agent access (CT's board is ToS-blocked for Anthropic agents). Viable later as a `ct_rate_board` adapter where ToS permits; not relied on now. |
| Status quo (legacy `tariffs`) | Empty and unlinked — produced the `$0.00` bug. Doing nothing leaves the core listing broken. |

## Consequences

### Positive

- **No vendor lock-in**: any source plugs in behind `SupplierOfferSource` with zero API/frontend change.
- **Honest `is_estimate` labeling**: estimates are never presented as firm offers; satisfies ADR-011.
- **Swappable sources**: `regional_estimate` now; `ct_rate_board` / `arcadia` / `energybot` / `manual` later, additively.
- **Recommend ready**: `POST /suppliers/recommend` ships now and auto-upgrades when real offers arrive (gated on `is_estimate`).

### Negative / Tradeoffs

- **Real per-supplier data is still a gap**: today's only source is regional estimates, so recommendations frequently return `null` until a real-offer source is wired in.
- **CT rate board is ToS-blocked for Anthropic agents**: the most obvious free obtainable-offer source cannot be automated by our agents today.
- **No user ZIP**: the app does not currently collect a user ZIP code, so zip-keyed sources (which need it for accurate, address-specific offers) cannot be fully leveraged yet.

### Neutral

- API surface changes: `GET /suppliers` gains pricing fields, `POST /suppliers/recommend` is added (replacing a prior 405), and `tariffs` is deprecated.

## Validation

- **Metric**: `GET /suppliers` returns non-null `avg_price_per_kwh` (estimate-labeled) for covered regions — no more `$0.00` cards.
- **Observation window**: through the first source swap.
- **Re-evaluation trigger**: when a real (non-estimate) offer source is wired in — confirm `POST /suppliers/recommend` begins returning non-null recommendations with `is_estimate: false` offers and no API/frontend change was required to add the source.

## Related

- ADR-011: Silent-fallback ban — `is_estimate` labeling honors the same honesty principle (no fabricated firm prices)
- `docs/API_REFERENCE.md` — `GET /suppliers` pricing fields, `POST /suppliers/recommend`, deprecated `GET /suppliers/{id}/tariffs`

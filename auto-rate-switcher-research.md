# Auto Rate Switcher — Landscape Research

**Date:** 2026-04-03
**Status:** Research complete, entering design phase

## Executive Summary

No US service offers fully autonomous, AI-driven electricity plan switching across multiple deregulated states. The white space is clear.

## Existing Services

### UK Market (pioneered, mostly collapsed)
| Service | Status | Model | Lesson |
|---------|--------|-------|--------|
| Flipper | Active | £30/yr subscription | Subscription survived energy crisis |
| Switchcraft | Active | Subscription | Fee-based resilience |
| Switchd | Active | Freemium £1.99-4.99/mo | Freemium model resilient |
| Look After My Bills | **Dead** | Commission from suppliers | Commission model collapsed when switching volumes fell 73% |
| WeFlip | Dormant | Commission (GoCompare) | Commission dependency killed it |

**Key lesson:** Commission-based auto-switching is existentially fragile. Subscription wins.

### US Market (fragmented, no national autonomous service)
| Service | States | Autonomy | Price | Gap |
|---------|--------|----------|-------|-----|
| Energy Ogre | TX only | Semi-auto at renewal | $10/mo | Single state, no mid-contract |
| Power Wizard | TX only | Advisory (approve each) | Subscription | Low autonomy |
| Smart Enroll | OH, PA, MA | Fully auto | Unknown | 3 states, low awareness |
| EnergyBot/Ebie | 13 states | AI advisory | Commission | Requires approval, has dev API |
| PowerKiosk | North America | Broker tool | $20/mo | Not consumer-facing |
| Utility Rescue | Multi-state | Semi-auto at renewal | Free (commission) | Commercial focus |

### Adjacent Models (not rate switching)
| Service | Model | Focus |
|---------|-------|-------|
| Renew Home (Google Nest) | VPP demand response | Load shifting, not plan switching |
| Voltus | Commercial VPP | Demand response payments |
| Tibber (EU) | Spot price pass-through + API | Become the supplier, optimize timing |
| Amber Electric (AU) | Wholesale pass-through + SmartShift | Battery/solar optimization |

## Switching APIs Available
1. **EnergyBot API** — 13 deregulated states, programmatic enrollment, requires compliance review
2. **PowerKiosk API** — North America, broker-focused, white-label enrollment
3. **ERCOT API** — Texas grid data, ESID validation, no enrollment capability
4. **NREL/OpenEI** — Tariff structures for 3,700+ utilities (regulated, not competitive plans)
5. **RateAcuity** — Commercial tariff data, no enrollment

## Data Platforms
1. **Arcadia Arc** — 95% US utility coverage, 125+ utilities, bill + interval data (BEST coverage)
2. **Bayou Energy** — 66% US meters, fastest data retrieval (<60s), highest reliability
3. **UtilityAPI** — Coverage SHRINKING (19 utilities removed Aug 2025, ~16% of US meters)

## Regulatory Requirements
- **LOA required** in all deregulated states (Letter of Authorization)
- **Anti-slamming laws** — unauthorized switching is illegal everywhere
- **State-by-state broker licensing:**
  - Texas: PUCT broker registration (lightest)
  - Ohio: PUCO CRES certification
  - Pennsylvania: PA PUC EGS license (heavier)
  - Illinois: ICC ARES certification
  - New York: PSC ESCO eligibility (heaviest)
- **Rescission periods:** TX=14 days, OH=7 days, PA/MA=3 business days

## The White Space (What RateShift Can Build)
Nobody does all of these together:
1. Multi-state US autonomous switching (TX + OH + PA + NY + IL minimum)
2. AI/ML on actual meter data to predict optimal switch timing
3. Standing LOA + autonomous execution with full contract lifecycle
4. ETF avoidance + renewal window monitoring + cooling-off tracking
5. Combined utility data + rate comparison + switching execution in one workflow

## Strategic Recommendations
- **Data**: Arcadia (95% coverage) > Bayou (speed) > UtilityAPI (shrinking)
- **Switching**: EnergyBot API for consumer enrollment, PowerKiosk for broker flows
- **Regulatory**: Start TX (lightest), add OH/PA, defer NY (heaviest)
- **Revenue**: Subscription model ($14.99 Business) — proven resilient vs commission
- **Demand response**: Partner with Renew Home/Voltus, don't compete

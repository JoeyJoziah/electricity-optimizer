# Sprint 4: Polish & Forward-Compat — QUEUED

**Status**: QUEUED (blocked on Sprint 3 completion)
**Target**: Naming conflicts, type safety, documentation
**Estimated files**: ~20

## Workstreams (Planned)

| WS | Tasks | Focus |
|----|-------|-------|
| WS-4A-naming | S4-01..S4-04 | Export conflicts, redirect logic, validation |
| WS-4B-ux | S4-05..S4-08 | UX polish (print styles, animations, colors, env var) |
| WS-4C-cleanup | S4-09..S4-12 | Code cleanup (password check, deprecated repo, docs) |

## Task Detail

| # | Task | Source |
|---|------|--------|
| S4-01 | Rename duplicate useAppliances exports | 20-P3 |
| S4-02 | Add array support to apiClient.get params | 20-P3 |
| S4-03 | Separate onboarding vs missing-region redirect logic | 14-P3 |
| S4-04 | Add numeric validation to community solar hooks | 14-P3 |
| S4-05 | Remove useRealtimeBroadcast stub or make it throw | 14-P3 |
| S4-06 | Add print styles for cost reports | 18-P3 |
| S4-07 | Fix progress bar animations (width -> transform:scaleX) | 18-P3 |
| S4-08 | Replace hardcoded chart colors with CSS custom properties | 18-P3 |
| S4-09 | Mark NEXT_PUBLIC_APP_URL as required in production | 06-P3 |
| S4-10 | Add common password check to password.py | 19-P3 |
| S4-11 | Clean up deprecated SupplierRepository | 03-P3 |
| S4-12 | Document all cross-cutting architectural decisions | 11-P3 |

## Post-Sprint Verification

- [ ] Full backend test suite passes
- [ ] Full frontend test suite passes
- [ ] No new lint warnings introduced
- [ ] CLAUDE.md updated with new patterns
- [ ] Memory persisted to Claude Flow
- [ ] Board sync triggered (GitHub Projects)
- [ ] DSP graph rebuilt (`python3 scripts/dsp_auto_bootstrap.py`)

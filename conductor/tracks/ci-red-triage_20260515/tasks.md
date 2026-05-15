# Tasks — ci-red-triage_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth; this mirrors actionable checkboxes for conductor validator compliance.

- [x] Task 1.1: Bump pinned versions in `backend/requirements.txt` (cryptography, python-multipart, python-dotenv)
- [x] Task 1.2: Commit + push, verify CI green for pip-audit step
- [x] Task 2.1: Add SERIAL exemption for audit-log tables in validator
- [x] Task 2.2: Commit + push, verify Migration Validation **convention checks** green (job overall still red on separate apply step — see plan.md Discovered Latent Reds #5)
- [~] Task 3.1: Run `npm audit fix` in `frontend/` — HALTED, no clean fix (see plan.md Phase 3)
- [ ] Task 3.2: Commit + push, verify npm audit step green
- [x] Task 4.1: Decide canonical Python formatter — DECIDED: ruff
- [x] Task 4.2: Execute chosen option — ci.yml + Makefile swapped to ruff
- [x] Task 4.3: Commit + push, verify Backend Lint green (took 3 iterations; root cause was flake8 still running with conflicting rule set — removed)

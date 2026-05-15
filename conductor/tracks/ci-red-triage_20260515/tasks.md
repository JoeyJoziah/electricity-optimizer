# Tasks — ci-red-triage_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth; this mirrors actionable checkboxes for conductor validator compliance.

- [x] Task 1.1: Bump pinned versions in `backend/requirements.txt` (cryptography, python-multipart, python-dotenv)
- [ ] Task 1.2: Commit + push, verify CI green for pip-audit step
- [x] Task 2.1: Add SERIAL exemption for audit-log tables in validator
- [ ] Task 2.2: Commit + push, verify Migration Validation green
- [ ] Task 3.1: Run `npm audit fix` in `frontend/`
- [ ] Task 3.2: Commit + push, verify npm audit step green
- [ ] Task 4.1: Decide canonical Python formatter (HUMAN DECISION REQUIRED)
- [ ] Task 4.2: Execute chosen option (after approval)
- [ ] Task 4.3: Commit + push, verify Backend Lint green

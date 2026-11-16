// PRD Scope #8 — canonical launch load-test entrypoint.
//
// The maintained k6 script lives at `tests/load/k6/rateshift-staging.js` so that
// the runner shell wrapper (`tests/load/k6/run.sh`) and results directory stay
// colocated. This file re-exports the same scenarios under the path the
// launch PRD references so checklist verification and external runbooks
// keep working without duplicating the workload definition.
//
// Run with:
//   k6 run tests/load/k6/k6-launch.js
// or via the wrapper:
//   STAGING_KEY=<rate_limit_bypass_key> ./tests/load/k6/run.sh

export { options, default, handleSummary } from './rateshift-staging.js';

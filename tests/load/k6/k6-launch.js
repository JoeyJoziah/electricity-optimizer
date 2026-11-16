// PRD Scope #8 — canonical launch load-test entrypoint.
//
// The maintained k6 script lives at `loadtest/rateshift-staging.js` so that
// the runner shell wrapper (`loadtest/run.sh`) and results directory stay
// colocated. This file re-exports the same scenarios under the path the
// launch PRD references so checklist verification and external runbooks
// keep working without duplicating the workload definition.
//
// Run with:
//   k6 run scripts/load-test/k6-launch.js
// or via the wrapper:
//   STAGING_KEY=<rate_limit_bypass_key> ./loadtest/run.sh

export { options, default, handleSummary } from '../../loadtest/rateshift-staging.js';

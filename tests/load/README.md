# Load tests

All load and stress tests live here. Nothing in this directory runs in CI or under
`pytest`; every tool is started by hand against a target you choose.

| Path | Tool | What it does |
|------|------|--------------|
| `k6/rateshift-staging.js` | k6 | Launch profile (ramp to 300 RPS for 5 minutes) against the public API |
| `k6/run.sh` | bash + k6 | Wrapper for `rateshift-staging.js`; `--quick` runs a 30 VU smoke test; writes JSON to `results/` |
| `k6/k6-launch.js` | k6 | Thin re-export of `rateshift-staging.js`, kept for runbooks that name it |
| `k6/load_test.js` | k6 | Scenario suite selected with `--env SCENARIO=smoke|standard|spike|soak` |
| `locustfile.py` | Locust | User-behaviour load test |
| `run_load_test.sh` | bash + Locust | Wrapper for `locustfile.py`; writes HTML reports to `reports/` |
| `stress_test.py` | Python (asyncio) | Endpoint and database stress test |
| `requirements.txt` | pip | Python dependencies for the Locust and stress tests |

## Running

```bash
# k6 smoke test (set STAGING_KEY to the rate-limit bypass key to avoid 429s)
STAGING_KEY=<key> BASE_URL=<target> ./tests/load/k6/run.sh --quick

# k6 scenario suite
k6 run --env SCENARIO=smoke --env BASE_URL=http://localhost:8000 tests/load/k6/load_test.js

# Locust
pip install -r tests/load/requirements.txt
cd tests/load && ./run_load_test.sh quick
```

`results/` is git-ignored. Do not point these at production without agreeing a window first.

More detail: `docs/LOAD_TESTING.md` (k6 scenarios) and `docs/runbooks/load-test.md` (launch run).

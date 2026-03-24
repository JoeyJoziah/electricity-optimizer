# Audit Report: Config & Secrets
## Date: 2026-03-17

---

### Executive Summary

Files audited: 12 (`.env`, `backend/.env`, `.env.example`, `.env.test`, `backend/.env.example`,
`frontend/.env.example`, `frontend/.env.local`, `.gitignore`, `.gitleaks.toml`,
`backend/config/secrets.py`, `backend/config/settings.py`, `backend/config/database.py`)

The project has a solid secrets management foundation: `.gitignore` correctly excludes all `.env*`
files (except `.example` variants), `render.yaml` uses `sync: false` for every secret,
`settings.py` enforces production-grade validators for all critical fields, and the 1Password
`SecretsManager` class provides a clean abstraction. No hardcoded live credentials were found in
any currently-tracked source file.

However, two issues require immediate attention before the repo can be considered clean. The
**`backend/.env` file contains live production credentials** (a real Upstash Redis URL with
embedded password and a real `INTERNAL_API_KEY` and `FIELD_ENCRYPTION_KEY`). Although the file is
not in the current HEAD, it was confirmed untracked rather than proven to have never appeared in
any commit — the git history must be audited to verify this. Additionally, `.env.test` and the
original `.env` were committed to git in commit `25d5732` and later removed in `4115aa4`; the
secrets in those files (test-tier only) are permanently readable from git history.

Further, the `SecretsManager` is defined and well-designed but appears to be **entirely unused at
runtime**: no non-test backend file imports it. All secrets reach the service layer via
`settings.py` / environment variables, bypassing the 1Password integration completely.

---

### Findings

---

#### P0 — Critical

**P0-1: `backend/.env` contains live credentials on disk (untracked but present)**

File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/.env`

The file is not tracked by git in `HEAD`, but it exists on disk and contains three high-value
secrets in plaintext:

```
REDIS_URL=rediss://default:AcP1AAIncDI5OThlZDNjZDkzOTU0ZDMxOGNjOWVmYmY1OTA3M2E2ZnAyNTAxNjU@holy-gull-50165.upstash.io:6379
JWT_SECRET=4827a3b06f9ef8bad2207d7beb30380916d3a9aeaffd92e1c0b0e49b25a6b1c8
INTERNAL_API_KEY=a385126d80683f30bbff026e9a95bb98243a12edf676cdde60ea145fafe60679
FIELD_ENCRYPTION_KEY=fb5ee47905695fdc11ab18d1eefdaad42968080e3c7e530b58d3573cf3fa093e
```

The Upstash URL embeds the password directly in the connection string. If this file has ever been
staged, stashed (`git stash`), or included in a worktree, these values will appear in git
internals. The `JWT_SECRET` and `INTERNAL_API_KEY` appear to match what is deployed to Render
(based on value length and format consistency with render.yaml `sync: false` entries). The
`FIELD_ENCRYPTION_KEY` is the live AES-256-GCM key used to encrypt utility account numbers in the
database — compromise of this key would allow decryption of all stored credentials.

Immediate actions:
1. Rotate all four secrets (Redis password, JWT_SECRET, INTERNAL_API_KEY, FIELD_ENCRYPTION_KEY).
   Note: rotating FIELD_ENCRYPTION_KEY requires a migration to re-encrypt all existing rows.
2. Run `git log --all --oneline -- backend/.env` and `git fsck --lost-found` to confirm whether
   the file was ever committed or stashed.
3. Delete the file: `rm backend/.env`. Developers should use `backend/.env.example` as a
   template and populate their own values from 1Password.

---

**P0-2: `.env.test` with secrets was committed to git and remains readable in history**

Commits: `25d5732` (added), `4115aa4` (removed and added to `.gitignore`).

The file was in the repository for approximately 4 days. Although the values are test-tier
placeholders (`testpassword123`, `testredis123`, `test_jwt_secret_key_change_in_production`), the
commit is permanently readable via `git show 25d5732 -- .env.test`. If any of these test values
were ever reused in staging or production (a common accidental pattern), those deployments remain
at risk.

Additionally, the current on-disk `.env.test` (not tracked) is **identical** to the deleted
version — meaning it was recreated after removal and still contains the same weak values including
`GRAFANA_PASSWORD=admin`.

Verification: `git show 25d5732 -- .env.test` — confirmed.

Actions:
1. If any test secret values were ever reused outside the test environment, rotate them.
2. Perform a BFG Repo-Cleaner or `git filter-repo` pass to expunge the committed `.env.test` from
   history if the repository has any external-facing exposure (public forks, CI artifact logs).
3. The current `.env.test` on disk should set `ENVIRONMENT=test` (not `development`) so the
   production validators in `settings.py` do not trigger on test runs.

---

#### P1 — High

**P1-1: `SecretsManager` (1Password integration) is defined but never imported or used at runtime**

Files: `backend/config/secrets.py` (defined), all other `backend/**/*.py` (not imported)

A comprehensive `get_secret()` / `require_secret()` abstraction over 1Password CLI is implemented
in `secrets.py` with 34 mapped secrets and a 1-hour TTL cache. However, `grep` across all
non-test backend Python files finds zero imports of `SecretsManager`, `get_secret`, or
`require_secret`. Every secret reaches the running process via `settings.py` loading environment
variables — the 1Password path is completely bypassed at runtime.

This means:
- In production on Render, secrets come from Render's dashboard env vars (manually entered), not
  from 1Password. If the Render secrets and the 1Password vault drift, the 1Password vault becomes
  a documentation artifact rather than the source of truth.
- The 1Password vault name hardcoded in `secrets.py` is `"Electricity Optimizer"` (line 40) while
  CLAUDE.md documents the vault as `"RateShift"`. This mismatch confirms the integration has not
  been validated against the actual vault.

Actions:
1. Either wire `SecretsManager` into the `Settings` class (e.g., as a pydantic `model_validator`
   that calls `get_secret()` for production), or document explicitly that 1Password is for
   developer reference only and Render's secret injection is the production mechanism.
2. Fix the vault name: change `OP_VAULT = "Electricity Optimizer"` to `OP_VAULT = "RateShift"`.
3. Add an integration test that runs `op whoami` and `get_secret("jwt_secret")` against the real
   vault in a CI job gated by the `OP_SERVICE_ACCOUNT_TOKEN` secret.

---

**P1-2: `SecretsManager.get_instance()` uses `@lru_cache` on a `@staticmethod` — cache cannot be cleared**

File: `backend/config/secrets.py`, lines 229-232

```python
@staticmethod
@lru_cache(maxsize=1)
def get_instance() -> "SecretsManager":
    return SecretsManager()
```

The `lru_cache` is applied to a `staticmethod`. Because `lru_cache` caches based on the arguments
passed (here: none), every call returns the same `SecretsManager` instance for the lifetime of the
process. The problem is that `lru_cache` on a `staticmethod` does not expose a `cache_clear()`
method via the normal class attribute path (`SecretsManager.get_instance.cache_clear()` will raise
`AttributeError` in Python 3.12). The existing `clear_cache()` method on the instance only clears
the in-memory secret value cache — it does not allow the `SecretsManager` itself to be
re-instantiated (e.g., to change `use_1password` at runtime or in tests). This makes unit-testing
the 1Password integration difficult without monkey-patching.

Actions:
1. Replace with a module-level singleton pattern:
   ```python
   _instance: Optional["SecretsManager"] = None
   def get_instance() -> "SecretsManager":
       global _instance
       if _instance is None:
           _instance = SecretsManager()
       return _instance
   ```
2. Expose a `reset_instance()` function for use in tests.

---

**P1-3: `JWT_SECRET` generates a random value on each cold start when env var is absent**

File: `backend/config/settings.py`, lines 59-62

```python
jwt_secret: str = Field(
    default_factory=lambda: __import__("secrets").token_hex(32),
    validation_alias="JWT_SECRET",
)
```

When `JWT_SECRET` is not set in the environment (e.g., a developer forgets to set it locally),
pydantic generates a fresh random value on each server restart. This silently invalidates all
existing user sessions and authentication tokens without any warning or error. In a Docker
container that is restarted or re-deployed, this will log out all active users.

The `validate_jwt_secret` validator only enforces strength in production (`ENVIRONMENT=production`).
In staging or development, an ephemeral JWT secret can mask authentication bugs that only appear
after restart.

Actions:
1. Change the default to a deliberate empty string and add a validator that warns loudly (or
   raises in non-development environments) when `JWT_SECRET` is absent:
   ```python
   jwt_secret: str = Field(default="", validation_alias="JWT_SECRET")
   ```
   ```python
   if not v and env != "development":
       raise ValueError("JWT_SECRET must be set in staging and production.")
   if not v:
       logger.warning("JWT_SECRET not set — generating ephemeral key. Sessions will not survive restart.")
       return __import__("secrets").token_hex(32)
   ```
2. Add `JWT_SECRET` to the staging validator path (not just `production`).

---

**P1-4: `validate_jwt_secret` blocklist does not include the actual `.env.test` value**

File: `backend/config/settings.py`, lines 241-246

```python
insecure_defaults = [
    "your-super-secret-key-change-in-production",
    "dev-local-secret-key-2026",
    "secret",
    "changeme",
]
```

The actual value in `.env.test` — `test_jwt_secret_key_change_in_production` — is not in this
blocklist. If `.env.test` were sourced against a production `ENVIRONMENT=production` deployment
(an accidental misconfiguration), the validator would pass silently because the value exceeds
32 characters in length. Similarly, `GRAFANA_PASSWORD=admin` in `.env.test` has no corresponding
validator.

Actions:
1. Add `"test_jwt_secret_key_change_in_production"` and `"generate_a_secure_random_string_at_least_32_chars"` to the `insecure_defaults` list.
2. Consider a more robust approach: require the JWT secret to be at least 64 hex characters
   (matching the output of `openssl rand -hex 32`) and reject anything that looks like a human-
   readable string in production.

---

**P1-5: `OTEL_EXPORTER_OTLP_HEADERS` (Grafana Cloud auth token) is not validated or documented in `settings.py`**

Files: `backend/.env.example` (line 126), `render.yaml` (line 80), `backend/config/settings.py`

`OTEL_EXPORTER_OTLP_HEADERS` holds the base64-encoded `instanceId:token` credential used to
authenticate to Grafana Cloud Tempo. It is consumed directly by the OTel SDK from the environment
without passing through `settings.py`. This means:
- There is no production-time validation that the header is set when `OTEL_ENABLED=true`.
- Logs at startup will not indicate whether tracing is configured correctly.
- The field is absent from `SecretsManager.SECRET_MAPPINGS` — there is no 1Password mapping for
  it, yet the 1Password vault entry "Grafana Cloud OTLP" is documented in CLAUDE.md.
- If the header value is accidentally logged (e.g., in a crash dump), the Grafana Cloud token is
  exposed.

Actions:
1. Add an `otel_otlp_headers` field to `Settings` and a `model_validator` that raises when
   `OTEL_ENABLED=true` but `OTEL_EXPORTER_OTLP_HEADERS` is empty in production.
2. Add `"otel_otlp_headers": "Grafana Cloud OTLP/headers"` to `SecretsManager.SECRET_MAPPINGS`.

---

#### P2 — Medium

**P2-1: `.gitleaks.toml` allowlist is minimal — no custom rules for project-specific token patterns**

File: `.gitleaks.toml`

The configuration only suppresses false positives from `.dsp/` path (DSP UID hashes). There are
no custom rules for project-specific token patterns (e.g., Upstash `rediss://default:` URLs,
Render API key format, Neon connection string format). The default gitleaks ruleset will catch
most generic secrets but may miss:
- Upstash connection strings with embedded passwords (the `backend/.env` Redis URL would be
  caught by `generic-api-key` rules, but the suppression path `.dsp/.*` is overly broad — a
  true secret placed in `.dsp/` would be silently ignored).
- Base64-encoded Grafana OTLP headers if they appear in code comments or config files.

Actions:
1. Add a custom `[[rules]]` entry targeting Upstash URL patterns:
   ```toml
   [[rules]]
   id = "upstash-redis-url"
   description = "Upstash Redis connection string with embedded password"
   regex = '''rediss?://[^:]+:[A-Za-z0-9+/=]{20,}@[a-z0-9-]+\.upstash\.io'''
   ```
2. Narrow the `.dsp/.*` path allowlist to only the UID map file:
   `paths = ['''.dsp/uid_map\.json''']`
3. Add a `[[rules]]` entry for Neon connection strings containing passwords.

---

**P2-2: Root `.env.example` and `backend/.env.example` are out of sync on several production vars**

Files: `.env.example`, `backend/.env.example`

The root `.env.example` includes vars that are not in `backend/.env.example` and vice versa,
creating confusion about what is actually required:

| Variable | Root `.env.example` | `backend/.env.example` | `settings.py` |
|---|---|---|---|
| `NOTION_API_KEY` | Yes (uncommented) | No | No |
| `GITHUB_TOKEN` | Yes (uncommented) | No | No |
| `GRAFANA_PASSWORD` | Yes (`change_this_secure_password`) | No | No |
| `GRAFANA_ROOT_URL` | Yes | No | No |
| `LOKI_*` (7 vars) | Yes | No | No |
| `GEMINI_API_KEY` | Commented | Commented | Yes |
| `GROQ_API_KEY` | No | Commented | Yes |
| `COMPOSIO_API_KEY` | No | Commented | Yes |
| `ENABLE_AI_AGENT` | No | Yes (`false`) | Yes |
| `UTILITYAPI_KEY` | Yes | No | Yes |
| `ALLOWED_REDIRECT_DOMAINS` | Commented | Commented | Yes |
| `GMAIL_CLIENT_ID/SECRET` | No | No | Yes |
| `OUTLOOK_CLIENT_ID/SECRET` | No | No | Yes |
| `FRONTEND_URL` | No | No | Yes (required for OAuth callbacks) |

The `LOKI_*` variables in the root `.env.example` are developer tooling config for Loki Mode and
do not belong in the application's environment template — they could confuse new contributors
into thinking these are required application settings.

Actions:
1. Consolidate to `backend/.env.example` as the single source of truth for backend config.
2. Add missing production vars to `backend/.env.example`: `GEMINI_API_KEY`, `GROQ_API_KEY`,
   `COMPOSIO_API_KEY`, `ENABLE_AI_AGENT`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`,
   `OUTLOOK_CLIENT_ID`, `OUTLOOK_CLIENT_SECRET`, `FRONTEND_URL`, `ALLOWED_REDIRECT_DOMAINS`.
3. Remove `LOKI_*` vars from the root `.env.example` (or move to a separate `.loki/.env.example`).
4. `NOTION_API_KEY`, `GITHUB_TOKEN`, `GRAFANA_PASSWORD` in the root `.env.example` are
   infrastructure/tooling vars — move them to a `docker-compose.override.yml.example` or a
   developer-setup doc.

---

**P2-3: `FIELD_ENCRYPTION_KEY` validator only enforces format in `production` — silent failure in staging**

File: `backend/config/settings.py`, lines 213-234

The `validate_field_encryption_key` validator raises only when `ENVIRONMENT=production`. In
`staging`, if `FIELD_ENCRYPTION_KEY` is absent or malformed, the service starts without encryption
enabled and all `encrypt_field()` calls will either fail at runtime or silently skip encryption
depending on how the `EncryptionService` handles a `None` key.

This creates a risk where staging data (which may be a copy of production data) is stored
unencrypted.

Actions:
1. Extend the validator to raise for both `production` and `staging` environments.
2. When the key is absent and the environment is `development`, log an explicit warning at startup:
   `"FIELD_ENCRYPTION_KEY not set — field encryption disabled. Portal credentials will not be encrypted."`

---

**P2-4: `validate_better_auth_secret` does not enforce presence (only length when present) in production**

File: `backend/config/settings.py`, lines 258-268

```python
if env == "production" and v is not None and len(v) < 32:
    raise ValueError(...)
```

`BETTER_AUTH_SECRET` is optional in settings but is required by the Better Auth library to sign
session tokens. If it is absent in production, Better Auth will either fail to initialize or use
an insecure fallback depending on the library version. The validator only checks length when a
value *is* provided — it does not enforce presence in production.

Note: `BETTER_AUTH_SECRET` is the primary user session signing key. It is more security-critical
than `JWT_SECRET` (which is used only for internal API key validation per the settings comment).

Actions:
1. Add a presence check:
   ```python
   if env == "production" and not v:
       raise ValueError("CRITICAL: BETTER_AUTH_SECRET must be set in production.")
   ```
2. Align the docstring: the comment in `backend/.env.example` correctly states this key is for
   "Signing key for session tokens" — update `settings.py` field comment to match.

---

**P2-5: `SecretsManager._get_from_1password()` logs `result.stderr` on failure — may expose partial credential data**

File: `backend/config/secrets.py`, lines 199-203

```python
logger.warning(
    "1password_read_failed",
    name=name,
    error=result.stderr,
)
```

The `op read` CLI writes error messages to stderr that can include vault path information (e.g.,
`"[ERROR] 2024/01/01 00:00:00 op://RateShift/Stripe Keys/secret_key: not found"`). If structured
logs are shipped to an external service (Grafana Loki, Sentry), this leaks the 1Password item
paths. While paths alone are not credentials, they reveal the vault structure and item naming,
aiding a targeted attack.

Actions:
1. Log only the secret `name` (already included) and a sanitized error code, not the raw stderr:
   ```python
   error_summary = result.stderr.split("\n")[0][:120] if result.stderr else "unknown"
   logger.warning("1password_read_failed", name=name, returncode=result.returncode, error_summary=error_summary)
   ```
2. Consider adding a `redact=True` structlog processor for fields named `error` that match
   `op://` URI patterns.

---

**P2-6: `backend/.env` has `DEBUG=true` for a file that contains live production credentials**

File: `backend/.env`, line 3

The file contains `DEBUG=true` alongside a live Upstash Redis URL and real API keys. If this file
is ever sourced against a production or staging `settings.py`, FastAPI's debug mode will be
active, which enables detailed tracebacks in HTTP responses that can expose environment variables,
database connection strings, and internal stack frames.

Action: Ensure local `.env` files default to `DEBUG=false`. The `backend/.env.example` correctly
defaults to `DEBUG=false`.

---

**P2-7: `render.yaml` missing several production-required env vars**

File: `render.yaml`

The following env vars are defined in `settings.py` and used in production features but are
absent from `render.yaml` (meaning they must be added manually in the Render dashboard and will
not be templated for new deployments):

- `GEMINI_API_KEY` (required when `ENABLE_AI_AGENT=true`)
- `GROQ_API_KEY` (AI agent fallback)
- `COMPOSIO_API_KEY` (AI agent tools — 1K actions/month)
- `ENABLE_AI_AGENT` (feature flag)
- `FRONTEND_URL` (OAuth callback redirect — noted as a TODO in `settings.py` line 164)
- `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` (email OAuth connection import)
- `OUTLOOK_CLIENT_ID` / `OUTLOOK_CLIENT_SECRET` (email OAuth connection import)
- `UTILITYAPI_KEY` (US smart meter data)
- `REDIS_PASSWORD` (listed separately from `REDIS_URL` in `settings.py`)

CLAUDE.md notes "42 total [Render env vars]" which exceeds the `render.yaml` count. The
discrepancy means these are set out-of-band and will be lost if the service is torn down and
re-created from `render.yaml`.

Action: Add all missing vars to `render.yaml` with `sync: false`. Treat `render.yaml` as the
complete manifest for disaster recovery — if a service must be re-provisioned, `render.yaml`
should be the only reference needed.

---

#### P3 — Low

**P3-1: `.env.example` (root) contains stale infrastructure vars from the project's pre-migration era**

File: `.env.example`

Variables `AIRFLOW_PORT=8080`, `GRAFANA_PORT=3001`, `GRAFANA_ROOT_URL`, `PROMETHEUS_PORT=9090`
reference Docker Compose infrastructure that was removed from the project. `AIRFLOW_DB_URL` and
`AIRFLOW_PORT` in `.env.test` (both on-disk and in git history) reference the Airflow setup that
was replaced by GitHub Actions and Cloudflare Workers. These orphaned entries can confuse
contributors into setting vars that are never read.

Action: Remove `AIRFLOW_*`, `GRAFANA_*`, `PROMETHEUS_PORT`, and `FRONTEND_PORT` from root
`.env.example`. These belong in a `docker-compose.env.example` if Docker Compose support is
maintained, or should be deleted.

---

**P3-2: `backend/.env.example` comment references old 1Password vault name**

File: `backend/.env.example`, line 17

```
# Retrieve from 1Password: op item get "Redis Upstash" --vault "dd"
```

The vault name `"dd"` does not match the documented vault `"RateShift"` (CLAUDE.md) or the code
`"Electricity Optimizer"` (secrets.py). All three names are in use across different files.
This creates ambiguity for any developer trying to retrieve a credential from 1Password.

Action: Standardize all references to the single vault name `"RateShift"` and update:
- `backend/.env.example` line 17 → `op item get "Redis Upstash" --vault "RateShift"`
- `backend/config/secrets.py` line 40 → `OP_VAULT = "RateShift"`

---

**P3-3: Root `.env.example` documents `DATA_RESIDENCY=EU` as default; `backend/.env.example` and `settings.py` default to `US`**

Files: `.env.example` (line 70), `backend/.env.example` (line 74), `settings.py` (line 106)

The root template sets `DATA_RESIDENCY=EU`, while the backend template and code default to `US`.
A developer using the root template for backend configuration would accidentally set EU residency,
which triggers different GDPR compliance paths than intended for the US-focused RateShift product.

Action: Align `DATA_RESIDENCY=US` across both example files and add a comment explaining the
impact of each value.

---

**P3-4: `GRAFANA_PASSWORD=admin` in `.env.test` and root `.env`**

Files: `.env.test` (line 42), root `.env` (line 42)

The on-disk `.env.test` and root `.env` files both set `GRAFANA_PASSWORD=admin`. While these are
for local development tooling, Grafana instances exposed accidentally to a network with default
credentials are a common attack vector. This value also exists in the git-committed version of
`.env.test` (commit `25d5732`).

Action: Change to a generated placeholder comment: `# GRAFANA_PASSWORD=  # Generate with: openssl rand -base64 12`

---

**P3-5: `.env.example` includes `LOKI_*` application-layer variables that are developer tooling, not app config**

File: `.env.example`, lines 152-158

```
LOKI_PROVIDER=claude
LOKI_PARALLEL=true
LOKI_AUTO_PR=true
LOKI_PROMPT_INJECTION=true
LOKI_AUDIT_ENABLED=true
LOKI_METRICS_ENABLED=true
LOKI_TELEMETRY_DISABLED=true
```

These variables configure the Loki Mode AI development assistant, not the RateShift application.
They are not referenced in `settings.py`, `backend/config/`, or any application code. Including
them in the shared `.env.example` implies they are required for the app to run and may leak
Loki Mode configuration preferences to contributors who should not need them.

Action: Move these to `.loki/.env.example` or document them in the Loki Mode section of
`CLAUDE.md` only.

---

**P3-6: `frontend/.env.local` committed with only two vars — easy to confuse with a real secrets file**

File: `frontend/.env.local`, 2 lines

```
NEXT_PUBLIC_API_URL=/api/v1
BACKEND_URL=http://localhost:8000
```

This file is gitignored but exists on disk. It contains no secrets, but its presence could
mislead a developer searching for the reason a secret env var is not being picked up — they may
not realize `frontend/.env.local` exists and is being loaded in addition to `frontend/.env.example`.
Because `.env.local` has higher priority than `.env` in Next.js, any variable set here silently
overrides the example file values.

Action: Either delete `frontend/.env.local` from disk and instruct developers to create it only
when needed, or add a comment header: `# Local overrides — do NOT commit secrets here. This file
is loaded by Next.js at higher priority than .env.example`.

---

### Statistics

| Severity | Count | Status |
|---|---|---|
| P0 — Critical | 2 | Requires immediate action |
| P1 — High | 5 | Should fix before next release |
| P2 — Medium | 7 | Address within sprint |
| P3 — Low | 6 | Backlog / housekeeping |
| **Total** | **20** | |

**Files with live secrets on disk (not in git HEAD):**
- `backend/.env` — 4 live credential values confirmed

**Files with secrets in git history (permanent):**
- `.env.test` — committed in `25d5732`, removed in `4115aa4` (test-tier values only)

**Files clean:**
- `backend/config/secrets.py` — no hardcoded credentials
- `backend/config/settings.py` — no hardcoded credentials; validators are correct
- `backend/config/database.py` — no hardcoded credentials
- `frontend/.env.local` — no secrets (2 non-sensitive vars)
- `.env.example`, `backend/.env.example`, `frontend/.env.example` — all use placeholder patterns
- `.gitignore` — correctly excludes `.env*` variants
- `render.yaml` — all secrets use `sync: false`

**Key strength**: The `settings.py` production validators are comprehensive and cover all
critical secrets (`DATABASE_URL`, `JWT_SECRET`, `INTERNAL_API_KEY`, `FIELD_ENCRYPTION_KEY`,
`STRIPE_SECRET_KEY`, `RESEND_API_KEY`). The fail-fast pattern at startup is the right approach.

**Key gap**: The `SecretsManager` / 1Password integration is well-designed but entirely unused
in production code paths. The vault name is wrong. Until this is wired up or explicitly
documented as out-of-scope, the 1Password integration provides no runtime security benefit.

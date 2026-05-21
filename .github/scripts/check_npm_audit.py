#!/usr/bin/env python3
"""Fail CI on high/critical npm advisories EXCEPT a documented allow-list.

Reads `npm audit --json` on stdin. Exits 1 if any high/critical vulnerability is
present whose top-level package is NOT in ALLOWLIST. Allow-listed advisories are
printed as warnings (visible, not silent).

ALLOWLIST — documented exceptions (review by 2026-07-01, see
conductor/tracks/ci-red-triage_20260515):
  next   : Next.js framework advisories have NO stable patch (only canary builds
           past 16.3.0-canary.5 as of 2026-05-21). `npm audit fix --force` would
           downgrade Next to 9.3.3. Accept-and-monitor for a stable patch.
  kysely : The patched 0.28.17 already resolves in node_modules via better-auth;
           only the committed package-lock pin is stale. Refresh in a deliberate
           dependency-upgrade pass rather than a churny blanket `npm audit fix`.

Any NEW vulnerable package (or these gaining a critical) still fails the build.
"""

import json
import sys

ALLOWLIST = {"next", "kysely"}


def main() -> int:
    data = json.load(sys.stdin)
    vulns = data.get("vulnerabilities", {})
    blocking, allowed = [], []
    for name, v in vulns.items():
        if v.get("severity") not in ("high", "critical"):
            continue
        (allowed if name in ALLOWLIST else blocking).append(f"{name} ({v['severity']})")

    if allowed:
        print(
            "::warning::Allow-listed high/critical advisories (documented exceptions): "
            + ", ".join(sorted(allowed))
        )
    if blocking:
        print(
            "::error::Non-allow-listed high/critical vulnerabilities found: "
            + ", ".join(sorted(blocking))
        )
        return 1
    print("npm audit: no non-allow-listed high/critical vulnerabilities.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

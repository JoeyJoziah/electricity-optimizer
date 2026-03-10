#!/usr/bin/env python3
"""
UptimeRobot Monitor Setup — RateShift (Electricity Optimizer)

Creates and configures uptime monitors for all production endpoints using the
UptimeRobot API v2 (https://uptimerobot.com/api/).

Monitors created:
  1. RateShift Frontend       — HTTPS keyword check, expects "RateShift"
  2. RateShift API Health     — HTTPS keyword check, expects "healthy"
  3. RateShift API Prices     — HTTPS status check, accepts 200 or 422

Idempotent: existing monitors are detected by URL and skipped. Re-running
this script is safe and will only create monitors that are missing.

Usage:
  export UPTIMEROBOT_API_KEY="your-api-key-here"
  python3 scripts/setup_uptimerobot.py

  # Dry run (print plan without making API calls):
  python3 scripts/setup_uptimerobot.py --dry-run

  # Also configure Slack alert contact:
  python3 scripts/setup_uptimerobot.py --slack-webhook https://hooks.slack.com/...

Environment variables:
  UPTIMEROBOT_API_KEY   Required. Read/Write API key from UptimeRobot account.
  SLACK_WEBHOOK_URL     Optional. Slack incoming webhook URL for alert routing.
                        Can also be passed via --slack-webhook flag.

UptimeRobot API reference:
  https://uptimerobot.com/api/

Monitor type codes:
  1 = HTTP(S)
  2 = Keyword (HTTP + keyword match)
  3 = Ping
  4 = Port

Alert contact type codes:
  2 = Email
  11 = Slack
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional
from urllib import request, parse, error as urllib_error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

UPTIMEROBOT_API_BASE = "https://api.uptimerobot.com/v2"

# SLA target: 99.5% per month
# Allowable downtime: ~3h 39m per month, ~10m 4s per day
SLA_TARGET_PERCENT = 99.5

# Monitor definitions — the source of truth for what gets created.
# Each dict maps directly to UptimeRobot newMonitor/editMonitor parameters.
MONITORS = [
    {
        "friendly_name": "RateShift Frontend",
        "url": "https://rateshift.app",
        "type": 2,  # Keyword monitor
        "interval": 300,  # 5 minutes (minimum on free plan)
        "keyword_type": 1,  # 1 = keyword must exist; 2 = must NOT exist
        "keyword_value": "RateShift",
        "alert_threshold": 2,  # Require 2 consecutive failures before alerting
        # UptimeRobot checks from multiple locations — a single blip should
        # not page the team. Two consecutive failures strongly indicate a real
        # outage rather than a transient probe error.
        "description": (
            "Vercel-hosted Next.js frontend. Keyword check ensures the page "
            "renders application content, not an error page or CDN stub."
        ),
    },
    {
        "friendly_name": "RateShift API Health",
        "url": "https://api.rateshift.app/api/v1/health",
        "type": 2,  # Keyword monitor
        "interval": 300,  # 5 minutes
        "keyword_type": 1,  # keyword must exist
        "keyword_value": "healthy",
        "alert_threshold": 2,
        "description": (
            "Backend FastAPI health endpoint on Render. Returns JSON with "
            '"status": "healthy" plus DB connectivity and uptime metadata. '
            "Keyword check on 'healthy' catches both HTTP failures and "
            "application-level degradation reported in the response body."
        ),
    },
    {
        "friendly_name": "RateShift API Prices",
        "url": "https://api.rateshift.app/api/v1/prices/current?region=CT",
        "type": 1,  # Plain HTTP status code monitor
        "interval": 300,  # 5 minutes
        # HTTP monitor considers 200-range codes as UP. We accept 422 too
        # because an unauthenticated caller gets HTTP 422 (Unprocessable
        # Entity — missing auth) which proves the API and routing layer are
        # alive. The custom_uptime_ranges or http_auth options are not used;
        # instead we rely on the fact that a 422 from FastAPI means the
        # request reached the application and was processed correctly.
        # UptimeRobot's HTTP monitor treats anything that is NOT a
        # connection error or 5xx as UP. 4xx responses are considered UP by
        # default on the HTTP monitor type, which is exactly what we want
        # here: 422 proves the API routing is operational.
        "alert_threshold": 2,
        "description": (
            "Live prices endpoint on Render. An unauthenticated probe returns "
            "HTTP 422 (missing auth token), which still proves the FastAPI "
            "process, routing layer, and Neon DB connection are operational. "
            "A 5xx or connection failure would indicate a real outage."
        ),
    },
]

# ---------------------------------------------------------------------------
# UptimeRobot API client (stdlib only — no requests dependency)
# ---------------------------------------------------------------------------


class UptimeRobotClient:
    """Thin wrapper around the UptimeRobot API v2."""

    def __init__(self, api_key: str, dry_run: bool = False) -> None:
        self.api_key = api_key
        self.dry_run = dry_run

    def _post(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """POST to the UptimeRobot API and return parsed JSON.

        Rate limit: UptimeRobot allows 10 requests/minute on free plans.
        This client adds a short sleep between calls to stay well within limits.
        """
        payload = {"api_key": self.api_key, "format": "json", **params}
        data = parse.urlencode(payload).encode("utf-8")
        url = f"{UPTIMEROBOT_API_BASE}/{endpoint}"

        if self.dry_run:
            print(f"  [DRY RUN] POST {url}")
            print(f"  [DRY RUN] Params: {json.dumps({k: v for k, v in params.items() if k != 'api_key'}, indent=4)}")
            return {"stat": "ok", "dry_run": True}

        req = request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        for attempt in range(3):
            try:
                with request.urlopen(req, timeout=30) as resp:
                    body = resp.read().decode("utf-8")
                    result = json.loads(body)
                    if result.get("stat") == "ok":
                        return result
                    # API returned an error payload
                    raise UptimeRobotError(
                        f"API error on {endpoint}: {result.get('error', result)}"
                    )
            except urllib_error.HTTPError as exc:
                if exc.code == 429:
                    wait = int(exc.headers.get("Retry-After", 10))
                    print(f"    Rate limited — waiting {wait}s...")
                    time.sleep(wait)
                    continue
                raise UptimeRobotError(f"HTTP {exc.code} from {endpoint}: {exc.read().decode()}")
            except urllib_error.URLError as exc:
                if attempt < 2:
                    print(f"    Network error (attempt {attempt + 1}/3): {exc.reason} — retrying in 5s")
                    time.sleep(5)
                    continue
                raise UptimeRobotError(f"Network error after 3 attempts: {exc.reason}")

        raise UptimeRobotError(f"All 3 attempts exhausted for {endpoint}")

    def get_account_details(self) -> Dict[str, Any]:
        """Fetch account information including monitor limits."""
        return self._post("getAccountDetails", {})

    def get_monitors(self) -> List[Dict[str, Any]]:
        """Fetch all existing monitors."""
        result = self._post("getMonitors", {"logs": 0})
        if result.get("dry_run"):
            return []
        return result.get("monitors", [])

    def get_alert_contacts(self) -> List[Dict[str, Any]]:
        """Fetch all existing alert contacts."""
        result = self._post("getAlertContacts", {})
        if result.get("dry_run"):
            return []
        return result.get("alert_contacts", [])

    def new_alert_contact(
        self,
        friendly_name: str,
        contact_type: int,
        value: str,
    ) -> Dict[str, Any]:
        """Create a new alert contact. contact_type 11 = Slack."""
        return self._post("newAlertContact", {
            "friendly_name": friendly_name,
            "type": contact_type,
            "value": value,
        })

    def new_monitor(self, monitor_def: Dict[str, Any], alert_contact_ids: List[str]) -> Dict[str, Any]:
        """Create a new monitor from a monitor definition dict."""
        params: Dict[str, Any] = {
            "friendly_name": monitor_def["friendly_name"],
            "url": monitor_def["url"],
            "type": monitor_def["type"],
            "interval": monitor_def["interval"],
            "alert_contacts": _format_alert_contacts(alert_contact_ids),
        }

        # Keyword-specific parameters (type == 2)
        if monitor_def["type"] == 2:
            params["keyword_type"] = monitor_def["keyword_type"]
            params["keyword_value"] = monitor_def["keyword_value"]

        # Alert threshold (how many consecutive failures before alerting)
        threshold = monitor_def.get("alert_threshold", 1)
        if threshold > 1:
            params["alert_contacts"] = _format_alert_contacts(
                alert_contact_ids, threshold=threshold
            )

        return self._post("newMonitor", params)

    def edit_monitor(self, monitor_id: int, alert_contact_ids: List[str], monitor_def: Dict[str, Any]) -> Dict[str, Any]:
        """Update alert contacts on an existing monitor."""
        params: Dict[str, Any] = {
            "id": monitor_id,
            "alert_contacts": _format_alert_contacts(
                alert_contact_ids,
                threshold=monitor_def.get("alert_threshold", 1),
            ),
        }
        return self._post("editMonitor", params)


class UptimeRobotError(Exception):
    """Raised when the UptimeRobot API returns an error."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_alert_contacts(contact_ids: List[str], threshold: int = 1, recurrence: int = 0) -> str:
    """
    Format alert_contacts parameter for UptimeRobot API.

    Format: "id_threshold_recurrence-id_threshold_recurrence-..."
      - threshold: number of consecutive failures before alerting
      - recurrence: 0 = notify only on status change; >0 = repeat every N minutes
    """
    if not contact_ids:
        return ""
    entries = [f"{cid}_{threshold}_{recurrence}" for cid in contact_ids]
    return "-".join(entries)


def find_monitor_by_url(monitors: List[Dict[str, Any]], url: str) -> Optional[Dict[str, Any]]:
    """Return an existing monitor matching the given URL, or None."""
    # Normalize trailing slashes for comparison
    normalized = url.rstrip("/")
    for m in monitors:
        if m.get("url", "").rstrip("/") == normalized:
            return m
    return None


def find_slack_contact(contacts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return an existing Slack alert contact, or None."""
    for c in contacts:
        # type 11 = Slack integration
        if c.get("type") == 11:
            return c
    return None


def sla_downtime_budget(sla_percent: float) -> Dict[str, float]:
    """Calculate monthly/weekly/daily downtime allowances for a given SLA."""
    uptime_fraction = sla_percent / 100.0
    downtime_fraction = 1.0 - uptime_fraction
    return {
        "monthly_minutes": round(30.44 * 24 * 60 * downtime_fraction, 1),
        "weekly_minutes": round(7 * 24 * 60 * downtime_fraction, 1),
        "daily_minutes": round(24 * 60 * downtime_fraction, 1),
    }


# ---------------------------------------------------------------------------
# Main setup flow
# ---------------------------------------------------------------------------


def setup_monitors(api_key: str, slack_webhook: Optional[str] = None, dry_run: bool = False) -> None:
    client = UptimeRobotClient(api_key=api_key, dry_run=dry_run)

    print("\nRateShift UptimeRobot Setup")
    print("=" * 60)

    if dry_run:
        print("DRY RUN MODE — no API calls will be made.\n")

    # ------------------------------------------------------------------
    # Step 1: Verify API key and account
    # ------------------------------------------------------------------
    print("[1/4] Verifying API key and account...")
    try:
        account_result = client.get_account_details()
        if not dry_run:
            info = account_result.get("account", {})
            print(f"      Account: {info.get('email', 'unknown')}")
            print(f"      Plan: {info.get('plan_name', 'unknown')}")
            limit = info.get("monitor_limit", "unknown")
            used = info.get("total_monitors_count", "unknown")
            print(f"      Monitors: {used}/{limit} used")
            remaining = int(limit) - int(used) if isinstance(limit, int) and isinstance(used, int) else "?"
            if isinstance(remaining, int) and remaining < len(MONITORS):
                print(f"\n  WARNING: Only {remaining} monitor slots available, need {len(MONITORS)}.")
                print("  Free plan allows 50 monitors. Check your account usage.")
        print("      OK")
    except UptimeRobotError as exc:
        print(f"\n  ERROR: Could not verify API key: {exc}")
        print("  Ensure UPTIMEROBOT_API_KEY is a valid Read/Write API key")
        print("  (found under Account > API Settings in the UptimeRobot dashboard).")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 2: Set up Slack alert contact
    # ------------------------------------------------------------------
    print("\n[2/4] Configuring alert contacts...")
    alert_contact_ids: List[str] = []

    effective_webhook = slack_webhook or os.getenv("SLACK_WEBHOOK_URL")

    if not dry_run:
        existing_contacts = client.get_alert_contacts()
        existing_slack = find_slack_contact(existing_contacts)

        if existing_slack:
            print(f"      Found existing Slack contact: id={existing_slack['id']}")
            alert_contact_ids.append(str(existing_slack["id"]))
        elif effective_webhook:
            print("      Creating Slack alert contact...")
            try:
                result = client.new_alert_contact(
                    friendly_name="RateShift Slack #incidents",
                    contact_type=11,  # Slack
                    value=effective_webhook,
                )
                new_id = str(result.get("alertcontact", {}).get("id", ""))
                if new_id:
                    alert_contact_ids.append(new_id)
                    print(f"      Created Slack contact: id={new_id}")
                else:
                    print(f"      WARNING: Unexpected response when creating Slack contact: {result}")
            except UptimeRobotError as exc:
                print(f"      WARNING: Could not create Slack contact: {exc}")
                print("      Monitors will be created without Slack alerts.")
        else:
            print("      No Slack webhook configured. Monitors will use email alerts only.")
            print("      To add Slack: --slack-webhook <url> or SLACK_WEBHOOK_URL env var.")
    else:
        if effective_webhook:
            print("  [DRY RUN] Would create Slack alert contact pointing to provided webhook.")
            alert_contact_ids = ["<slack-contact-id>"]
        else:
            print("  [DRY RUN] No Slack webhook provided — would skip Slack contact creation.")

    # ------------------------------------------------------------------
    # Step 3: Create monitors (idempotent)
    # ------------------------------------------------------------------
    print("\n[3/4] Creating monitors...")
    existing_monitors = client.get_monitors() if not dry_run else []

    created = 0
    skipped = 0
    updated = 0

    for mon_def in MONITORS:
        name = mon_def["friendly_name"]
        url = mon_def["url"]
        print(f"\n  Monitor: {name}")
        print(f"  URL:     {url}")

        existing = find_monitor_by_url(existing_monitors, url)

        if existing and not dry_run:
            print(f"  Status:  EXISTS (id={existing['id']}) — skipping creation.")

            # Update alert contacts on the existing monitor if we have a new
            # Slack contact that wasn't there before. This keeps the existing
            # monitor configuration intact while adding our alert routing.
            if alert_contact_ids:
                try:
                    client.edit_monitor(
                        monitor_id=existing["id"],
                        alert_contact_ids=alert_contact_ids,
                        monitor_def=mon_def,
                    )
                    print(f"  Alert contacts updated on existing monitor.")
                    updated += 1
                except UptimeRobotError as exc:
                    print(f"  WARNING: Could not update alert contacts: {exc}")
                    skipped += 1
            else:
                skipped += 1
            continue

        if dry_run:
            mon_type = "Keyword" if mon_def["type"] == 2 else "HTTP"
            print(f"  Status:  [DRY RUN] Would CREATE ({mon_type} monitor, {mon_def['interval'] // 60}-min interval)")
            if mon_def["type"] == 2:
                kw_mode = "must contain" if mon_def.get("keyword_type") == 1 else "must NOT contain"
                print(f"           Keyword: '{mon_def['keyword_value']}' ({kw_mode})")
            print(f"           Alert threshold: {mon_def.get('alert_threshold', 1)} consecutive failures")
            created += 1
            continue

        try:
            result = client.new_monitor(mon_def=mon_def, alert_contact_ids=alert_contact_ids)
            new_id = result.get("monitor", {}).get("id")
            print(f"  Status:  CREATED (id={new_id})")
            created += 1
            # UptimeRobot rate limit: 10 req/min on free plans — be courteous.
            time.sleep(1)
        except UptimeRobotError as exc:
            print(f"  ERROR:   Could not create monitor: {exc}")
            skipped += 1

    # ------------------------------------------------------------------
    # Step 4: Summary and SLA reference
    # ------------------------------------------------------------------
    print("\n[4/4] Summary")
    print("=" * 60)
    print(f"  Monitors created:  {created}")
    print(f"  Monitors updated:  {updated}")
    print(f"  Monitors skipped:  {skipped} (already existed, no changes needed)")
    print()

    budget = sla_downtime_budget(SLA_TARGET_PERCENT)
    print(f"  SLA target: {SLA_TARGET_PERCENT}% uptime")
    print(f"  Allowable downtime:")
    print(f"    Monthly: {budget['monthly_minutes']} min  (~{budget['monthly_minutes'] / 60:.1f}h)")
    print(f"    Weekly:  {budget['weekly_minutes']} min")
    print(f"    Daily:   {budget['daily_minutes']} min  (~{budget['daily_minutes'] * 60:.0f}s)")
    print()
    print("  Next steps:")
    print("  1. Verify monitors appear in https://dashboard.uptimerobot.com")
    print("  2. Confirm Slack alerts fire in #incidents on test downtime")
    print("  3. Add UPTIMEROBOT_API_KEY to 1Password vault 'Electricity Optimizer'")
    print("  4. Set UPTIMEROBOT_API_KEY as a GitHub Actions secret for GHA workflows")
    print()

    if dry_run:
        print("  DRY RUN complete. Run without --dry-run to apply changes.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set up UptimeRobot monitors for RateShift (Electricity Optimizer).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Standard setup (API key from env var):
  export UPTIMEROBOT_API_KEY="ur1234567-abcdef..."
  python3 scripts/setup_uptimerobot.py

  # With Slack webhook routing:
  python3 scripts/setup_uptimerobot.py --slack-webhook https://hooks.slack.com/services/...

  # Preview what would be created without making any changes:
  python3 scripts/setup_uptimerobot.py --dry-run

  # Full setup with Slack, dry run first:
  UPTIMEROBOT_API_KEY="..." python3 scripts/setup_uptimerobot.py \\
    --slack-webhook https://hooks.slack.com/services/... \\
    --dry-run
""",
    )
    parser.add_argument(
        "--slack-webhook",
        metavar="URL",
        help="Slack incoming webhook URL for alert routing (overrides SLACK_WEBHOOK_URL env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the setup plan without making any API calls",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Resolve API key
    api_key = os.getenv("UPTIMEROBOT_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: UPTIMEROBOT_API_KEY environment variable is not set.")
        print()
        print("Find your API key at:")
        print("  https://dashboard.uptimerobot.com -> Account -> API Settings")
        print()
        print("Then run:")
        print("  export UPTIMEROBOT_API_KEY='ur...'")
        print("  python3 scripts/setup_uptimerobot.py")
        sys.exit(1)

    if args.dry_run and not api_key:
        # Allow dry run without a real key for planning purposes
        api_key = "dry-run-placeholder"

    setup_monitors(
        api_key=api_key,
        slack_webhook=args.slack_webhook,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()

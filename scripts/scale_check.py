#!/usr/bin/env python3
"""
RateShift Scale Check -- Infrastructure Diagnostic

Reports current infrastructure utilization and flags scaling triggers.
Can be run manually or as a GHA cron job.

Usage:
    python3 scripts/scale_check.py
    python3 scripts/scale_check.py --json          # Machine-readable output
    python3 scripts/scale_check.py --check-render   # Include Render API checks (requires RENDER_API_KEY)

Environment Variables:
    RENDER_API_KEY       - Render API key (optional, for service metadata)
    RENDER_SERVICE_ID    - Render service ID (default: srv-d649uhur433s73d557cg)
    DATABASE_URL         - Neon PostgreSQL connection string (optional, for DB diagnostics)
    REDIS_URL            - Redis connection string (optional, for Redis diagnostics)
    BACKEND_URL          - Backend URL for health endpoint checks (default: https://api.rateshift.app)
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RENDER_SERVICE_ID = os.environ.get(
    "RENDER_SERVICE_ID", "srv-d649uhur433s73d557cg"
)
BACKEND_URL = os.environ.get(
    "BACKEND_URL", "https://api.rateshift.app"
)

# Scaling trigger thresholds (from docs/SCALING_PLAN.md)
THRESHOLDS = {
    "health_latency_warning_ms": 1000,
    "health_latency_critical_ms": 2000,
    "neon_active_hours_warn_pct": 0.80,  # 80% of plan limit
    "neon_storage_warn_pct": 0.80,       # 80% of plan limit
    "db_pool_exhaustion_errors": 0,      # any is a trigger
}

# Neon plan limits
NEON_PLANS = {
    "free": {"active_hours": 100, "storage_mb": 512, "cost": 0},
    "launch": {"active_hours": 300, "storage_mb": 10240, "cost": 19},
    "scale": {"active_hours": None, "storage_mb": 51200, "cost": 69},
}

# Render plan specs
RENDER_PLANS = {
    "free": {"ram_mb": 512, "cpu": "0.5 shared", "auto_sleep": True, "cost": 0},
    "starter": {"ram_mb": 512, "cpu": "0.5 shared", "auto_sleep": False, "cost": 7},
    "standard": {"ram_mb": 2048, "cpu": "1 dedicated", "auto_sleep": False, "cost": 25},
    "pro": {"ram_mb": 4096, "cpu": "2 dedicated", "auto_sleep": False, "cost": 85},
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScalingAlert:
    """A scaling trigger that has been activated."""
    level: str          # P0, P1, P2
    component: str      # render, neon, redis, general
    message: str
    recommendation: str


@dataclass
class DiagnosticReport:
    """Complete diagnostic report."""
    timestamp: str = ""
    backend_url: str = ""
    health_status: Optional[str] = None
    health_latency_ms: Optional[float] = None
    render_plan: Optional[str] = None
    render_auto_sleep: Optional[bool] = None
    redis_connected: Optional[bool] = None
    redis_url_configured: bool = False
    db_pool_size: int = 3
    db_max_overflow: int = 5
    db_pool_max_total: int = 8
    estimated_monthly_cost: float = 0.0
    cost_breakdown: dict = field(default_factory=dict)
    alerts: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def to_dict(self):
        result = asdict(self)
        result["alerts"] = [asdict(a) for a in self.alerts]
        return result


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------

def check_health_endpoint(report: DiagnosticReport) -> None:
    """Probe the backend health endpoint and measure latency."""
    url = f"{BACKEND_URL}/health/live"
    report.backend_url = BACKEND_URL

    try:
        start = time.monotonic()
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "scale-check/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            elapsed_ms = (time.monotonic() - start) * 1000
            body = json.loads(resp.read().decode())

            report.health_status = body.get("status", "unknown")
            report.health_latency_ms = round(elapsed_ms, 1)

            if elapsed_ms > THRESHOLDS["health_latency_critical_ms"]:
                report.alerts.append(ScalingAlert(
                    level="P0",
                    component="render",
                    message=f"Health endpoint latency {elapsed_ms:.0f}ms exceeds critical threshold ({THRESHOLDS['health_latency_critical_ms']}ms)",
                    recommendation="Upgrade Render tier or investigate backend performance. Possible cold start.",
                ))
            elif elapsed_ms > THRESHOLDS["health_latency_warning_ms"]:
                report.alerts.append(ScalingAlert(
                    level="P1",
                    component="render",
                    message=f"Health endpoint latency {elapsed_ms:.0f}ms exceeds warning threshold ({THRESHOLDS['health_latency_warning_ms']}ms)",
                    recommendation="Monitor trend. If sustained, upgrade Render tier.",
                ))
    except urllib.error.HTTPError as e:
        report.health_status = f"error ({e.code})"
        report.errors.append(f"Health check returned HTTP {e.code}")
    except urllib.error.URLError as e:
        report.health_status = "unreachable"
        report.errors.append(f"Health check failed: {e.reason}")
        report.alerts.append(ScalingAlert(
            level="P0",
            component="render",
            message="Backend is unreachable",
            recommendation="Check Render service status. May be in auto-sleep (free tier) or experiencing an outage.",
        ))
    except Exception as e:
        report.health_status = "error"
        report.errors.append(f"Health check exception: {e}")


def check_render_plan(report: DiagnosticReport) -> None:
    """Check current Render plan via API (if RENDER_API_KEY is available)."""
    api_key = os.environ.get("RENDER_API_KEY")
    if not api_key:
        report.render_plan = "unknown (RENDER_API_KEY not set)"
        return

    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            plan = data.get("plan", data.get("service", {}).get("plan", "unknown"))
            report.render_plan = plan

            plan_lower = plan.lower() if isinstance(plan, str) else "unknown"
            plan_info = RENDER_PLANS.get(plan_lower, {})
            report.render_auto_sleep = plan_info.get("auto_sleep")
            report.cost_breakdown["render"] = plan_info.get("cost", 0)

            if plan_info.get("auto_sleep"):
                report.alerts.append(ScalingAlert(
                    level="P1",
                    component="render",
                    message="Render free tier has auto-sleep enabled (15min timeout)",
                    recommendation="Upgrade to Starter ($7/mo) to eliminate cold starts. See docs/SCALING_PLAN.md.",
                ))
    except Exception as e:
        report.render_plan = f"error ({e})"
        report.errors.append(f"Render API check failed: {e}")


def check_env_config(report: DiagnosticReport) -> None:
    """Check environment variable configuration for scaling readiness."""
    # Redis
    redis_url = os.environ.get("REDIS_URL")
    report.redis_url_configured = bool(redis_url)

    if not redis_url:
        report.redis_connected = False
        report.alerts.append(ScalingAlert(
            level="P2",
            component="redis",
            message="REDIS_URL is not configured. Rate limiter uses in-memory fallback (not shared across workers).",
            recommendation="Add Upstash Redis (free tier) before scaling to multiple workers. See docs/SCALING_PLAN.md.",
        ))
    else:
        # Try to connect to Redis
        try:
            import redis
            r = redis.from_url(redis_url, socket_connect_timeout=5)
            r.ping()
            report.redis_connected = True
            r.close()
        except ImportError:
            report.redis_connected = None  # Cannot check without redis package
        except Exception as e:
            report.redis_connected = False
            report.alerts.append(ScalingAlert(
                level="P1",
                component="redis",
                message=f"Redis URL is configured but connection failed: {e}",
                recommendation="Verify REDIS_URL is correct and the Redis instance is accessible.",
            ))

    # DB pool settings
    report.db_pool_size = int(os.environ.get("DB_POOL_SIZE", "3"))
    report.db_max_overflow = int(os.environ.get("DB_MAX_OVERFLOW", "5"))
    report.db_pool_max_total = report.db_pool_size + report.db_max_overflow

    # Database URL
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        report.errors.append("DATABASE_URL is not set. DB diagnostics skipped.")


def estimate_costs(report: DiagnosticReport) -> None:
    """Estimate current monthly costs based on detected configuration."""
    costs = report.cost_breakdown

    # Render cost (from API check or infer from plan)
    if "render" not in costs:
        plan = (report.render_plan or "").lower()
        for plan_name, plan_info in RENDER_PLANS.items():
            if plan_name in plan:
                costs["render"] = plan_info["cost"]
                break
        else:
            costs["render"] = 0  # Assume free if unknown

    # Neon cost (infer from pool size as a proxy)
    if report.db_pool_max_total <= 8:
        costs["neon"] = 0  # Free tier
    elif report.db_pool_max_total <= 15:
        costs["neon"] = 19  # Launch
    else:
        costs["neon"] = 69  # Scale

    # Redis cost
    if report.redis_connected:
        costs["redis"] = 0  # Assume free tier initially
    else:
        costs["redis"] = 0

    # Monitoring (UptimeRobot free + Better Stack free)
    costs["monitoring"] = 0

    report.estimated_monthly_cost = sum(costs.values())


def check_internal_health_data(report: DiagnosticReport) -> None:
    """Optionally check the /internal/health-data endpoint for data pipeline health."""
    api_key = os.environ.get("INTERNAL_API_KEY")
    if not api_key:
        return

    url = f"{BACKEND_URL}/api/v1/internal/health-data"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "X-API-Key": api_key,
                "User-Agent": "scale-check/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            critical_tables = data.get("critical_empty_tables", [])
            if critical_tables:
                report.alerts.append(ScalingAlert(
                    level="P1",
                    component="neon",
                    message=f"Critical tables are empty: {', '.join(critical_tables)}",
                    recommendation="Data pipelines may not be running. Check cron workflows.",
                ))
    except Exception:
        pass  # Non-critical check


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_diagnostics(include_render_api: bool = False) -> DiagnosticReport:
    """Run all diagnostic checks and return the report."""
    report = DiagnosticReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    check_health_endpoint(report)
    check_env_config(report)
    if include_render_api:
        check_render_plan(report)
    check_internal_health_data(report)
    estimate_costs(report)

    return report


def print_report(report: DiagnosticReport, as_json: bool = False) -> None:
    """Print the diagnostic report in human-readable or JSON format."""
    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
        return

    print("=" * 60)
    print("  RateShift -- Infrastructure Scale Check")
    print("=" * 60)
    print(f"  Timestamp : {report.timestamp}")
    print(f"  Backend   : {report.backend_url}")
    print()

    # Health
    print("  Health Endpoint")
    print("  ---------------")
    print(f"  Status    : {report.health_status or 'not checked'}")
    latency_str = f"{report.health_latency_ms:.0f}ms" if report.health_latency_ms else "N/A"
    print(f"  Latency   : {latency_str}")
    print()

    # Infrastructure
    print("  Infrastructure")
    print("  --------------")
    print(f"  Render plan   : {report.render_plan or 'not checked (use --check-render)'}")
    if report.render_auto_sleep is not None:
        print(f"  Auto-sleep    : {'Yes (free tier)' if report.render_auto_sleep else 'No'}")
    print(f"  Redis         : {'Connected' if report.redis_connected else ('Not configured' if not report.redis_url_configured else 'Configured but not connected')}")
    print(f"  DB pool       : size={report.db_pool_size}, overflow={report.db_max_overflow}, max_total={report.db_pool_max_total}")
    print()

    # Costs
    print("  Estimated Monthly Cost")
    print("  ----------------------")
    for component, cost in report.cost_breakdown.items():
        print(f"  {component:15s}: ${cost}")
    print(f"  {'TOTAL':15s}: ${report.estimated_monthly_cost}")
    print()

    # Alerts
    if report.alerts:
        print("  Scaling Alerts")
        print("  --------------")
        for alert in report.alerts:
            marker = "!!!" if alert.level == "P0" else "!" if alert.level == "P1" else "."
            print(f"  [{alert.level}] {marker} {alert.component}: {alert.message}")
            print(f"         -> {alert.recommendation}")
            print()
    else:
        print("  No scaling alerts. Infrastructure is within thresholds.")
        print()

    # Errors
    if report.errors:
        print("  Diagnostic Errors")
        print("  -----------------")
        for error in report.errors:
            print(f"  - {error}")
        print()

    print("=" * 60)
    print("  See docs/SCALING_PLAN.md for upgrade procedures.")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="RateShift infrastructure scale diagnostics"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON (for CI/automation)",
    )
    parser.add_argument(
        "--check-render",
        action="store_true",
        help="Include Render API checks (requires RENDER_API_KEY env var)",
    )
    args = parser.parse_args()

    report = run_diagnostics(include_render_api=args.check_render)
    print_report(report, as_json=args.json)

    # Exit code: 1 if any P0 alerts, 0 otherwise
    has_p0 = any(a.level == "P0" for a in report.alerts)
    sys.exit(1 if has_p0 else 0)


if __name__ == "__main__":
    main()

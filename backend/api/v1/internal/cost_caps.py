"""
Cost-Cap Alert Endpoint

POST /api/v1/internal/cost-caps/check

Evaluates observable proxies for the four monitored services and returns
structured thresholds:

  Service    Budget cap  50%     80%     100%
  ---------  ----------  ------  ------  ------
  Resend     $20/mo      $10     $16     $20      (~50k emails on Pro plan; $0.26/1k over)
  Neon       $30/mo      $15     $24     $30      (compute-hours + storage proxy)
  CF Worker  $20/mo      $10     $16     $20      (request count proxy; free 100k/day = 3M/mo)
  Render     $7/mo       $3.50   $5.60   $7       (CPU saturation proxy; Starter is flat-rate)

Each threshold is checked against an observable metric from the live system.
Designed to be called by the `cost-cap-alerts.yml` GHA daily cron.

Threshold breach response:
  50% — Slack warning (yellow)
  80% — Slack alert (orange)  + incident-response consideration
  100% — Slack critical (red) + immediate action required

Protected by the router-level X-API-Key dependency.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session

logger = structlog.get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Budget configuration (edit these when plans change)
# ---------------------------------------------------------------------------

_BUDGETS: dict[str, dict[str, Any]] = {
    "resend": {
        "cap_usd": 20.00,
        "monthly_unit_limit": 50_000,  # emails on Resend Pro plan
        "unit_label": "emails",
        "cost_per_unit": 20.00 / 50_000,
    },
    "neon": {
        "cap_usd": 30.00,
        "monthly_unit_limit": 1919,  # compute hours on Neon Launch plan
        "unit_label": "compute-hours-proxy",
        # Proxy: assume each active connection × hour = 1 unit (rough heuristic)
        "cost_per_unit": 30.00 / 1919,
    },
    "cf_worker": {
        "cap_usd": 20.00,
        "monthly_unit_limit": 10_000_000,  # 10M requests on Workers Paid
        "unit_label": "requests",
        "cost_per_unit": 20.00 / 10_000_000,
    },
    "render": {
        "cap_usd": 7.00,
        "monthly_unit_limit": 1,  # flat-rate; proxy via uptime fraction
        "unit_label": "flat-rate",
        "cost_per_unit": 7.00,
    },
}

_THRESHOLDS = [0.50, 0.80, 1.00]


def _breached_level(fraction: float) -> str | None:
    if fraction >= 1.00:
        return "critical"
    if fraction >= 0.80:
        return "warning_high"
    if fraction >= 0.50:
        return "warning_low"
    return None


# ---------------------------------------------------------------------------
# Observable metric collectors
# ---------------------------------------------------------------------------


async def _resend_usage(db: AsyncSession) -> dict[str, Any]:
    """
    Estimate Resend usage for the current month by counting rows across the
    tables that trigger email sends: user_drip_state (welcome + drip emails)
    and notification_deliveries.

    This is a proxy, not the Resend API — it counts outbound send attempts
    from the backend, not Resend's own delivery count. Sufficient for
    threshold alerting; use the Resend dashboard for exact billing.
    """
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        text("""
            SELECT
                (SELECT COUNT(*) FROM user_drip_state WHERE welcome_sent_at >= :month_start) +
                (SELECT COUNT(*) FROM user_drip_state WHERE day2_sent_at >= :month_start) +
                (SELECT COUNT(*) FROM user_drip_state WHERE day7_sent_at >= :month_start) +
                (
                    SELECT COALESCE(COUNT(*), 0)
                    FROM notification_deliveries
                    WHERE delivered_at >= :month_start
                ) AS total_emails
        """),
        {"month_start": month_start},
    )
    row = result.fetchone()
    total = int(row[0]) if row else 0
    budget = _BUDGETS["resend"]
    fraction = total / budget["monthly_unit_limit"]
    estimated_cost = round(total * budget["cost_per_unit"], 4)
    return {
        "service": "resend",
        "metric": total,
        "unit": budget["unit_label"],
        "monthly_limit": budget["monthly_unit_limit"],
        "fraction": round(fraction, 4),
        "estimated_cost_usd": estimated_cost,
        "budget_cap_usd": budget["cap_usd"],
        "breach_level": _breached_level(fraction),
    }


async def _neon_usage(db: AsyncSession) -> dict[str, Any]:
    """
    Neon cost proxy: database size + active connections as a rough cost signal.
    Reports DB size in MB and active connection count; flags if either
    crosses heuristic thresholds (>500 MB storage or >20 active connections).
    """
    result = await db.execute(
        text("""
            SELECT
                pg_database_size(current_database()) / (1024.0 * 1024.0) AS size_mb,
                (SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active') AS active_conns
        """)
    )
    row = result.fetchone()
    size_mb = float(row[0]) if row else 0.0
    active_conns = int(row[1]) if row else 0

    # Neon free tier: 512 MB storage. Paid: more. Use 512 MB as the proxy limit.
    storage_fraction = size_mb / 512.0
    # Connection fraction: 20 active / 30 max steady-state
    conn_fraction = active_conns / 30.0
    # Take the max as the proxy breach signal
    fraction = max(storage_fraction, conn_fraction)
    estimated_cost = round((size_mb / 512.0) * _BUDGETS["neon"]["cap_usd"], 2)
    return {
        "service": "neon",
        "metric": {"size_mb": round(size_mb, 1), "active_connections": active_conns},
        "unit": "storage_mb + active_conns",
        "monthly_limit": {"storage_mb": 512, "max_active_conns": 30},
        "fraction": round(fraction, 4),
        "estimated_cost_usd": estimated_cost,
        "budget_cap_usd": _BUDGETS["neon"]["cap_usd"],
        "breach_level": _breached_level(fraction),
        "note": "Proxy metric — verify against Neon dashboard for exact billing",
    }


async def _cf_worker_usage(db: AsyncSession) -> dict[str, Any]:
    """
    CF Worker usage proxy: count gateway event records if they exist in DB,
    otherwise report as unavailable. Real usage is visible in the CF dashboard
    and via gateway-stats endpoint.

    The gateway-stats endpoint (in-Worker counters) resets per-isolate and is
    not a reliable monthly total — report that limitation clearly.
    """
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Try to count gateway requests from the observability logs table if it exists
    request_count = 0
    has_table = False
    try:
        result = await db.execute(
            text("""
                SELECT COUNT(*)
                FROM gateway_request_logs
                WHERE created_at >= :month_start
            """),
            {"month_start": month_start},
        )
        row = result.fetchone()
        request_count = int(row[0]) if row else 0
        has_table = True
    except Exception:
        has_table = False

    budget = _BUDGETS["cf_worker"]
    fraction = request_count / budget["monthly_unit_limit"] if has_table else 0.0
    estimated_cost = round(request_count * budget["cost_per_unit"], 4) if has_table else None
    return {
        "service": "cf_worker",
        "metric": request_count if has_table else "unavailable",
        "unit": budget["unit_label"],
        "monthly_limit": budget["monthly_unit_limit"],
        "fraction": round(fraction, 4),
        "estimated_cost_usd": estimated_cost,
        "budget_cap_usd": budget["cap_usd"],
        "breach_level": _breached_level(fraction) if has_table else None,
        "note": "Verify against CF dashboard — gateway_request_logs table "
        + ("found" if has_table else "not found; metric unavailable"),
    }


async def _render_usage(db: AsyncSession) -> dict[str, Any]:
    """
    Render cost proxy: flat-rate Starter is $7/mo regardless of usage.
    Monitor CPU saturation via response time percentiles in gateway logs.
    Reports fraction of the month elapsed (billing is time-based).
    """
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    fraction_elapsed = (now - month_start).total_seconds() / (
        next_month - month_start
    ).total_seconds()
    estimated_cost = round(fraction_elapsed * _BUDGETS["render"]["cap_usd"], 2)
    return {
        "service": "render",
        "metric": round(fraction_elapsed, 4),
        "unit": "fraction_of_billing_month_elapsed",
        "monthly_limit": 1.0,
        "fraction": round(fraction_elapsed, 4),
        "estimated_cost_usd": estimated_cost,
        "budget_cap_usd": _BUDGETS["render"]["cap_usd"],
        "breach_level": None,  # flat-rate — no breach possible, just monitor
        "note": "Flat-rate $7/mo. Monitor CPU via Render dashboard. No threshold breach on time proxy.",
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/cost-caps/check", tags=["Internal"])
async def check_cost_caps(
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Evaluate cost-cap proxies for all four monitored services and return
    structured breach levels for Slack alerting.

    Returns a list of services with their current metric, estimated cost,
    and breach_level (None | warning_low | warning_high | critical).
    """
    collectors = [
        _resend_usage,
        _neon_usage,
        _cf_worker_usage,
        _render_usage,
    ]

    results = []
    for collector in collectors:
        try:
            results.append(await collector(db))
        except Exception as exc:
            logger.warning("cost_cap_collector_error", collector=collector.__name__, error=str(exc))
            results.append(
                {
                    "service": collector.__name__.replace("_usage", ""),
                    "error": str(exc),
                    "breach_level": None,
                }
            )

    breaches = [r for r in results if r.get("breach_level")]
    logger.info(
        "cost_caps_checked",
        total_services=len(results),
        breaches=[r["service"] for r in breaches],
    )

    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "services": results,
        "breaches": [
            {
                "service": r["service"],
                "level": r["breach_level"],
                "estimated_cost_usd": r.get("estimated_cost_usd"),
                "budget_cap_usd": r.get("budget_cap_usd"),
                "fraction": r.get("fraction"),
            }
            for r in breaches
        ],
    }

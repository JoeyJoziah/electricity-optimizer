"""
Affiliate Link Service

Generates tracked affiliate URLs for supplier switch CTAs and records
click events for revenue attribution.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlparse

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Affiliate partner configuration
# In production, these would come from a config table or env vars.
AFFILIATE_PARTNERS: Dict[str, Dict[str, str]] = {
    "choose_energy": {
        "base_url": "https://www.chooseenergy.com/shop/",
        "utm_source": "rateshift",
        "utm_medium": "referral",
    },
    "energysage": {
        "base_url": "https://www.energysage.com/shop/",
        "utm_source": "rateshift",
        "utm_medium": "referral",
    },
}


class AffiliateService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def generate_affiliate_url(
        self,
        supplier_name: str,
        utility_type: str,
        region: str,
        partner: str = "choose_energy",
    ) -> Optional[str]:
        """Generate a tracked affiliate URL for a supplier.

        Returns None if no affiliate partner is configured for this context.
        """
        config = AFFILIATE_PARTNERS.get(partner)
        if not config:
            return None

        params = {
            "utm_source": config["utm_source"],
            "utm_medium": config["utm_medium"],
            "utm_campaign": f"{utility_type}_{region}".lower(),
            "utm_content": supplier_name.lower().replace(" ", "_"),
        }
        return f"{config['base_url']}?{urlencode(params)}"

    async def record_click(
        self,
        user_id: Optional[str],
        supplier_id: Optional[str],
        supplier_name: str,
        utility_type: str,
        region: str,
        source_page: str,
        affiliate_url: str,
    ) -> str:
        """Record an affiliate click event. Returns the click ID."""
        click_id = str(uuid.uuid4())
        await self.db.execute(
            text("""
                INSERT INTO affiliate_clicks
                    (id, user_id, supplier_id, supplier_name, utility_type,
                     region, source_page, affiliate_url)
                VALUES
                    (:id, :user_id, :supplier_id, :supplier_name, :utility_type,
                     :region, :source_page, :affiliate_url)
            """),
            {
                "id": click_id,
                "user_id": user_id,
                "supplier_id": supplier_id,
                "supplier_name": supplier_name,
                "utility_type": utility_type,
                "region": region,
                "source_page": source_page,
                "affiliate_url": affiliate_url,
            },
        )
        await self.db.commit()
        logger.info(
            "affiliate_click_recorded",
            click_id=click_id,
            supplier=supplier_name,
            utility_type=utility_type,
        )
        return click_id

    async def mark_converted(
        self,
        click_id: str,
        commission_cents: int = 0,
    ) -> bool:
        """Mark a click as converted (user actually switched)."""
        result = await self.db.execute(
            text("""
                UPDATE affiliate_clicks
                SET converted = true,
                    converted_at = NOW(),
                    commission_cents = :commission
                WHERE id = :click_id AND NOT converted
            """),
            {"click_id": click_id, "commission": commission_cents},
        )
        await self.db.commit()
        updated = result.rowcount > 0
        if updated:
            logger.info(
                "affiliate_conversion_recorded",
                click_id=click_id,
                commission_cents=commission_cents,
            )
        return updated

    async def get_revenue_summary(
        self,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get affiliate revenue summary for internal reporting."""
        result = await self.db.execute(
            text("""
                SELECT
                    utility_type,
                    COUNT(*) AS total_clicks,
                    COUNT(*) FILTER (WHERE converted) AS conversions,
                    COALESCE(SUM(commission_cents) FILTER (WHERE converted), 0) AS total_commission_cents
                FROM affiliate_clicks
                WHERE clicked_at >= NOW() - :days * INTERVAL '1 day'
                GROUP BY utility_type
                ORDER BY total_clicks DESC
            """),
            {"days": days},
        )
        rows = result.mappings().all()
        summary = [
            {
                "utility_type": r["utility_type"],
                "total_clicks": r["total_clicks"],
                "conversions": r["conversions"],
                "conversion_rate": round(r["conversions"] / max(r["total_clicks"], 1) * 100, 1),
                "total_commission_cents": r["total_commission_cents"],
            }
            for r in rows
        ]
        return {
            "period_days": days,
            "by_utility": summary,
            "total_clicks": sum(s["total_clicks"] for s in summary),
            "total_conversions": sum(s["conversions"] for s in summary),
            "total_revenue_cents": sum(s["total_commission_cents"] for s in summary),
        }

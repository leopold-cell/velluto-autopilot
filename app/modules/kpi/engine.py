"""
KPI Engine — aggregates metrics from all sources into a unified snapshot.
Runs hourly + on-demand. Stores results in kpi_snapshots table.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.kpi import KpiSnapshot

log = structlog.get_logger()


class KpiEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def capture_snapshot(self, period: str = "day") -> KpiSnapshot:
        today = datetime.now(timezone.utc).date()
        raw = await self._collect_all()

        snap = KpiSnapshot(
            snapshot_date=today,
            period=period,
            # Sales
            orders_count=raw["shopify"]["order_count"],
            orders_target=settings.daily_sales_target,
            revenue_eur=raw["shopify"]["revenue_eur"],
            aov_eur=raw["shopify"]["aov_eur"],
            # Meta
            ad_spend_eur=raw["meta"]["spend"],
            ad_roas=raw["meta"]["roas"],
            ad_cpa_eur=raw["meta"]["cpa"],
            ad_ctr_pct=raw["meta"]["ctr"],
            ad_impressions=raw["meta"]["impressions"],
            # GSC
            organic_clicks=raw["gsc"]["clicks"],
            avg_position=raw["gsc"]["avg_position"],
            # Shopify sessions (from clarity)
            sessions=raw["clarity"]["sessions"],
            conversion_rate_pct=raw["clarity"]["conversion_rate"],
            cart_abandonment_rate_pct=raw["clarity"]["cart_abandonment"],
            # Email
            email_revenue_eur=raw["email"]["revenue"],
            email_open_rate_pct=raw["email"]["open_rate"],
            raw=raw,
        )
        self.db.add(snap)
        await self.db.commit()
        await self.db.refresh(snap)
        log.info("kpi.snapshot_captured", orders=snap.orders_count, revenue=snap.revenue_eur)
        return snap

    async def get_dashboard(self) -> dict[str, Any]:
        today = datetime.now(timezone.utc).date()
        result = await self.db.execute(
            select(KpiSnapshot)
            .where(KpiSnapshot.snapshot_date == today, KpiSnapshot.period == "day")
            .order_by(KpiSnapshot.captured_at.desc())
            .limit(1)
        )
        snap = result.scalar_one_or_none()

        if not snap:
            snap = await self.capture_snapshot()

        gap = snap.orders_target - snap.orders_count
        pacing_pct = (snap.orders_count / snap.orders_target * 100) if snap.orders_target else 0

        return {
            "date": today.isoformat(),
            "sales": {
                "orders_today": snap.orders_count,
                "target": snap.orders_target,
                "gap": gap,
                "pacing_pct": round(pacing_pct, 1),
                "revenue_eur": snap.revenue_eur,
                "aov_eur": snap.aov_eur,
            },
            "meta_ads": {
                "spend_eur": snap.ad_spend_eur,
                "roas": snap.ad_roas,
                "cpa_eur": snap.ad_cpa_eur,
                "ctr_pct": snap.ad_ctr_pct,
                "atc_count": snap.raw.get("meta", {}).get("atc_count", 0),
                "cost_per_atc": snap.raw.get("meta", {}).get("cost_per_atc", 0.0),
            },
            "seo": {
                "organic_clicks": snap.organic_clicks,
                "avg_position": snap.avg_position,
            },
            "cro": {
                "sessions": snap.sessions,
                "conversion_rate_pct": snap.conversion_rate_pct,
                "cart_abandonment_pct": snap.cart_abandonment_rate_pct,
            },
            "email": {
                "revenue_eur": snap.email_revenue_eur,
                "open_rate_pct": snap.email_open_rate_pct,
            },
            "captured_at": snap.captured_at.isoformat(),
        }

    async def get_trend(self, days: int = 7) -> list[dict]:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
        result = await self.db.execute(
            select(KpiSnapshot)
            .where(KpiSnapshot.snapshot_date >= cutoff, KpiSnapshot.period == "day")
            .order_by(KpiSnapshot.snapshot_date.asc())
        )
        snaps = result.scalars().all()
        return [
            {
                "date": s.snapshot_date.isoformat(),
                "orders": s.orders_count,
                "revenue_eur": s.revenue_eur,
                "roas": s.ad_roas,
                "spend_eur": s.ad_spend_eur,
            }
            for s in snaps
        ]

    async def _collect_all(self) -> dict[str, Any]:
        shopify_data = await self._fetch_shopify()
        meta_data = await self._fetch_meta()
        gsc_data = await self._fetch_gsc()
        clarity_data = await self._fetch_clarity()
        email_data = await self._fetch_email()

        return {
            "shopify": shopify_data,
            "meta": meta_data,
            "gsc": gsc_data,
            "clarity": clarity_data,
            "email": email_data,
        }

    async def _fetch_shopify(self) -> dict:
        try:
            from app.modules.shopify.tools import shopify_get_orders
            return await shopify_get_orders(days=1)
        except Exception as e:
            log.warning("kpi.shopify_fetch_failed", error=str(e))
            return {"order_count": 0, "revenue_eur": 0.0, "aov_eur": 0.0}

    async def _fetch_meta(self) -> dict:
        try:
            from app.modules.meta_ads.client import MetaAdsClient
            client = MetaAdsClient()
            insights = await client.get_account_insights(date_preset="today")
            roas_list = insights.get("purchase_roas", [])
            roas = float(roas_list[0].get("value", 0)) if roas_list else 0.0
            cpa = 0.0
            for item in insights.get("cost_per_action_type", []):
                if item.get("action_type") == "purchase":
                    cpa = float(item.get("value", 0))
            atc = client.extract_atc_metrics(insights)
            return {
                "spend": float(insights.get("spend", 0)),
                "roas": roas,
                "cpa": cpa,
                "ctr": float(insights.get("ctr", 0)),
                "impressions": int(insights.get("impressions", 0)),
                "atc_count": atc["atc_count"],
                "cost_per_atc": atc["cost_per_atc"],
            }
        except Exception as e:
            log.warning("kpi.meta_fetch_failed", error=str(e))
            return {"spend": 0.0, "roas": 0.0, "cpa": 0.0, "ctr": 0.0, "impressions": 0,
                    "atc_count": 0, "cost_per_atc": 0.0}

    async def _fetch_gsc(self) -> dict:
        try:
            from app.modules.gsc.client import GSCClient
            client = GSCClient()
            return await client.get_today_summary()
        except Exception as e:
            log.warning("kpi.gsc_fetch_failed", error=str(e))
            return {"clicks": 0, "impressions": 0, "avg_position": 0.0}

    async def _fetch_clarity(self) -> dict:
        try:
            from app.modules.clarity.client import ClarityClient
            client = ClarityClient()
            return await client.get_today_summary()
        except Exception as e:
            log.warning("kpi.clarity_fetch_failed", error=str(e))
            return {"sessions": 0, "conversion_rate": 0.0, "cart_abandonment": 0.0}

    async def _fetch_email(self) -> dict:
        try:
            from app.modules.email_marketing.client import EmailClient
            client = EmailClient()
            return await client.get_today_stats()
        except Exception as e:
            log.warning("kpi.email_fetch_failed", error=str(e))
            return {"revenue": 0.0, "open_rate": 0.0}

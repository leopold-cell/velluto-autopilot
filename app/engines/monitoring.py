"""
Monitoring & Alerting Engine.
Checks system health and sends urgent WhatsApp alerts for critical failures.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.kpi import KpiSnapshot

log = structlog.get_logger()

# Prometheus metrics
orchestrator_runs = Counter("velluto_orchestrator_runs_total", "Orchestrator cycle runs", ["status"])
actions_executed = Counter("velluto_actions_total", "Actions executed", ["module", "action", "status"])
approval_requests = Counter("velluto_approval_requests_total", "Approval requests", ["risk_level"])
daily_orders = Gauge("velluto_daily_orders", "Orders today")
daily_revenue = Gauge("velluto_daily_revenue_eur", "Revenue today EUR")
ad_roas = Gauge("velluto_ad_roas", "Current ROAS")
api_latency = Histogram(
    "velluto_api_latency_seconds",
    "API call latency",
    ["service"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)


ALERT_THRESHOLDS = {
    "min_daily_orders_by_hour": {
        10: 2,
        14: 4,
        18: 6,
        23: 7,
    },
    "min_roas": 1.5,
    "max_error_rate_pct": 10.0,
}


class MonitoringEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_health_checks(self) -> dict[str, Any]:
        checks = {
            "database": await self._check_db(),
            "redis": await self._check_redis(),
            "sales_pace": await self._check_sales_pace(),
            "error_rate": await self._check_error_rate(),
        }
        all_healthy = all(c["healthy"] for c in checks.values())
        return {"healthy": all_healthy, "checks": checks}

    async def _check_db(self) -> dict:
        try:
            await self.db.execute(select(func.now()))
            return {"healthy": True}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def _check_redis(self) -> dict:
        try:
            from app.redis_client import get_redis
            r = await get_redis()
            await r.ping()
            return {"healthy": True}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def _check_sales_pace(self) -> dict:
        today = datetime.now(timezone.utc).date()
        result = await self.db.execute(
            select(KpiSnapshot).where(
                KpiSnapshot.snapshot_date == today,
                KpiSnapshot.period == "day",
            ).order_by(KpiSnapshot.captured_at.desc()).limit(1)
        )
        snap = result.scalar_one_or_none()
        if not snap:
            return {"healthy": True, "note": "no_snapshot_yet"}

        hour = datetime.now(timezone.utc).hour
        from app.config import settings

        expected = 0
        for h, target in sorted(ALERT_THRESHOLDS["min_daily_orders_by_hour"].items()):
            if hour >= h:
                expected = target

        healthy = snap.orders_count >= expected
        return {
            "healthy": healthy,
            "orders_today": snap.orders_count,
            "expected_by_now": expected,
            "target": settings.daily_sales_target,
        }

    async def _check_error_rate(self) -> dict:
        from sqlalchemy import Integer, case
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        result = await self.db.execute(
            select(
                func.count().label("total"),
                func.sum(
                    case((AuditLog.status == "failure", 1), else_=0)
                ).label("failures"),
            ).where(AuditLog.created_at >= one_hour_ago)
        )
        row = result.one()
        total = row.total or 0
        failures = row.failures or 0
        error_rate = (failures / total * 100) if total > 0 else 0.0

        healthy = error_rate < ALERT_THRESHOLDS["max_error_rate_pct"]
        return {"healthy": healthy, "error_rate_pct": round(error_rate, 2), "total": total}

    async def alert_critical(self, message: str, context: dict | None = None) -> None:
        log.error("alert.critical", message=message, context=context)
        try:
            from app.modules.whatsapp.client import WhatsAppClient
            client = WhatsAppClient()
            text = f"🚨 *VELLUTO CRITICAL ALERT*\n\n{message}"
            if context:
                text += "\n\n```" + "\n".join(f"{k}: {v}" for k, v in context.items()) + "```"
            await client.send_text(text)
        except Exception as e:
            log.error("alert.whatsapp_failed", error=str(e))

    async def alert_warning(self, message: str) -> None:
        log.warning("alert.warning", message=message)
        try:
            from app.modules.whatsapp.client import WhatsAppClient
            client = WhatsAppClient()
            await client.send_text(f"⚠️ *Velluto Warning*\n{message}")
        except Exception as e:
            log.warning("alert.whatsapp_failed", error=str(e))

"""
Dashboard API — single endpoint that aggregates all data the dashboard needs.
Combines KPIs, trend, agent activity, token cost, Meta campaigns, and suggestions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit import AuditLog
from app.models.kpi import KpiSnapshot
from app.models.task import Task, TaskStatus
from app.modules.kpi.engine import KpiEngine
from app.modules.token_optimizer.optimizer import TokenOptimizer

log = structlog.get_logger()

router = APIRouter()


@router.get("")
async def dashboard_data(db: AsyncSession = Depends(get_db)):
    kpi_engine = KpiEngine(db)
    token_optimizer = TokenOptimizer()

    today_kpis, trend, agent_activity, token_report, campaigns, suggestions, alerts = (
        await _gather_kpis(kpi_engine),
        await _gather_trend(db),
        await _gather_agent_activity(db),
        await token_optimizer.get_weekly_cost_summary(),
        await _gather_campaigns(),
        await _gather_suggestions(db),
        await _gather_alerts(db),
    )

    daily_token = await token_optimizer.get_daily_report()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kpis": today_kpis,
        "trend": trend,
        "agent_activity": agent_activity,
        "token_cost": {
            "today": daily_token,
            "week": token_report,
        },
        "campaigns": campaigns,
        "suggestions": suggestions,
        "alerts": alerts,
    }


async def _gather_kpis(engine: KpiEngine) -> dict:
    try:
        return await engine.get_dashboard()
    except Exception as e:
        log.warning("dashboard.kpi_failed", error=str(e))
        return {}


async def _gather_trend(db: AsyncSession) -> list[dict]:
    try:
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=14)
        result = await db.execute(
            select(KpiSnapshot)
            .where(KpiSnapshot.snapshot_date >= cutoff, KpiSnapshot.period == "day")
            .order_by(KpiSnapshot.snapshot_date.asc())
        )
        snaps = result.scalars().all()
        return [
            {
                "date": s.snapshot_date.isoformat(),
                "orders": s.orders_count,
                "revenue_eur": float(s.revenue_eur or 0),
                "roas": float(s.ad_roas or 0),
                "spend_eur": float(s.ad_spend_eur or 0),
                "organic_clicks": s.organic_clicks or 0,
            }
            for s in snaps
        ]
    except Exception as e:
        log.warning("dashboard.trend_failed", error=str(e))
        return []


async def _gather_agent_activity(db: AsyncSession) -> list[dict]:
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await db.execute(
            select(AuditLog)
            .where(AuditLog.created_at >= cutoff)
            .order_by(AuditLog.created_at.desc())
            .limit(20)
        )
        logs = result.scalars().all()
        return [
            {
                "ts": a.created_at.isoformat(),
                "action": a.action,
                "module": a.module,
                "status": a.status,
                "dry_run": a.dry_run,
                "duration_ms": a.duration_ms,
                "tokens_used": a.tokens_used,
                "error": a.error,
            }
            for a in logs
        ]
    except Exception as e:
        log.warning("dashboard.activity_failed", error=str(e))
        return []


async def _gather_campaigns() -> list[dict]:
    try:
        from app.modules.meta_ads.client import MetaAdsClient
        client = MetaAdsClient()
        campaigns = await client.get_campaigns()
        result = []
        for c in campaigns.get("data", []):
            result.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "status": c.get("status"),
                "objective": c.get("objective"),
                "daily_budget_eur": float(c.get("daily_budget", 0)) / 100,
            })
        return result
    except Exception as e:
        log.warning("dashboard.campaigns_failed", error=str(e))
        return []


async def _gather_suggestions(db: AsyncSession) -> list[dict]:
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        result = await db.execute(
            select(AuditLog)
            .where(
                AuditLog.created_at >= cutoff,
                AuditLog.action == "generate_suggestions",
                AuditLog.status == "success",
            )
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        log_entry = result.scalar_one_or_none()
        if log_entry and log_entry.output_data:
            suggestions = log_entry.output_data.get("suggestions", [])
            return suggestions if isinstance(suggestions, list) else []
        return []
    except Exception as e:
        log.warning("dashboard.suggestions_failed", error=str(e))
        return []


async def _gather_alerts(db: AsyncSession) -> list[dict]:
    alerts = []
    try:
        today = datetime.now(timezone.utc).date()
        result = await db.execute(
            select(KpiSnapshot)
            .where(KpiSnapshot.snapshot_date == today, KpiSnapshot.period == "day")
            .order_by(KpiSnapshot.captured_at.desc())
            .limit(1)
        )
        snap = result.scalar_one_or_none()
        if snap:
            if (snap.ad_spend_eur or 0) > 5 and (snap.ad_roas or 0) == 0:
                alerts.append({
                    "level": "critical",
                    "message": f"€{snap.ad_spend_eur:.2f} spent today with 0x ROAS — pixel tracking may be broken",
                })
            if snap.orders_count == 0 and (snap.ad_spend_eur or 0) > 0:
                alerts.append({
                    "level": "warning",
                    "message": "Zero orders recorded despite active ad spend",
                })
            if snap.ad_ctr_pct and snap.ad_ctr_pct < 0.5:
                alerts.append({
                    "level": "warning",
                    "message": f"Low ad CTR ({snap.ad_ctr_pct:.2f}%) — consider refreshing creatives",
                })
    except Exception as e:
        log.warning("dashboard.alerts_failed", error=str(e))

    return alerts

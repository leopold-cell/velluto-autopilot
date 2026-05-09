"""
System Optimizer — analyzes orchestrator efficiency over time.
Recommends which actions are high-value, which are wasted tokens.
Reduces prompt size for low-variance cycles.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.task import Task, TaskStatus

log = structlog.get_logger()


class SystemOptimizer:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_efficiency_report(self, days: int = 7) -> dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Task stats
        task_result = await self.db.execute(
            select(
                func.count(Task.id).label("total_tasks"),
                func.avg(Task.total_tokens).label("avg_tokens"),
                func.sum(Task.actions_executed).label("total_actions"),
                func.sum(Task.actions_pending).label("total_pending"),
            ).where(Task.created_at >= cutoff, Task.status == TaskStatus.completed)
        )
        task_stats = task_result.one()

        # Top actions by frequency
        action_result = await self.db.execute(
            select(AuditLog.action, func.count(AuditLog.id).label("count"))
            .where(AuditLog.created_at >= cutoff)
            .group_by(AuditLog.action)
            .order_by(func.count(AuditLog.id).desc())
            .limit(10)
        )
        top_actions = [{"action": r.action, "count": r.count} for r in action_result]

        # Error rate by module
        from sqlalchemy import case
        error_result = await self.db.execute(
            select(
                AuditLog.module,
                func.count(AuditLog.id).label("total"),
                func.sum(
                    case((AuditLog.status == "failure", 1), else_=0)
                ).label("failures"),
            )
            .where(AuditLog.created_at >= cutoff)
            .group_by(AuditLog.module)
        )
        module_errors = [
            {
                "module": r.module,
                "total": r.total,
                "failures": r.failures or 0,
                "error_rate_pct": round((r.failures or 0) / r.total * 100, 1) if r.total else 0,
            }
            for r in error_result
        ]

        from app.modules.token_optimizer.optimizer import TokenOptimizer
        token_report = await TokenOptimizer().get_weekly_cost_summary()

        return {
            "period_days": days,
            "tasks": {
                "total": task_stats.total_tasks or 0,
                "avg_tokens_per_cycle": round(float(task_stats.avg_tokens or 0), 0),
                "total_actions_executed": task_stats.total_actions or 0,
                "total_actions_pending_approval": task_stats.total_pending or 0,
            },
            "top_actions": top_actions,
            "module_error_rates": module_errors,
            "token_cost": token_report,
            "recommendations": self._generate_recommendations(task_stats, module_errors),
        }

    def _generate_recommendations(self, task_stats, module_errors: list[dict]) -> list[str]:
        recommendations = []
        avg_tokens = float(task_stats.avg_tokens or 0)

        if avg_tokens > 5000:
            recommendations.append(
                f"High token usage ({avg_tokens:.0f} avg/cycle). "
                "Consider reducing tool spec verbosity or using smaller cycles for read-only tasks."
            )

        high_error_modules = [m for m in module_errors if m["error_rate_pct"] > 20]
        for m in high_error_modules:
            recommendations.append(
                f"Module '{m['module']}' has {m['error_rate_pct']}% error rate. "
                "Check API credentials and rate limits."
            )

        return recommendations

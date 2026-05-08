"""KPI tool definitions for the orchestrator."""

from __future__ import annotations

from typing import Any

TOOL_SPECS = [
    {
        "name": "kpi_get_dashboard",
        "description": (
            "Get the current KPI dashboard: sales today vs target, "
            "ad performance, SEO metrics, email revenue, and conversion rate. "
            "Always call this first in every orchestration cycle."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "kpi_get_trend",
        "description": "Get daily KPI trends for the last N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7, "description": "Number of days to look back"},
            },
            "required": [],
        },
    },
    {
        "name": "kpi_capture_snapshot",
        "description": "Force a fresh KPI snapshot (re-fetches from all sources).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


async def kpi_get_dashboard(db) -> dict[str, Any]:
    from app.modules.kpi.engine import KpiEngine
    engine = KpiEngine(db)
    return await engine.get_dashboard()


async def kpi_get_trend(db, days: int = 7) -> dict[str, Any]:
    from app.modules.kpi.engine import KpiEngine
    engine = KpiEngine(db)
    return {"trend": await engine.get_trend(days=days)}


async def kpi_capture_snapshot(db) -> dict[str, Any]:
    from app.modules.kpi.engine import KpiEngine
    engine = KpiEngine(db)
    snap = await engine.capture_snapshot()
    return {"captured": True, "snapshot_id": str(snap.id)}


def make_executors(db):
    return {
        "kpi_get_dashboard": lambda **kw: kpi_get_dashboard(db, **kw),
        "kpi_get_trend": lambda **kw: kpi_get_trend(db, **kw),
        "kpi_capture_snapshot": lambda **kw: kpi_capture_snapshot(db, **kw),
    }

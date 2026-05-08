"""Competitor monitoring tool definitions for the orchestrator."""

from __future__ import annotations

from typing import Any

TOOL_SPECS = [
    {
        "name": "competitor_scan",
        "description": (
            "Scan all configured competitor websites for pricing changes, "
            "new promotions, and new products. Run weekly or on demand."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


async def competitor_scan() -> dict[str, Any]:
    from app.modules.competitor.monitor import CompetitorMonitor
    monitor = CompetitorMonitor()
    return await monitor.scan_all()


EXECUTORS = {
    "competitor_scan": competitor_scan,
}

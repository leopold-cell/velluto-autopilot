"""Integration tests for the Orchestrator agent."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engines.approval import ApprovalEngine
from app.engines.rollback import RollbackEngine
from app.orchestrator.agent import Orchestrator


MOCK_KPI_DASHBOARD = {
    "date": "2026-05-08",
    "sales": {"orders_today": 3, "target": 7, "gap": 4, "pacing_pct": 42.9, "revenue_eur": 447.0, "aov_eur": 149.0},
    "meta_ads": {"spend_eur": 60.0, "roas": 2.0, "cpa_eur": 30.0, "ctr_pct": 1.8},
    "seo": {"organic_clicks": 30, "avg_position": 18.2},
    "cro": {"sessions": 240, "conversion_rate_pct": 1.25, "cart_abandonment_pct": 74.0},
    "email": {"revenue_eur": 45.0, "open_rate_pct": 26.0},
    "captured_at": "2026-05-08T09:00:00+00:00",
}


def _make_mock_response(tool_name: str, tool_id: str, text: str | None = None):
    """Build a mock Anthropic response with one tool_use block."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = tool_id
    tool_block.name = tool_name
    tool_block.input = {}

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text or f"Called {tool_name}"

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = "Cycle complete. Analyzed KPIs and made recommendations."

    mock_resp_tool = MagicMock()
    mock_resp_tool.stop_reason = "tool_use"
    mock_resp_tool.content = [tool_block]
    mock_resp_tool.usage = MagicMock(
        input_tokens=500,
        output_tokens=200,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=500,
    )

    mock_resp_end = MagicMock()
    mock_resp_end.stop_reason = "end_turn"
    mock_resp_end.content = [final_block]
    mock_resp_end.usage = MagicMock(
        input_tokens=600,
        output_tokens=150,
        cache_read_input_tokens=500,
        cache_creation_input_tokens=0,
    )

    return mock_resp_tool, mock_resp_end


@pytest.mark.asyncio
class TestOrchestrator:
    async def test_dry_run_cycle_completes(self, db):
        """Orchestrator cycle runs in dry_run mode without errors."""
        orch = Orchestrator()

        tool_resp, end_resp = _make_mock_response("kpi_get_dashboard", "tool_1")

        with patch.object(orch.client.messages, "create", new=AsyncMock(
            side_effect=[tool_resp, end_resp]
        )):
            with patch("app.modules.kpi.tools.kpi_get_dashboard", new=AsyncMock(return_value=MOCK_KPI_DASHBOARD)):
                with patch.object(orch.token_optimizer, "track_usage", new=AsyncMock(return_value={})):
                    result = await orch.run_cycle(trigger="test", dry_run=True)

        assert "summary" in result
        assert "total_tokens" in result
        assert result["total_tokens"] > 0

    async def test_task_record_created(self, db):
        """A Task record is written to the database during cycle."""
        from sqlalchemy import select
        from app.models.task import Task

        orch = Orchestrator()
        task_id = uuid.uuid4()
        _, end_resp = _make_mock_response("kpi_get_dashboard", "tool_1")

        with patch.object(orch.client.messages, "create", new=AsyncMock(return_value=end_resp)):
            with patch.object(orch.token_optimizer, "track_usage", new=AsyncMock(return_value={})):
                await orch.run_cycle(task_id=task_id, trigger="test", dry_run=True)

        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        assert task is not None
        assert task.status.value == "completed"

    async def test_failed_cycle_updates_task_status(self, db):
        from sqlalchemy import select
        from app.models.task import Task

        orch = Orchestrator()
        task_id = uuid.uuid4()

        with patch.object(orch.client.messages, "create", new=AsyncMock(side_effect=Exception("API down"))):
            with patch("app.modules.whatsapp.client.WhatsAppClient") as mock_wa:
                mock_wa.return_value.send_text = AsyncMock()
                with pytest.raises(Exception):
                    await orch.run_cycle(task_id=task_id, trigger="test", dry_run=True)

        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        assert task is not None
        assert task.status.value == "failed"
        assert "API down" in task.error

    def test_build_inverse_for_budget_change(self):
        orch = Orchestrator()
        inverse = orch._build_inverse(
            "meta_adjust_campaign_budget",
            {"campaign_id": "123", "new_daily_budget": 120.0, "current_budget": 100.0, "reason": "scale"},
            {"updated": True},
        )
        assert inverse is not None
        assert inverse["payload"]["new_daily_budget"] == 100.0
        assert inverse["payload"]["campaign_id"] == "123"

    def test_build_inverse_for_pause_campaign(self):
        orch = Orchestrator()
        inverse = orch._build_inverse(
            "meta_pause_campaign",
            {"campaign_id": "456"},
            {"paused": True},
        )
        assert inverse is not None
        assert inverse["action"] == "meta_resume_campaign"

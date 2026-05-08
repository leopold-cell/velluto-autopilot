"""API endpoint tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestHealthEndpoints:
    async def test_ping(self, client):
        r = await client.get("/health/ping")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    async def test_health_check(self, client):
        with patch("app.engines.monitoring.MonitoringEngine.run_health_checks", new=AsyncMock(
            return_value={"healthy": True, "checks": {}}
        )):
            r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["healthy"] is True


@pytest.mark.asyncio
class TestOrchestratorEndpoints:
    async def test_run_cycle_returns_task_id(self, client):
        r = await client.post("/orchestrator/run", json={"dry_run": True})
        assert r.status_code == 200
        data = r.json()
        assert "task_id" in data
        assert data["status"] == "queued"

    async def test_list_tasks_returns_list(self, client):
        r = await client.get("/orchestrator/tasks")
        assert r.status_code == 200
        assert "tasks" in r.json()


@pytest.mark.asyncio
class TestApprovalEndpoints:
    async def test_list_approvals_empty(self, client):
        r = await client.get("/approvals")
        assert r.status_code == 200
        data = r.json()
        assert "approvals" in data
        assert isinstance(data["approvals"], list)

    async def test_resolve_nonexistent_approval(self, client):
        import uuid
        r = await client.post(
            f"/approvals/{uuid.uuid4()}/resolve",
            json={"decision": "approve", "resolved_by": "test"},
        )
        assert r.status_code == 200
        assert "error" in r.json()

    async def test_resolve_invalid_decision(self, client):
        import uuid
        r = await client.post(
            f"/approvals/{uuid.uuid4()}/resolve",
            json={"decision": "maybe", "resolved_by": "test"},
        )
        assert r.status_code == 400


@pytest.mark.asyncio
class TestReportEndpoints:
    async def test_token_report(self, client):
        with patch("app.modules.token_optimizer.optimizer.TokenOptimizer.get_daily_report",
                   new=AsyncMock(return_value={"total_cost_usd": 0.05})):
            with patch("app.modules.token_optimizer.optimizer.TokenOptimizer.get_weekly_cost_summary",
                       new=AsyncMock(return_value={"weekly_total_usd": 0.35})):
                r = await client.get("/reports/tokens")
        assert r.status_code == 200
        data = r.json()
        assert "today" in data
        assert "week" in data

    async def test_pending_rollbacks(self, client):
        r = await client.get("/reports/rollback/pending")
        assert r.status_code == 200
        assert "pending" in r.json()


@pytest.mark.asyncio
class TestWhatsAppWebhook:
    async def test_verify_webhook(self, client):
        from app.config import settings
        r = await client.get(
            "/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": settings.whatsapp_verify_token,
                "hub.challenge": "challenge123",
            },
        )
        assert r.status_code == 200

    async def test_verify_webhook_wrong_token(self, client):
        r = await client.get(
            "/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "challenge123",
            },
        )
        assert r.status_code == 403

"""Tests for the ApprovalEngine."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.engines.approval import ApprovalEngine, classify_risk, HIGH_RISK_ACTIONS
from app.models.approval import Approval, ApprovalStatus


class TestClassifyRisk:
    def test_high_risk_actions_are_high(self):
        for action in HIGH_RISK_ACTIONS:
            assert classify_risk(action, {}) == "high"

    def test_seo_update_is_low(self):
        assert classify_risk("update_product_seo", {}) == "low"

    def test_budget_change_over_threshold_is_high(self):
        risk = classify_risk("adjust_meta_budget", {"change_pct": 0.25})
        assert risk == "high"

    def test_budget_change_under_threshold_is_medium(self):
        risk = classify_risk("adjust_meta_budget", {"change_pct": 0.05})
        assert risk == "medium"

    def test_generate_creative_is_low(self):
        assert classify_risk("generate_ad_creative", {}) == "low"


@pytest.mark.asyncio
class TestApprovalEngine:
    async def test_low_risk_auto_executes(self, db):
        engine = ApprovalEngine(db)
        executed = []

        async def mock_executor(payload):
            executed.append(payload)
            return {"done": True}

        result = await engine.request(
            action="update_product_seo",
            module="shopify",
            payload={"product_id": "123"},
            reason="SEO improvement",
            executor=mock_executor,
        )
        assert result["status"] == "auto_executed"
        assert len(executed) == 1

    async def test_high_risk_creates_pending_approval(self, db, mock_whatsapp):
        engine = ApprovalEngine(db)

        with patch("app.engines.approval.send_approval_request", new=AsyncMock()):
            result = await engine.request(
                action="update_product_price",
                module="shopify",
                payload={"product_id": "123", "variant_id": "456", "new_price": 199.0},
                reason="Competitor pricing",
            )

        assert result["status"] == "pending_approval"
        assert "approval_id" in result
        assert result["risk_level"] == "high"

    async def test_resolve_approve_calls_executor(self, db, mock_whatsapp):
        engine = ApprovalEngine(db)
        executed = []

        async def mock_executor(payload):
            executed.append(payload)
            return {"updated": True}

        with patch("app.engines.approval.send_approval_request", new=AsyncMock()):
            pending = await engine.request(
                action="update_product_price",
                module="shopify",
                payload={"product_id": "123"},
                reason="test",
            )

        approval_id = uuid.UUID(pending["approval_id"])
        result = await engine.resolve(
            approval_id=approval_id,
            decision="approve",
            resolved_by="test",
            executor=mock_executor,
        )
        assert result["status"] == "approved"
        assert len(executed) == 1

    async def test_resolve_reject_does_not_execute(self, db):
        engine = ApprovalEngine(db)
        executed = []

        with patch("app.engines.approval.send_approval_request", new=AsyncMock()):
            pending = await engine.request(
                action="update_product_price",
                module="shopify",
                payload={"product_id": "123"},
                reason="test",
            )

        approval_id = uuid.UUID(pending["approval_id"])
        result = await engine.resolve(
            approval_id=approval_id,
            decision="reject",
            resolved_by="test",
            rejection_reason="Not now",
        )
        assert result["status"] == "rejected"
        assert len(executed) == 0

    async def test_resolve_nonexistent_approval_returns_error(self, db):
        engine = ApprovalEngine(db)
        result = await engine.resolve(uuid.uuid4(), "approve", "test")
        assert "error" in result

    async def test_expired_approval_returns_error(self, db):
        from sqlalchemy import update
        from app.models.approval import Approval

        engine = ApprovalEngine(db)
        with patch("app.engines.approval.send_approval_request", new=AsyncMock()):
            pending = await engine.request(
                action="update_product_price",
                module="shopify",
                payload={"product_id": "123"},
                reason="test",
            )

        approval_id = uuid.UUID(pending["approval_id"])
        # Manually expire it
        await db.execute(
            update(Approval)
            .where(Approval.id == approval_id)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(hours=5))
        )
        await db.commit()

        result = await engine.resolve(approval_id, "approve", "test")
        assert result.get("error") == "approval_expired"

"""Tests for the RollbackEngine."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.engines.rollback import RollbackEngine, _INVERSE_REGISTRY, register_inverse


@pytest.mark.asyncio
class TestRollbackEngine:
    async def test_register_creates_record(self, db):
        engine = RollbackEngine(db)
        action_id = uuid.uuid4()

        record = await engine.register(
            action_id=action_id,
            action="meta_adjust_campaign_budget",
            module="meta",
            forward_payload={"campaign_id": "123", "new_daily_budget": 120.0},
            inverse_action="meta_adjust_campaign_budget",
            inverse_payload={"campaign_id": "123", "new_daily_budget": 100.0},
        )
        assert record.action_id == action_id
        assert record.rolled_back is False

    async def test_rollback_calls_inverse_function(self, db):
        called_with = []

        @register_inverse("meta_test", "meta_adjust_campaign_budget")
        async def _inverse(payload):
            called_with.append(payload)
            return {"restored": True}

        engine = RollbackEngine(db)
        action_id = uuid.uuid4()

        await engine.register(
            action_id=action_id,
            action="meta_adjust_campaign_budget",
            module="meta_test",
            forward_payload={"campaign_id": "123", "new_daily_budget": 120.0},
            inverse_action="meta_adjust_campaign_budget",
            inverse_payload={"campaign_id": "123", "new_daily_budget": 100.0},
        )

        result = await engine.rollback(action_id, rolled_back_by="test")
        assert result["status"] == "rolled_back"
        assert len(called_with) == 1
        assert called_with[0]["campaign_id"] == "123"

    async def test_rollback_nonexistent_returns_error(self, db):
        engine = RollbackEngine(db)
        result = await engine.rollback(uuid.uuid4())
        assert "error" in result

    async def test_rollback_twice_returns_error(self, db):
        @register_inverse("meta_test2", "meta_adjust_campaign_budget")
        async def _inverse(payload):
            return {"restored": True}

        engine = RollbackEngine(db)
        action_id = uuid.uuid4()

        await engine.register(
            action_id=action_id,
            action="meta_adjust_campaign_budget",
            module="meta_test2",
            forward_payload={"campaign_id": "999"},
            inverse_action="meta_adjust_campaign_budget",
            inverse_payload={"campaign_id": "999", "new_daily_budget": 50.0},
        )

        await engine.rollback(action_id)
        result = await engine.rollback(action_id)
        assert "error" in result

    async def test_list_pending_returns_unrolled(self, db):
        engine = RollbackEngine(db)
        action_id = uuid.uuid4()

        await engine.register(
            action_id=action_id,
            action="shopify_update_product_seo",
            module="shopify",
            forward_payload={"product_id": "999"},
            inverse_action="shopify_update_product_seo",
            inverse_payload={"product_id": "999", "seo_title": "Original"},
        )

        pending = await engine.list_pending()
        action_ids = [p["action_id"] for p in pending]
        assert str(action_id) in action_ids

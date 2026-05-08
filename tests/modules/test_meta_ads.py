"""Tests for Meta Ads module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.meta_ads.optimizer import (
    MetaAdsOptimizer,
    ROAS_SCALE_UP,
    ROAS_SCALE_DOWN,
    ROAS_PAUSE,
    BUDGET_SCALE_FACTOR,
    BUDGET_REDUCTION_FACTOR,
)


MOCK_CAMPAIGN = {
    "id": "camp_123",
    "name": "Test Campaign",
    "status": "ACTIVE",
    "daily_budget": "10000",  # €100 in cents
}

MOCK_INSIGHTS_HIGH_ROAS = {
    "spend": "50.00",
    "impressions": "10000",
    "clicks": "250",
    "ctr": "2.5",
    "cpm": "5.0",
    "purchase_roas": [{"action_type": "purchase", "value": "3.5"}],
    "actions": [{"action_type": "purchase", "value": "12"}],
}

MOCK_INSIGHTS_LOW_ROAS = {
    "spend": "50.00",
    "impressions": "10000",
    "clicks": "100",
    "ctr": "1.0",
    "cpm": "5.0",
    "purchase_roas": [{"action_type": "purchase", "value": "1.0"}],
    "actions": [{"action_type": "purchase", "value": "3"}],
}

MOCK_INSIGHTS_CRITICAL = {
    "spend": "25.00",
    "impressions": "5000",
    "clicks": "50",
    "ctr": "1.0",
    "cpm": "5.0",
    "purchase_roas": [{"action_type": "purchase", "value": "0.5"}],
    "actions": [{"action_type": "purchase", "value": "1"}],
}


@pytest.mark.asyncio
class TestMetaAdsOptimizer:
    def _make_optimizer(self, campaign_insights):
        optimizer = MetaAdsOptimizer()
        optimizer.client = MagicMock()
        optimizer.client.get_campaigns = AsyncMock(return_value=[MOCK_CAMPAIGN])
        optimizer.client.get_account_insights = AsyncMock(return_value=campaign_insights)
        optimizer.client.get_campaign_insights = AsyncMock(return_value=campaign_insights)
        return optimizer

    async def test_high_roas_recommends_scale_up(self):
        optimizer = self._make_optimizer(MOCK_INSIGHTS_HIGH_ROAS)
        result = await optimizer.analyze_and_recommend()
        recs = result["recommendations"]
        assert any(r["action"] == "adjust_meta_budget" and r.get("new_daily_budget", 0) > 100 for r in recs)

    async def test_low_roas_recommends_scale_down(self):
        optimizer = self._make_optimizer(MOCK_INSIGHTS_LOW_ROAS)
        result = await optimizer.analyze_and_recommend()
        recs = result["recommendations"]
        assert any(r["action"] == "adjust_meta_budget" and r.get("new_daily_budget", 999) < 100 for r in recs)

    async def test_critical_roas_recommends_pause(self):
        optimizer = self._make_optimizer(MOCK_INSIGHTS_CRITICAL)
        result = await optimizer.analyze_and_recommend()
        recs = result["recommendations"]
        assert any(r["action"] == "pause_campaign" for r in recs)

    async def test_budget_change_dry_run(self):
        optimizer = MetaAdsOptimizer()
        optimizer.client = MagicMock()
        result = await optimizer.execute_budget_change("camp_123", 120.0, dry_run=True)
        assert result["dry_run"] is True
        optimizer.client.update_campaign_budget.assert_not_called()

    async def test_pause_campaign_dry_run(self):
        optimizer = MetaAdsOptimizer()
        optimizer.client = MagicMock()
        result = await optimizer.execute_pause_campaign("camp_123", dry_run=True)
        assert result["dry_run"] is True
        optimizer.client.update_campaign_status.assert_not_called()

    def test_extract_roas(self):
        optimizer = MetaAdsOptimizer()
        assert optimizer._extract_roas(MOCK_INSIGHTS_HIGH_ROAS) == 3.5
        assert optimizer._extract_roas({}) == 0.0
        assert optimizer._extract_roas({"purchase_roas": []}) == 0.0

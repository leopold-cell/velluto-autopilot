"""Tests for KPI Engine."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.kpi.engine import KpiEngine


MOCK_SHOPIFY = {"order_count": 4, "revenue_eur": 596.0, "aov_eur": 149.0}
MOCK_META = {"spend": 85.0, "roas": 7.0, "cpa": 21.25, "ctr": 2.3, "impressions": 12000}
MOCK_GSC = {"clicks": 45, "impressions": 600, "avg_position": 14.5}
MOCK_CLARITY = {"sessions": 320, "conversion_rate": 1.25, "cart_abandonment": 72.0}
MOCK_EMAIL = {"revenue": 89.0, "open_rate": 28.5}


@pytest.mark.asyncio
class TestKpiEngine:
    @patch.multiple(
        "app.modules.kpi.engine.KpiEngine",
        _fetch_shopify=AsyncMock(return_value=MOCK_SHOPIFY),
        _fetch_meta=AsyncMock(return_value=MOCK_META),
        _fetch_gsc=AsyncMock(return_value=MOCK_GSC),
        _fetch_clarity=AsyncMock(return_value=MOCK_CLARITY),
        _fetch_email=AsyncMock(return_value=MOCK_EMAIL),
    )
    async def test_capture_snapshot_creates_record(self, db):
        engine = KpiEngine(db)
        snap = await engine.capture_snapshot()

        assert snap.orders_count == 4
        assert snap.revenue_eur == 596.0
        assert snap.ad_roas == 7.0
        assert snap.organic_clicks == 45
        assert snap.sessions == 320
        assert snap.email_open_rate_pct == 28.5

    @patch.multiple(
        "app.modules.kpi.engine.KpiEngine",
        _fetch_shopify=AsyncMock(return_value=MOCK_SHOPIFY),
        _fetch_meta=AsyncMock(return_value=MOCK_META),
        _fetch_gsc=AsyncMock(return_value=MOCK_GSC),
        _fetch_clarity=AsyncMock(return_value=MOCK_CLARITY),
        _fetch_email=AsyncMock(return_value=MOCK_EMAIL),
    )
    async def test_get_dashboard_returns_structured_data(self, db):
        engine = KpiEngine(db)
        dashboard = await engine.get_dashboard()

        assert "sales" in dashboard
        assert "meta_ads" in dashboard
        assert "seo" in dashboard
        assert "cro" in dashboard
        assert "email" in dashboard
        assert dashboard["sales"]["orders_today"] == 4
        assert dashboard["sales"]["target"] == 7
        assert dashboard["sales"]["gap"] == 3
        assert dashboard["meta_ads"]["roas"] == 7.0

    @patch.multiple(
        "app.modules.kpi.engine.KpiEngine",
        _fetch_shopify=AsyncMock(return_value=MOCK_SHOPIFY),
        _fetch_meta=AsyncMock(return_value=MOCK_META),
        _fetch_gsc=AsyncMock(return_value=MOCK_GSC),
        _fetch_clarity=AsyncMock(return_value=MOCK_CLARITY),
        _fetch_email=AsyncMock(return_value=MOCK_EMAIL),
    )
    async def test_pacing_calculation(self, db):
        engine = KpiEngine(db)
        dashboard = await engine.get_dashboard()
        pacing = dashboard["sales"]["pacing_pct"]
        assert pacing == round(4 / 7 * 100, 1)

    async def test_get_trend_returns_list(self, db, sample_kpi_snapshot):
        db.add(sample_kpi_snapshot)
        await db.commit()

        engine = KpiEngine(db)
        trend = await engine.get_trend(days=7)
        assert isinstance(trend, list)
        assert len(trend) >= 1
        assert "date" in trend[0]
        assert "orders" in trend[0]

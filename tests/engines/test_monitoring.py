"""Tests for the MonitoringEngine."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.engines.monitoring import MonitoringEngine


@pytest.mark.asyncio
class TestMonitoringEngine:
    async def test_db_check_passes_when_db_is_healthy(self, db):
        monitor = MonitoringEngine(db)
        result = await monitor._check_db()
        assert result["healthy"] is True

    async def test_redis_check_passes_when_redis_is_available(self, db):
        monitor = MonitoringEngine(db)
        with patch("app.engines.monitoring.get_redis") as mock_redis:
            r = AsyncMock()
            r.ping = AsyncMock(return_value=True)
            mock_redis.return_value = r
            result = await monitor._check_redis()
        assert result["healthy"] is True

    async def test_redis_check_fails_when_redis_is_down(self, db):
        monitor = MonitoringEngine(db)
        with patch("app.engines.monitoring.get_redis") as mock_redis:
            mock_redis.side_effect = ConnectionError("redis down")
            result = await monitor._check_redis()
        assert result["healthy"] is False
        assert "error" in result

    async def test_health_check_aggregates_all_checks(self, db):
        monitor = MonitoringEngine(db)
        with patch.object(monitor, "_check_db", AsyncMock(return_value={"healthy": True})):
            with patch.object(monitor, "_check_redis", AsyncMock(return_value={"healthy": True})):
                with patch.object(monitor, "_check_sales_pace", AsyncMock(return_value={"healthy": True})):
                    with patch.object(monitor, "_check_error_rate", AsyncMock(return_value={"healthy": True, "error_rate_pct": 0.0})):
                        result = await monitor.run_health_checks()
        assert result["healthy"] is True
        assert "checks" in result

    async def test_alert_critical_sends_whatsapp(self, db, mock_whatsapp):
        monitor = MonitoringEngine(db)
        with patch("app.engines.monitoring.WhatsAppClient", return_value=mock_whatsapp):
            await monitor.alert_critical("Test critical alert", {"key": "value"})
        mock_whatsapp.send_text.assert_called_once()
        call_args = mock_whatsapp.send_text.call_args[0][0]
        assert "CRITICAL" in call_args

    async def test_alert_warning_sends_whatsapp(self, db, mock_whatsapp):
        monitor = MonitoringEngine(db)
        with patch("app.engines.monitoring.WhatsAppClient", return_value=mock_whatsapp):
            await monitor.alert_warning("Something to watch")
        mock_whatsapp.send_text.assert_called_once()

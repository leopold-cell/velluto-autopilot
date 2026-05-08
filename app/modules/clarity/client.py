"""Microsoft Clarity API client for CRO analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog

from app.config import settings

log = structlog.get_logger()

BASE = "https://www.clarity.ms/api/v1"


class ClarityClient:
    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=BASE,
            headers={"Authorization": f"Bearer {settings.clarity_api_token}"},
            timeout=30.0,
        )
        self.project_id = settings.clarity_project_id

    async def get_today_summary(self) -> dict[str, Any]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            r = await self._client.get(
                f"/projects/{self.project_id}/metrics",
                params={"startDate": today, "endDate": today},
            )
            r.raise_for_status()
            data = r.json()

            sessions = data.get("totalSessions", 0)
            conversions = data.get("totalConversions", 0)
            cart_abandonment = data.get("cartAbandonmentRate", 0.0)
            conversion_rate = (conversions / sessions * 100) if sessions > 0 else 0.0

            return {
                "sessions": sessions,
                "conversion_rate": round(conversion_rate, 2),
                "cart_abandonment": round(float(cart_abandonment), 2),
            }
        except Exception as e:
            log.warning("clarity.today_summary_failed", error=str(e))
            return {"sessions": 0, "conversion_rate": 0.0, "cart_abandonment": 0.0}

    async def get_heatmap_insights(self, page_url: str) -> dict[str, Any]:
        """Get rage clicks, dead clicks, and scroll depth for a page."""
        try:
            r = await self._client.get(
                f"/projects/{self.project_id}/heatmaps",
                params={"url": page_url},
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning("clarity.heatmap_failed", url=page_url, error=str(e))
            return {}

    async def get_funnel_analysis(self) -> dict[str, Any]:
        """Get checkout funnel drop-off rates."""
        try:
            r = await self._client.get(f"/projects/{self.project_id}/funnel")
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning("clarity.funnel_failed", error=str(e))
            return {}

    async def get_cro_opportunities(self) -> dict[str, Any]:
        """Identify pages with high rage-click or scroll-stop rates."""
        try:
            r = await self._client.get(
                f"/projects/{self.project_id}/pages",
                params={"sortBy": "rageClicks", "limit": 10},
            )
            r.raise_for_status()
            data = r.json()
            pages = data.get("pages", [])
            return {
                "high_rage_click_pages": [
                    {
                        "url": p.get("url"),
                        "rage_clicks": p.get("rageClicks", 0),
                        "sessions": p.get("sessions", 0),
                    }
                    for p in pages
                ]
            }
        except Exception as e:
            log.warning("clarity.cro_opportunities_failed", error=str(e))
            return {"high_rage_click_pages": []}

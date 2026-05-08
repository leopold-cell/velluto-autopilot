"""Meta Marketing API async client."""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

log = structlog.get_logger()

BASE = "https://graph.facebook.com/v21.0"


class MetaAdsClient:
    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=BASE,
            params={"access_token": settings.meta_access_token},
            timeout=30.0,
        )
        self.ad_account_id = settings.meta_ad_account_id

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get(self, path: str, params: dict | None = None) -> Any:
        r = await self._client.get(path, params=params or {})
        r.raise_for_status()
        return r.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def post(self, path: str, data: dict) -> Any:
        r = await self._client.post(path, data=data)
        r.raise_for_status()
        return r.json()

    # ── Campaigns ─────────────────────────────────────────────────────────────

    async def get_campaigns(self) -> list[dict]:
        fields = "id,name,status,daily_budget,lifetime_budget,objective"
        data = await self.get(
            f"/{self.ad_account_id}/campaigns",
            params={"fields": fields, "limit": 50},
        )
        return data.get("data", [])

    async def update_campaign_budget(self, campaign_id: str, daily_budget_cents: int) -> dict:
        return await self.post(f"/{campaign_id}", {"daily_budget": daily_budget_cents})

    async def update_campaign_status(self, campaign_id: str, status: str) -> dict:
        return await self.post(f"/{campaign_id}", {"status": status})

    # ── Ad Sets ───────────────────────────────────────────────────────────────

    async def get_adsets(self, campaign_id: str) -> list[dict]:
        fields = "id,name,status,daily_budget,targeting,optimization_goal,bid_amount"
        data = await self.get(
            f"/{campaign_id}/adsets",
            params={"fields": fields, "limit": 50},
        )
        return data.get("data", [])

    async def update_adset_bid(self, adset_id: str, bid_amount_cents: int) -> dict:
        return await self.post(f"/{adset_id}", {"bid_amount": bid_amount_cents})

    # ── Insights ──────────────────────────────────────────────────────────────

    async def get_campaign_insights(self, campaign_id: str, date_preset: str = "today") -> dict:
        fields = (
            "spend,impressions,clicks,ctr,cpc,cpm,actions,action_values,"
            "cost_per_action_type,purchase_roas"
        )
        data = await self.get(
            f"/{campaign_id}/insights",
            params={"fields": fields, "date_preset": date_preset},
        )
        rows = data.get("data", [])
        return rows[0] if rows else {}

    async def get_account_insights(self, date_preset: str = "today") -> dict:
        fields = (
            "spend,impressions,clicks,ctr,cpm,actions,action_values,purchase_roas,cost_per_action_type"
        )
        data = await self.get(
            f"/{self.ad_account_id}/insights",
            params={"fields": fields, "date_preset": date_preset},
        )
        rows = data.get("data", [])
        return rows[0] if rows else {}

    # ── Ads ───────────────────────────────────────────────────────────────────

    async def get_ads(self, campaign_id: str) -> list[dict]:
        fields = "id,name,status,creative"
        data = await self.get(
            f"/{campaign_id}/ads",
            params={"fields": fields, "limit": 50},
        )
        return data.get("data", [])

    async def create_ad(self, adset_id: str, creative_id: str, name: str) -> dict:
        return await self.post(
            f"/{self.ad_account_id}/ads",
            {
                "name": name,
                "adset_id": adset_id,
                "creative": f'{{"creative_id":"{creative_id}"}}',
                "status": "PAUSED",
            },
        )

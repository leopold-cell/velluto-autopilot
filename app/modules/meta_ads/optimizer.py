"""
Meta Ads optimizer — analyzes campaign performance and recommends actions.
Uses rule-based logic + Claude reasoning for nuanced decisions.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.modules.meta_ads.client import MetaAdsClient

log = structlog.get_logger()

# ROAS thresholds
ROAS_SCALE_UP = 3.0      # ROAS above this → increase budget
ROAS_SCALE_DOWN = 1.5    # ROAS below this → decrease budget
ROAS_PAUSE = 0.8         # ROAS below this → pause campaign

BUDGET_SCALE_FACTOR = 1.20   # +20% budget increase
BUDGET_REDUCTION_FACTOR = 0.80  # -20% budget reduction


class MetaAdsOptimizer:
    def __init__(self):
        self.client = MetaAdsClient()

    async def analyze_and_recommend(self) -> dict[str, Any]:
        campaigns = await self.client.get_campaigns()
        account_insights = await self.client.get_account_insights(date_preset="last_7d")

        recommendations: list[dict] = []
        for campaign in campaigns:
            if campaign.get("status") != "ACTIVE":
                continue

            insights = await self.client.get_campaign_insights(campaign["id"], date_preset="today")
            roas = self._extract_roas(insights)
            spend = float(insights.get("spend", 0))
            current_budget = int(campaign.get("daily_budget", 0)) / 100  # cents → EUR

            rec = self._build_recommendation(campaign, roas, spend, current_budget, insights)
            if rec:
                recommendations.append(rec)

        return {
            "account_summary": self._parse_account_insights(account_insights),
            "campaigns_analyzed": len(campaigns),
            "recommendations": recommendations,
        }

    def _extract_roas(self, insights: dict) -> float:
        roas_data = insights.get("purchase_roas", [])
        if isinstance(roas_data, list) and roas_data:
            return float(roas_data[0].get("value", 0))
        return 0.0

    def _extract_purchases(self, insights: dict) -> int:
        for action in insights.get("actions", []):
            if action.get("action_type") == "purchase":
                return int(action.get("value", 0))
        return 0

    def _build_recommendation(
        self,
        campaign: dict,
        roas: float,
        spend: float,
        current_budget: float,
        insights: dict,
    ) -> dict | None:
        cid = campaign["id"]
        name = campaign.get("name", cid)

        if roas == 0 and spend > 20:
            return {
                "action": "pause_campaign",
                "campaign_id": cid,
                "campaign_name": name,
                "reason": f"Spend €{spend:.0f} with 0 ROAS — possible tracking issue or no sales",
                "risk": "medium",
            }

        if roas < ROAS_PAUSE and spend > 10:
            return {
                "action": "pause_campaign",
                "campaign_id": cid,
                "campaign_name": name,
                "roas": roas,
                "reason": f"ROAS {roas:.2f} is below minimum threshold {ROAS_PAUSE}",
                "risk": "high",
            }

        if roas < ROAS_SCALE_DOWN and current_budget > 5:
            new_budget = round(current_budget * BUDGET_REDUCTION_FACTOR, 2)
            change_pct = (new_budget - current_budget) / current_budget
            return {
                "action": "adjust_meta_budget",
                "campaign_id": cid,
                "campaign_name": name,
                "current_budget": current_budget,
                "new_daily_budget": new_budget,
                "change_pct": change_pct,
                "roas": roas,
                "reason": f"ROAS {roas:.2f} below scale target {ROAS_SCALE_DOWN} — reducing budget",
                "risk": "medium",
            }

        if roas > ROAS_SCALE_UP:
            new_budget = round(current_budget * BUDGET_SCALE_FACTOR, 2)
            change_pct = (new_budget - current_budget) / current_budget
            return {
                "action": "adjust_meta_budget",
                "campaign_id": cid,
                "campaign_name": name,
                "current_budget": current_budget,
                "new_daily_budget": new_budget,
                "change_pct": change_pct,
                "roas": roas,
                "reason": f"ROAS {roas:.2f} exceeds scale target {ROAS_SCALE_UP} — scaling budget",
                "risk": "high" if change_pct > 0.10 else "medium",
            }

        return None

    def _parse_account_insights(self, insights: dict) -> dict:
        roas = self._extract_roas(insights)
        return {
            "spend_7d_eur": float(insights.get("spend", 0)),
            "impressions_7d": int(insights.get("impressions", 0)),
            "clicks_7d": int(insights.get("clicks", 0)),
            "ctr_pct": float(insights.get("ctr", 0)),
            "cpm_eur": float(insights.get("cpm", 0)),
            "roas_7d": roas,
        }

    async def execute_budget_change(
        self, campaign_id: str, new_daily_budget: float, dry_run: bool = False
    ) -> dict:
        if dry_run:
            return {"dry_run": True, "campaign_id": campaign_id, "new_budget": new_daily_budget}
        result = await self.client.update_campaign_budget(campaign_id, int(new_daily_budget * 100))
        return {"updated": True, "campaign_id": campaign_id, "result": result}

    async def execute_pause_campaign(self, campaign_id: str, dry_run: bool = False) -> dict:
        if dry_run:
            return {"dry_run": True, "campaign_id": campaign_id, "action": "pause"}
        result = await self.client.update_campaign_status(campaign_id, "PAUSED")
        return {"paused": True, "campaign_id": campaign_id, "result": result}

"""Meta Ads tool definitions for the orchestrator."""

from __future__ import annotations

from typing import Any

from app.modules.meta_ads.client import MetaAdsClient
from app.modules.meta_ads.optimizer import MetaAdsOptimizer

client = MetaAdsClient()
optimizer = MetaAdsOptimizer()

TOOL_SPECS = [
    {
        "name": "meta_get_campaigns",
        "description": "Get all Meta ad campaigns with status and current budgets.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "meta_get_account_insights",
        "description": "Get Meta ad account performance insights (spend, ROAS, CPC, CTR).",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_preset": {
                    "type": "string",
                    "enum": ["today", "yesterday", "last_7d", "last_30d"],
                    "default": "today",
                },
            },
            "required": [],
        },
    },
    {
        "name": "meta_analyze_and_recommend",
        "description": (
            "Analyze all Meta campaigns and return optimization recommendations "
            "(budget changes, pauses, scale-ups)."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "meta_adjust_campaign_budget",
        "description": (
            "Adjust a Meta campaign's daily budget. "
            "HIGH RISK if change >10% — requires approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "new_daily_budget": {"type": "number", "description": "New daily budget in EUR"},
                "reason": {"type": "string"},
            },
            "required": ["campaign_id", "new_daily_budget", "reason"],
        },
    },
    {
        "name": "meta_pause_campaign",
        "description": "Pause a Meta campaign. Medium risk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["campaign_id", "reason"],
        },
    },
]


async def meta_get_campaigns() -> dict[str, Any]:
    campaigns = await client.get_campaigns()
    return {"campaigns": campaigns}


async def meta_get_account_insights(date_preset: str = "today") -> dict[str, Any]:
    return await client.get_account_insights(date_preset=date_preset)


async def meta_analyze_and_recommend() -> dict[str, Any]:
    return await optimizer.analyze_and_recommend()


async def meta_adjust_campaign_budget(
    campaign_id: str, new_daily_budget: float, reason: str, dry_run: bool = False
) -> dict[str, Any]:
    return await optimizer.execute_budget_change(campaign_id, new_daily_budget, dry_run=dry_run)


async def meta_pause_campaign(
    campaign_id: str, reason: str, dry_run: bool = False
) -> dict[str, Any]:
    return await optimizer.execute_pause_campaign(campaign_id, dry_run=dry_run)


EXECUTORS = {
    "meta_get_campaigns": meta_get_campaigns,
    "meta_get_account_insights": meta_get_account_insights,
    "meta_analyze_and_recommend": meta_analyze_and_recommend,
    "meta_adjust_campaign_budget": meta_adjust_campaign_budget,
    "meta_pause_campaign": meta_pause_campaign,
}

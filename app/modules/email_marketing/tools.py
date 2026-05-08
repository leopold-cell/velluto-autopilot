"""Email marketing tool definitions for the orchestrator."""

from __future__ import annotations

from typing import Any

TOOL_SPECS = [
    {
        "name": "email_get_metrics",
        "description": "Get today's email marketing performance (open rate, clicks, revenue).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "email_trigger_flow",
        "description": (
            "Trigger an automated email flow for a customer. "
            "HIGH RISK for mass sends (>100 recipients) — requires approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "flow_name": {
                    "type": "string",
                    "enum": ["abandoned_cart", "post_purchase", "welcome_series", "win_back"],
                },
                "customer_email": {"type": "string"},
                "customer_context": {"type": "object"},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["flow_name", "customer_email"],
        },
    },
    {
        "name": "email_send_campaign",
        "description": (
            "Send a bulk email campaign to a segment. "
            "ALWAYS requires approval — this is send_mass_email action."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "segment": {"type": "string"},
                "campaign_goal": {"type": "string"},
                "dry_run": {"type": "boolean", "default": True},
            },
            "required": ["subject", "segment", "campaign_goal"],
        },
    },
]


async def email_get_metrics() -> dict[str, Any]:
    from app.modules.email_marketing.client import EmailClient
    return await EmailClient().get_today_stats()


async def email_trigger_flow(
    flow_name: str,
    customer_email: str,
    customer_context: dict | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    from app.modules.email_marketing.flows import trigger_flow
    return await trigger_flow(
        flow_name=flow_name,
        customer_email=customer_email,
        customer_context=customer_context or {},
        dry_run=dry_run,
    )


async def email_send_campaign(
    subject: str,
    segment: str,
    campaign_goal: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    return {
        "dry_run": True,
        "note": "Mass email always requires explicit approval before sending.",
        "subject": subject,
        "segment": segment,
    }


EXECUTORS = {
    "email_get_metrics": email_get_metrics,
    "email_trigger_flow": email_trigger_flow,
    "email_send_campaign": email_send_campaign,
}

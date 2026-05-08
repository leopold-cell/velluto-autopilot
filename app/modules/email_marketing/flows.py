"""
Automated email flows replacing Klaviyo.
Flows are triggered by Shopify webhooks stored in Redis queue.
"""

from __future__ import annotations

from typing import Any

import anthropic
import structlog

from app.config import settings
from app.modules.email_marketing.client import EmailClient

log = structlog.get_logger()

email_client = EmailClient()
claude = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

FLOWS = {
    "abandoned_cart": {
        "delays_hours": [1, 24, 72],
        "description": "3-step cart abandonment sequence",
    },
    "post_purchase": {
        "delays_hours": [24, 72, 168],
        "description": "Post-purchase thank you + review request + cross-sell",
    },
    "welcome_series": {
        "delays_hours": [0, 24, 72, 168],
        "description": "4-step welcome for new subscribers",
    },
    "win_back": {
        "delays_hours": [0, 72, 168],
        "description": "Re-engagement for lapsed customers (90+ days)",
    },
}


async def generate_flow_email(
    flow_name: str,
    step: int,
    customer_context: dict,
) -> dict[str, Any]:
    """Use Claude to generate a personalized flow email."""
    flow = FLOWS.get(flow_name, {})
    prompt = f"""
Write a {flow_name} email (step {step + 1} of {len(flow.get('delays_hours', [1]))}) for Velluto cycling eyewear.

Customer context:
- Name: {customer_context.get('name', 'Cyclist')}
- Last product viewed: {customer_context.get('last_product', 'unknown')}
- Cart value: {customer_context.get('cart_value', 'unknown')}
- Customer since: {customer_context.get('customer_since', 'new')}

Flow: {flow.get('description', flow_name)}

Write in Velluto's premium, cycling-focused voice.
Output JSON: {{
  "subject": "...",
  "preview_text": "...",
  "html_body": "...",
  "plain_text": "..."
}}
"""
    response = await claude.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    import json
    text = response.content[0].text.strip()
    try:
        return json.loads(text)
    except Exception:
        return {"subject": f"From Velluto — {flow_name}", "html_body": text, "plain_text": text}


async def trigger_flow(
    flow_name: str,
    customer_email: str,
    customer_context: dict,
    dry_run: bool = False,
) -> dict[str, Any]:
    if flow_name not in FLOWS:
        return {"error": f"unknown_flow: {flow_name}", "available": list(FLOWS.keys())}

    flow = FLOWS[flow_name]
    step_0_content = await generate_flow_email(flow_name, 0, customer_context)

    if dry_run:
        return {
            "dry_run": True,
            "flow": flow_name,
            "recipient": customer_email,
            "first_email_preview": step_0_content,
        }

    # Queue subsequent steps in Redis
    from app.redis_client import get_redis
    import json
    r = await get_redis()
    for i, delay_hours in enumerate(flow["delays_hours"][1:], start=1):
        await r.rpush(
            "email_flow_queue",
            json.dumps({
                "flow_name": flow_name,
                "step": i,
                "customer_email": customer_email,
                "customer_context": customer_context,
                "send_after_hours": delay_hours,
                "queued_at": __import__("datetime").datetime.utcnow().isoformat(),
            }),
        )

    result = await email_client.send_transactional(
        to_email=customer_email,
        subject=step_0_content.get("subject", f"From Velluto"),
        html_content=step_0_content.get("html_body", ""),
    )
    log.info("email_flow.triggered", flow=flow_name, customer=customer_email)
    return {"triggered": True, "flow": flow_name, "first_send": result}

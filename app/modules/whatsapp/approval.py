"""
WhatsApp approval flow.
Sends interactive button messages for pending approvals.
Approval ID is embedded in button ID so the webhook handler can resolve it.
"""

from __future__ import annotations

import structlog

from app.models.approval import Approval
from app.modules.whatsapp.client import WhatsAppClient

log = structlog.get_logger()

RISK_EMOJI = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "🆘"}


async def send_approval_request(approval: Approval) -> None:
    client = WhatsAppClient()
    risk_label = RISK_EMOJI.get(approval.risk_level, "⚠️") + f" {approval.risk_level.upper()}"

    body_lines = [
        f"*Action Required [{risk_label}]*",
        "",
        f"Action: `{approval.action}`",
        f"Module: {approval.module}",
        f"Reason: {approval.reason}",
        "",
    ]

    if approval.dry_run_result:
        body_lines.append("*Preview:*")
        for k, v in approval.dry_run_result.items():
            body_lines.append(f"  {k}: {v}")
        body_lines.append("")

    expires = approval.expires_at.strftime("%H:%M") if approval.expires_at else "—"
    body_lines.append(f"⏰ Expires at {expires} (4h window)")

    short_id = str(approval.id)[:8]
    body = "\n".join(body_lines)

    await client.send_interactive_buttons(
        header=f"Velluto Autopilot — Approval #{short_id}",
        body=body,
        footer="Reply APPROVE or REJECT",
        buttons=[
            {"id": f"approve:{approval.id}", "title": "✅ Approve"},
            {"id": f"reject:{approval.id}", "title": "❌ Reject"},
        ],
    )
    log.info("approval.whatsapp_sent", approval_id=str(approval.id))

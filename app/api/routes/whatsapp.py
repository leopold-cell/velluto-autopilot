"""
WhatsApp webhook handler.
GET  /whatsapp/webhook  — verify webhook with Meta
POST /whatsapp/webhook  — receive messages (button replies for approvals, text commands)
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.whatsapp.client import WhatsAppClient

log = structlog.get_logger()
router = APIRouter()
client = WhatsAppClient()


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    challenge = client.verify_webhook(hub_mode, hub_verify_token, hub_challenge)
    if challenge is None:
        raise HTTPException(403, "Invalid verify token")
    return int(challenge)


@router.post("/webhook")
async def receive_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    msg = client.parse_incoming(body)

    if not msg:
        return {"status": "no_message"}

    log.info("whatsapp.incoming", type=msg["type"], from_=msg["from"])

    # Handle button replies (approval decisions)
    if msg["type"] == "interactive" and msg.get("button_id"):
        await _handle_button(msg["button_id"], db)
        return {"status": "handled"}

    # Handle text commands
    if msg["type"] == "text" and msg.get("text"):
        await _handle_command(msg["text"].strip(), db)
        return {"status": "handled"}

    return {"status": "ignored"}


async def _handle_button(button_id: str, db: AsyncSession):
    """Parse button_id like 'approve:UUID' or 'reject:UUID'."""
    try:
        action, approval_id_str = button_id.split(":", 1)
        approval_id = uuid.UUID(approval_id_str)
    except (ValueError, TypeError):
        log.warning("whatsapp.invalid_button_id", button_id=button_id)
        return

    from app.engines.approval import ApprovalEngine
    engine = ApprovalEngine(db)

    if action == "approve":
        result = await engine.resolve(approval_id, "approve", resolved_by="whatsapp")
        await client.send_text(f"✅ Action approved and executed.\n{result.get('status')}")
    elif action == "reject":
        result = await engine.resolve(approval_id, "reject", resolved_by="whatsapp")
        await client.send_text("❌ Action rejected and cancelled.")
    else:
        await client.send_text(f"Unknown action: {action}")


COMMANDS = {
    "status": "Get KPI dashboard",
    "run": "Trigger an orchestration cycle",
    "pending": "List pending approvals",
    "help": "Show available commands",
}


async def _handle_command(text: str, db: AsyncSession):
    cmd = text.lower().strip()

    if cmd == "help":
        lines = ["*Available commands:*"] + [f"• `{k}` — {v}" for k, v in COMMANDS.items()]
        await client.send_text("\n".join(lines))

    elif cmd == "status":
        from app.modules.kpi.engine import KpiEngine
        dashboard = await KpiEngine(db).get_dashboard()
        s = dashboard["sales"]
        m = dashboard["meta_ads"]
        text = (
            f"📊 *Velluto Status*\n\n"
            f"Orders today: {s['orders_today']}/{s['target']} ({s['pacing_pct']}%)\n"
            f"Revenue: €{s['revenue_eur']:.0f}\n"
            f"Ad spend: €{m['spend_eur']:.0f} | ROAS: {m['roas']:.2f}x\n"
        )
        await client.send_text(text)

    elif cmd == "run":
        from app.orchestrator.agent import Orchestrator
        await client.send_text("🤖 Starting orchestration cycle...")
        try:
            result = await Orchestrator().run_cycle(trigger="whatsapp")
            await client.send_text(
                f"✅ Cycle complete\n"
                f"Actions: {result['actions_executed']}\n"
                f"Pending approval: {result['actions_pending_approval']}\n\n"
                f"{result.get('summary', '')[:300]}"
            )
        except Exception as e:
            await client.send_text(f"❌ Cycle failed: {e}")

    elif cmd == "pending":
        from app.engines.rollback import RollbackEngine
        from app.engines.approval import ApprovalEngine
        from sqlalchemy import select
        from app.models.approval import Approval, ApprovalStatus

        result = await db.execute(
            select(Approval)
            .where(Approval.status == ApprovalStatus.pending)
            .order_by(Approval.created_at.desc())
            .limit(5)
        )
        approvals = result.scalars().all()
        if not approvals:
            await client.send_text("✅ No pending approvals.")
        else:
            lines = [f"*{len(approvals)} pending approvals:*"]
            for a in approvals:
                lines.append(f"• `{a.action}` [{a.risk_level}] — {a.reason[:60]}")
            await client.send_text("\n".join(lines))

    else:
        await client.send_text(f"Unknown command: `{cmd}`\nSend `help` for available commands.")

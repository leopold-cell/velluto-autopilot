"""
Dashboard Chat API.

POST /chat  — conversational interface powered by Claude.
The agent receives live KPI context so answers are grounded in real data.
Conversation history is managed client-side and sent with each request.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import anthropic
import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.audit import AuditLog
from app.models.kpi import KpiSnapshot

log = structlog.get_logger()
router = APIRouter()


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    stream: bool = True


async def _build_context(db: AsyncSession) -> str:
    """Gather live KPI + agent data to ground the chat."""
    now = datetime.now(timezone.utc)
    today = now.date()

    # Latest KPI snapshot
    snap_row = await db.execute(
        select(KpiSnapshot)
        .where(KpiSnapshot.snapshot_date == today)
        .order_by(KpiSnapshot.created_at.desc())
        .limit(1)
    )
    snap: KpiSnapshot | None = snap_row.scalar_one_or_none()

    # Last 7 days snapshots for trend
    week_rows = await db.execute(
        select(KpiSnapshot)
        .where(KpiSnapshot.snapshot_date >= today - timedelta(days=7))
        .order_by(KpiSnapshot.snapshot_date.asc())
    )
    week_snaps = week_rows.scalars().all()

    # Recent audit logs
    recent_logs = await db.execute(
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(15)
    )
    recent = recent_logs.scalars().all()

    lines = [f"## Live Velluto Autopilot Context — {now.strftime('%Y-%m-%d %H:%M UTC')}\n"]

    if snap:
        lines.append("### Today's KPIs")
        lines.append(f"- Revenue: €{snap.revenue_eur or 0:.2f}")
        lines.append(f"- Orders: {snap.orders_count or 0}")
        lines.append(f"- Ad spend: €{snap.ad_spend_eur or 0:.2f}")
        lines.append(f"- ROAS: {snap.ad_roas or 0:.2f}×")
        lines.append(f"- Shopify sessions: {snap.shopify_sessions or 0}")
        lines.append(f"- Conversion rate: {snap.conversion_rate or 0:.2f}%")
        raw = snap.raw or {}
        atc = raw.get("meta", {}).get("atc_count", 0)
        cpa = raw.get("meta", {}).get("cost_per_atc", 0)
        lines.append(f"- ATC events: {atc}  |  Cost/ATC: €{cpa:.2f}")

    if week_snaps:
        lines.append("\n### 7-Day Revenue Trend")
        for s in week_snaps[-7:]:
            lines.append(f"  {s.snapshot_date}: €{s.revenue_eur or 0:.0f} rev, "
                         f"{s.orders_count or 0} orders, €{s.ad_spend_eur or 0:.0f} spend")

    if recent:
        lines.append("\n### Recent Agent Actions (last 15)")
        for log_entry in recent:
            ts = log_entry.created_at.strftime("%H:%M") if log_entry.created_at else "?"
            lines.append(f"  [{ts}] {log_entry.agent or '?'} — {log_entry.action or '?'}: "
                         f"{str(log_entry.result or '')[:80]}")

    return "\n".join(lines)


CHAT_SYSTEM = """You are the Velluto Autopilot AI assistant — a senior growth advisor for Velluto, a premium Dutch road cycling eyewear brand.

You have access to live KPI data, agent activity logs, and campaign data provided in the context below.

Your role:
- Answer questions about performance, trends, and strategy with concrete data references
- Explain what the autopilot agents are doing and why
- Suggest actionable next steps grounded in the current data
- Be direct and concise — this is a founder-level dashboard, not a report
- When you don't know something or data is missing, say so clearly

Brand context:
- Products: StradaPro cycling glasses, interchangeable lenses (VellutoVisione, VellutoPuro), accessories
- Price point: €149 for glasses, €39.90 VellutoVisione, €19.90 VellutoPuro
- Current phase: pixel training with ATC campaigns (building toward 50 purchase events before switching objectives)
- Markets: Netherlands (primary), expanding across Europe in 10 languages

Keep answers focused. Use € for currency. Reference specific numbers from the context when answering."""


@router.post("")
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    context = await _build_context(db)
    system_with_context = f"{CHAT_SYSTEM}\n\n{context}"

    claude = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    if request.stream:
        async def generate():
            async with claude.messages.stream(
                model=settings.anthropic_model,
                max_tokens=1024,
                system=system_with_context,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    # Server-sent events format
                    yield f"data: {text}\n\n".encode()
            yield b"data: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})
    else:
        response = await claude.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=system_with_context,
            messages=messages,
        )
        return {"reply": response.content[0].text,
                "usage": {"input": response.usage.input_tokens,
                          "output": response.usage.output_tokens}}

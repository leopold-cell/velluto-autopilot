"""
Approval Engine — routes high-risk actions through WhatsApp confirmation.

Risk levels:
  low      → auto-execute immediately
  medium   → auto-execute with audit log + WhatsApp notification
  high     → require WhatsApp approval before executing
  critical → require WhatsApp approval + dry-run preview in message
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval, ApprovalStatus

log = structlog.get_logger()

# Actions that always require approval regardless of thresholds
HIGH_RISK_ACTIONS = frozenset(
    {
        "update_product_price",
        "create_discount",
        "update_discount",
        "increase_ad_budget",
        "update_checkout",
        "update_homepage",
        "add_legal_claim",
        "update_product_guarantee",
        "send_mass_email",
        "create_bundle",
        "update_bundle",
        "delete_product",
        "archive_product",
    }
)

APPROVAL_TIMEOUT_HOURS = 4


def classify_risk(action: str, payload: dict) -> str:
    if action in HIGH_RISK_ACTIONS:
        return "high"

    # Budget changes over threshold are high risk
    if action == "adjust_meta_budget":
        change_pct = abs(payload.get("change_pct", 0))
        from app.config import settings
        if change_pct > settings.max_auto_budget_change_pct:
            return "high"
        return "medium"

    if action in {"update_product_seo", "generate_ad_creative", "update_collection_description"}:
        return "low"

    return "medium"


class ApprovalEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def request(
        self,
        action: str,
        module: str,
        payload: dict,
        reason: str,
        dry_run_result: dict | None = None,
        executor: Callable[[dict], Awaitable[Any]] | None = None,
    ) -> dict[str, Any]:
        risk = classify_risk(action, payload)

        if risk == "low":
            return await self._auto_execute(action, module, payload, executor)

        if risk == "medium":
            result = await self._auto_execute(action, module, payload, executor)
            await self._notify_whatsapp(action, module, payload, reason, risk, result)
            return result

        # high / critical → create pending approval
        approval = Approval(
            action=action,
            module=module,
            risk_level=risk,
            payload=payload,
            reason=reason,
            status=ApprovalStatus.pending,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=APPROVAL_TIMEOUT_HOURS),
            dry_run_result=dry_run_result,
        )
        self.db.add(approval)
        await self.db.commit()
        await self.db.refresh(approval)

        await self._send_approval_request(approval)

        log.info(
            "approval.pending",
            approval_id=str(approval.id),
            action=action,
            risk=risk,
        )
        return {
            "status": "pending_approval",
            "approval_id": str(approval.id),
            "risk_level": risk,
            "expires_at": approval.expires_at.isoformat(),
        }

    async def resolve(
        self,
        approval_id: uuid.UUID,
        decision: str,
        resolved_by: str,
        rejection_reason: str | None = None,
        executor: Callable[[dict], Awaitable[Any]] | None = None,
    ) -> dict[str, Any]:
        from sqlalchemy import select

        result = await self.db.execute(select(Approval).where(Approval.id == approval_id))
        approval = result.scalar_one_or_none()

        if not approval:
            return {"error": "approval_not_found"}

        if approval.status != ApprovalStatus.pending:
            return {"error": "approval_already_resolved", "status": approval.status}

        if approval.expires_at and datetime.now(timezone.utc) > approval.expires_at:
            approval.status = ApprovalStatus.expired
            await self.db.commit()
            return {"error": "approval_expired"}

        approval.resolved_at = datetime.now(timezone.utc)
        approval.resolved_by = resolved_by

        if decision == "approve":
            approval.status = ApprovalStatus.approved
            await self.db.commit()

            exec_result = None
            if executor:
                exec_result = await executor(approval.payload)

            log.info("approval.approved", approval_id=str(approval_id), action=approval.action)
            return {"status": "approved", "result": exec_result}

        approval.status = ApprovalStatus.rejected
        approval.rejection_reason = rejection_reason
        await self.db.commit()

        log.info("approval.rejected", approval_id=str(approval_id), action=approval.action)
        return {"status": "rejected", "reason": rejection_reason}

    async def _auto_execute(
        self,
        action: str,
        module: str,
        payload: dict,
        executor: Callable[[dict], Awaitable[Any]] | None,
    ) -> dict[str, Any]:
        if executor:
            result = await executor(payload)
            return {"status": "auto_executed", "result": result}
        return {"status": "auto_executed", "result": None}

    async def _notify_whatsapp(
        self,
        action: str,
        module: str,
        payload: dict,
        reason: str,
        risk: str,
        result: dict,
    ) -> None:
        try:
            from app.modules.whatsapp.client import WhatsAppClient
            client = WhatsAppClient()
            message = (
                f"✅ *Auto-executed [{risk.upper()}]*\n"
                f"Action: `{action}`\n"
                f"Module: {module}\n"
                f"Reason: {reason}"
            )
            await client.send_text(message)
        except Exception as e:
            log.warning("whatsapp.notification_failed", error=str(e))

    async def _send_approval_request(self, approval: Approval) -> None:
        try:
            from app.modules.whatsapp.approval import send_approval_request
            await send_approval_request(approval)
        except Exception as e:
            log.error("approval.whatsapp_send_failed", approval_id=str(approval.id), error=str(e))

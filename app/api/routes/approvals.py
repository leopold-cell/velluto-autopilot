from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engines.approval import ApprovalEngine
from app.models.approval import Approval, ApprovalStatus

router = APIRouter()


class ResolveRequest(BaseModel):
    decision: str  # "approve" | "reject"
    resolved_by: str = "operator"
    rejection_reason: str | None = None


@router.get("")
async def list_approvals(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
):
    q = select(Approval).order_by(Approval.created_at.desc()).limit(limit)
    if status:
        q = q.where(Approval.status == status)
    result = await db.execute(q)
    approvals = result.scalars().all()
    return {
        "approvals": [
            {
                "id": str(a.id),
                "action": a.action,
                "module": a.module,
                "risk_level": a.risk_level,
                "status": a.status,
                "reason": a.reason,
                "created_at": a.created_at.isoformat(),
                "expires_at": a.expires_at.isoformat() if a.expires_at else None,
            }
            for a in approvals
        ]
    }


@router.get("/{approval_id}")
async def get_approval(approval_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Approval).where(Approval.id == approval_id))
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(404, "Approval not found")
    return {
        "id": str(approval.id),
        "action": approval.action,
        "module": approval.module,
        "risk_level": approval.risk_level,
        "status": approval.status,
        "payload": approval.payload,
        "reason": approval.reason,
        "dry_run_result": approval.dry_run_result,
        "created_at": approval.created_at.isoformat(),
        "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
        "resolved_at": approval.resolved_at.isoformat() if approval.resolved_at else None,
        "resolved_by": approval.resolved_by,
    }


@router.post("/{approval_id}/resolve")
async def resolve_approval(
    approval_id: uuid.UUID,
    body: ResolveRequest,
    db: AsyncSession = Depends(get_db),
):
    if body.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be 'approve' or 'reject'")

    engine = ApprovalEngine(db)

    async def _execute(payload: dict):
        from app.orchestrator.agent import Orchestrator
        orch = Orchestrator()
        return await orch._dispatch_tool(
            tool_name=payload.get("action", ""),
            tool_input=payload,
            action_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            db=db,
            approval_engine=engine,
            rollback_engine=__import__("app.engines.rollback", fromlist=["RollbackEngine"]).RollbackEngine(db),
            dry_run=False,
        )

    return await engine.resolve(
        approval_id=approval_id,
        decision=body.decision,
        resolved_by=body.resolved_by,
        rejection_reason=body.rejection_reason,
        executor=_execute if body.decision == "approve" else None,
    )

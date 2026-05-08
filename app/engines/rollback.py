"""
Rollback Engine — every mutation registers an inverse operation.
Call RollbackEngine.register() after each successful action.
Call RollbackEngine.rollback(action_id) to undo it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rollback import RollbackRecord

log = structlog.get_logger()

# Registry: module → action → async inverse function
_INVERSE_REGISTRY: dict[str, dict[str, Callable]] = {}


def register_inverse(module: str, action: str):
    """Decorator to register an inverse function for an action."""
    def decorator(fn: Callable):
        _INVERSE_REGISTRY.setdefault(module, {})[action] = fn
        return fn
    return decorator


class RollbackEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(
        self,
        action_id: uuid.UUID,
        action: str,
        module: str,
        forward_payload: dict,
        inverse_action: str,
        inverse_payload: dict,
    ) -> RollbackRecord:
        record = RollbackRecord(
            action_id=action_id,
            action=action,
            module=module,
            forward_payload=forward_payload,
            inverse_action=inverse_action,
            inverse_payload=inverse_payload,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        log.info("rollback.registered", action_id=str(action_id), action=action)
        return record

    async def rollback(self, action_id: uuid.UUID, rolled_back_by: str = "operator") -> dict[str, Any]:
        result = await self.db.execute(
            select(RollbackRecord).where(
                RollbackRecord.action_id == action_id,
                RollbackRecord.rolled_back == False,  # noqa: E712
            )
        )
        record = result.scalar_one_or_none()

        if not record:
            return {"error": "rollback_record_not_found_or_already_rolled_back"}

        module_inverses = _INVERSE_REGISTRY.get(record.module, {})
        inverse_fn = module_inverses.get(record.inverse_action)

        if not inverse_fn:
            return {
                "error": "no_inverse_function_registered",
                "module": record.module,
                "inverse_action": record.inverse_action,
            }

        try:
            result_data = await inverse_fn(record.inverse_payload)
            record.rolled_back = True
            record.rolled_back_at = datetime.now(timezone.utc)
            record.rolled_back_by = rolled_back_by
            await self.db.commit()

            log.info(
                "rollback.success",
                action_id=str(action_id),
                action=record.action,
                inverse=record.inverse_action,
            )
            return {"status": "rolled_back", "result": result_data}

        except Exception as e:
            record.rollback_error = str(e)
            await self.db.commit()
            log.error("rollback.failed", action_id=str(action_id), error=str(e))
            return {"error": "rollback_failed", "detail": str(e)}

    async def rollback_last_n_hours(self, hours: int, rolled_back_by: str = "operator") -> list[dict]:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.db.execute(
            select(RollbackRecord).where(
                RollbackRecord.created_at >= cutoff,
                RollbackRecord.rolled_back == False,  # noqa: E712
            ).order_by(RollbackRecord.created_at.desc())
        )
        records = result.scalars().all()

        results = []
        for record in records:
            rb = await self.rollback(record.action_id, rolled_back_by=rolled_back_by)
            results.append({"action_id": str(record.action_id), **rb})

        return results

    async def list_pending(self) -> list[dict]:
        result = await self.db.execute(
            select(RollbackRecord)
            .where(RollbackRecord.rolled_back == False)  # noqa: E712
            .order_by(RollbackRecord.created_at.desc())
            .limit(50)
        )
        records = result.scalars().all()
        return [
            {
                "action_id": str(r.action_id),
                "action": r.action,
                "module": r.module,
                "created_at": r.created_at.isoformat(),
                "forward_payload": r.forward_payload,
            }
            for r in records
        ]

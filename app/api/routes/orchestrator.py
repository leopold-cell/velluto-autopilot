from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.task import Task, TaskStatus
from app.orchestrator.agent import Orchestrator
from app.orchestrator.optimizer import SystemOptimizer

router = APIRouter()


class RunCycleRequest(BaseModel):
    dry_run: bool = False
    focus: str | None = None
    trigger: str = "api"


@router.post("/run")
async def run_cycle(
    body: RunCycleRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger an orchestration cycle. Runs in background, returns task_id immediately."""
    task_id = uuid.uuid4()
    orchestrator = Orchestrator()

    async def _run():
        await orchestrator.run_cycle(
            task_id=task_id,
            trigger=body.trigger,
            dry_run=body.dry_run,
            focus=body.focus,
        )

    background_tasks.add_task(_run)
    return {"task_id": str(task_id), "status": "queued"}


@router.post("/run/sync")
async def run_cycle_sync(body: RunCycleRequest, db: AsyncSession = Depends(get_db)):
    """Run orchestration synchronously and return result. Use for testing only."""
    task_id = uuid.uuid4()
    result = await Orchestrator().run_cycle(
        task_id=task_id,
        trigger=body.trigger,
        dry_run=body.dry_run,
        focus=body.focus,
    )
    return {"task_id": str(task_id), **result}


@router.get("/tasks")
async def list_tasks(db: AsyncSession = Depends(get_db), limit: int = 20):
    result = await db.execute(
        select(Task).order_by(Task.created_at.desc()).limit(limit)
    )
    tasks = result.scalars().all()
    return {
        "tasks": [
            {
                "id": str(t.id),
                "name": t.name,
                "status": t.status,
                "trigger": t.trigger,
                "created_at": t.created_at.isoformat(),
                "actions_executed": t.actions_executed,
                "total_tokens": t.total_tokens,
            }
            for t in tasks
        ]
    }


@router.get("/tasks/{task_id}")
async def get_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    return {
        "id": str(task.id),
        "name": task.name,
        "status": task.status,
        "result": task.result,
        "error": task.error,
        "total_tokens": task.total_tokens,
        "actions_executed": task.actions_executed,
        "created_at": task.created_at.isoformat(),
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


@router.get("/efficiency")
async def get_efficiency(days: int = 7, db: AsyncSession = Depends(get_db)):
    optimizer = SystemOptimizer(db)
    return await optimizer.get_efficiency_report(days=days)


@router.post("/rollback/{action_id}")
async def rollback_action(action_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from app.engines.rollback import RollbackEngine
    engine = RollbackEngine(db)
    return await engine.rollback(action_id, rolled_back_by="api")

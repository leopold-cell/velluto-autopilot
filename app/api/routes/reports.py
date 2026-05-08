from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.kpi.engine import KpiEngine
from app.modules.token_optimizer.optimizer import TokenOptimizer
from app.orchestrator.optimizer import SystemOptimizer

router = APIRouter()


@router.get("/kpi")
async def kpi_dashboard(db: AsyncSession = Depends(get_db)):
    engine = KpiEngine(db)
    return await engine.get_dashboard()


@router.get("/kpi/trend")
async def kpi_trend(days: int = 7, db: AsyncSession = Depends(get_db)):
    engine = KpiEngine(db)
    return {"trend": await engine.get_trend(days=days)}


@router.post("/kpi/snapshot")
async def force_snapshot(db: AsyncSession = Depends(get_db)):
    engine = KpiEngine(db)
    snap = await engine.capture_snapshot()
    return {"captured": True, "snapshot_id": str(snap.id), "orders": snap.orders_count}


@router.get("/tokens")
async def token_usage():
    optimizer = TokenOptimizer()
    return {
        "today": await optimizer.get_daily_report(),
        "week": await optimizer.get_weekly_cost_summary(),
    }


@router.get("/efficiency")
async def efficiency(days: int = 7, db: AsyncSession = Depends(get_db)):
    optimizer = SystemOptimizer(db)
    return await optimizer.get_efficiency_report(days=days)


@router.get("/rollback/pending")
async def pending_rollbacks(db: AsyncSession = Depends(get_db)):
    from app.engines.rollback import RollbackEngine
    engine = RollbackEngine(db)
    return {"pending": await engine.list_pending()}

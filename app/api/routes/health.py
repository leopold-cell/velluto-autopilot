from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engines.monitoring import MonitoringEngine

router = APIRouter()


@router.get("")
async def health(db: AsyncSession = Depends(get_db)):
    monitor = MonitoringEngine(db)
    return await monitor.run_health_checks()


@router.get("/ping")
async def ping():
    return {"status": "ok"}

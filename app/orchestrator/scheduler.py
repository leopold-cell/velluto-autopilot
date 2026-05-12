"""
APScheduler — runs the orchestrator on schedule.
Jobs:
  - Every hour: full orchestration cycle
  - 08:30 Europe/Berlin: daily report
  - Every 6h: KPI snapshot
  - Weekly Monday 07:00: competitor scan
"""

from __future__ import annotations

import asyncio
import signal

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

log = structlog.get_logger()


async def job_orchestrate(focus: str | None = None):
    from app.orchestrator.agent import Orchestrator
    log.info("scheduler.job_start", job="orchestrate", focus=focus)
    try:
        result = await Orchestrator().run_cycle(trigger="scheduler", focus=focus)
        log.info("scheduler.job_done", job="orchestrate", actions=result.get("actions_executed"))
    except Exception as e:
        log.error("scheduler.job_failed", job="orchestrate", error=str(e))


async def job_daily_report():
    from app.workers.daily_report import generate_and_send
    log.info("scheduler.job_start", job="daily_report")
    try:
        await generate_and_send()
    except Exception as e:
        log.error("scheduler.job_failed", job="daily_report", error=str(e))


async def job_kpi_snapshot():
    from app.database import AsyncSessionLocal
    from app.modules.kpi.engine import KpiEngine
    log.info("scheduler.job_start", job="kpi_snapshot")
    try:
        async with AsyncSessionLocal() as db:
            snap = await KpiEngine(db).capture_snapshot()
            log.info("scheduler.kpi_captured", orders=snap.orders_count, revenue=snap.revenue_eur)
    except Exception as e:
        log.error("scheduler.job_failed", job="kpi_snapshot", error=str(e))


async def job_competitor_scan():
    from app.modules.competitor.tools import competitor_scan
    log.info("scheduler.job_start", job="competitor_scan")
    try:
        result = await competitor_scan()
        changes = result.get("total_changes", 0)
        if changes > 0:
            from app.modules.whatsapp.client import WhatsAppClient
            await WhatsAppClient().send_text(
                f"🔍 *Competitor Alert*\n{changes} changes detected across competitors."
            )
    except Exception as e:
        log.error("scheduler.job_failed", job="competitor_scan", error=str(e))


async def job_clarity_analysis():
    from app.modules.clarity.agent import run_clarity_analysis
    log.info("scheduler.job_start", job="clarity_analysis")
    try:
        result = await run_clarity_analysis()
        log.info("scheduler.job_done", job="clarity_analysis",
                 health=result.get("health_score"), blockers=len(result.get("conversion_blockers", [])))
    except Exception as e:
        log.error("scheduler.job_failed", job="clarity_analysis", error=str(e))


async def job_meta_orchestration():
    from app.orchestrator.meta_orchestrator import run_meta_orchestration
    log.info("scheduler.job_start", job="meta_orchestration")
    try:
        report = await run_meta_orchestration()
        score = (report.get("system_health") or {}).get("score", "?")
        log.info("scheduler.job_done", job="meta_orchestration", system_score=score)
    except Exception as e:
        log.error("scheduler.job_failed", job="meta_orchestration", error=str(e))


async def job_health_check():
    from app.database import AsyncSessionLocal
    from app.engines.monitoring import MonitoringEngine
    async with AsyncSessionLocal() as db:
        monitor = MonitoringEngine(db)
        health = await monitor.run_health_checks()
        if not health["healthy"]:
            failing = [k for k, v in health["checks"].items() if not v["healthy"]]
            await monitor.alert_critical(
                f"Health check failed: {', '.join(failing)}",
                context=health["checks"],
            )


def build_scheduler() -> AsyncIOScheduler:
    tz = settings.daily_report_timezone
    hour, minute = settings.daily_report_time.split(":")

    scheduler = AsyncIOScheduler(timezone=tz)

    # Hourly orchestration
    scheduler.add_job(job_orchestrate, "interval", hours=1, id="orchestrate_hourly")

    # Daily report at configured time
    scheduler.add_job(
        job_daily_report,
        CronTrigger(hour=int(hour), minute=int(minute), timezone=tz),
        id="daily_report",
    )

    # KPI snapshots every 6 hours
    scheduler.add_job(job_kpi_snapshot, "interval", hours=6, id="kpi_snapshot")

    # Competitor scan — Monday 07:00
    scheduler.add_job(
        job_competitor_scan,
        CronTrigger(day_of_week="mon", hour=7, minute=0, timezone=tz),
        id="competitor_scan_weekly",
    )

    # Clarity behavioral analysis every 6 hours
    scheduler.add_job(job_clarity_analysis, "interval", hours=6, id="clarity_analysis")

    # Meta-orchestrator daily at 05:00 — system-wide analysis + QA improvement
    scheduler.add_job(
        job_meta_orchestration,
        CronTrigger(hour=5, minute=0, timezone=tz),
        id="meta_orchestration_daily",
    )

    # Health check every 15 minutes
    scheduler.add_job(job_health_check, "interval", minutes=15, id="health_check")

    return scheduler


async def main():
    scheduler = build_scheduler()
    scheduler.start()
    log.info(
        "scheduler.started",
        jobs=[job.id for job in scheduler.get_jobs()],
        timezone=settings.daily_report_timezone,
    )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _stop(*_):
        stop_event.set()

    loop.add_signal_handler(signal.SIGTERM, _stop)
    loop.add_signal_handler(signal.SIGINT, _stop)

    await stop_event.wait()
    scheduler.shutdown()
    log.info("scheduler.stopped")


if __name__ == "__main__":
    asyncio.run(main())

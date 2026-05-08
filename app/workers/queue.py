"""
Redis queue worker — processes background jobs from the email_flow_queue and task_queue.
Runs as a separate process: `python -m app.workers.queue`
"""

from __future__ import annotations

import asyncio
import json
import signal
from datetime import datetime, timezone

import structlog

from app.redis_client import get_redis

log = structlog.get_logger()


async def process_email_flow_queue():
    """Process queued email flow steps when their delay has elapsed."""
    r = await get_redis()
    while True:
        try:
            # Non-blocking pop
            item = await r.lpop("email_flow_queue")
            if not item:
                await asyncio.sleep(60)
                continue

            job = json.loads(item)
            queued_at = datetime.fromisoformat(job["queued_at"])
            delay_hours = job.get("send_after_hours", 1)
            send_after = queued_at.replace(tzinfo=timezone.utc)

            from datetime import timedelta
            if datetime.now(timezone.utc) < send_after + timedelta(hours=delay_hours):
                # Not yet — re-queue
                await r.rpush("email_flow_queue", item)
                await asyncio.sleep(300)  # check again in 5 min
                continue

            # Time to send
            from app.modules.email_marketing.flows import generate_flow_email, trigger_flow
            from app.modules.email_marketing.client import EmailClient

            content = await generate_flow_email(
                flow_name=job["flow_name"],
                step=job["step"],
                customer_context=job["customer_context"],
            )
            ec = EmailClient()
            await ec.send_transactional(
                to_email=job["customer_email"],
                subject=content.get("subject", "From Velluto"),
                html_content=content.get("html_body", ""),
            )
            log.info(
                "worker.email_flow_sent",
                flow=job["flow_name"],
                step=job["step"],
                to=job["customer_email"],
            )

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("worker.email_flow_error", error=str(e))
            await asyncio.sleep(30)


async def process_task_queue():
    """Process generic async tasks from the task_queue."""
    r = await get_redis()
    while True:
        try:
            item = await r.blpop("task_queue", timeout=30)
            if not item:
                continue

            _, raw = item
            job = json.loads(raw)
            task_type = job.get("type")

            if task_type == "orchestrate":
                from app.orchestrator.agent import Orchestrator
                await Orchestrator().run_cycle(
                    trigger="queue",
                    dry_run=job.get("dry_run", False),
                    focus=job.get("focus"),
                )
            else:
                log.warning("worker.unknown_task_type", task_type=task_type)

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("worker.task_queue_error", error=str(e))
            await asyncio.sleep(10)


async def main():
    log.info("worker.starting")
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()

    def _stop(*_):
        stop_event.set()

    loop.add_signal_handler(signal.SIGTERM, _stop)
    loop.add_signal_handler(signal.SIGINT, _stop)

    tasks = [
        asyncio.create_task(process_email_flow_queue()),
        asyncio.create_task(process_task_queue()),
    ]

    await stop_event.wait()

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    log.info("worker.stopped")


if __name__ == "__main__":
    asyncio.run(main())

"""Daily job. Run: python -m idearadar.scheduler  (cron 05:00 UTC; --once runs immediately)."""
import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from .collectors.hackernews import HackerNewsCollector
from .collectors.youtube import YouTubeCollector
from .config import get_settings
from .db import make_session_factory
from .llm import ClaudeLLM
from .pipeline import run_daily


def job() -> None:
    cfg = get_settings()
    session = make_session_factory(cfg.database_url)()
    try:
        collectors = [HackerNewsCollector(), YouTubeCollector(cfg.youtube_api_key)]
        ideas = run_daily(session, collectors, ClaudeLLM(session, cfg), cfg)
        logging.info("created %d pending ideas for approval", len(ideas))
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if "--once" in sys.argv:
        job()
    else:
        sched = BlockingScheduler(timezone="UTC")
        sched.add_job(job, "cron", hour=5, minute=0)
        sched.start()

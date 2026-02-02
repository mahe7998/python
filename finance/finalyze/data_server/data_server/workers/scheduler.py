"""APScheduler setup for background workers."""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from data_server.config import get_settings
from data_server.workers.price_worker import update_prices
from data_server.workers.news_worker import update_news

logger = logging.getLogger(__name__)
settings = get_settings()

# Global scheduler instance
scheduler: AsyncIOScheduler | None = None


async def start_scheduler():
    """Start the background job scheduler."""
    global scheduler

    scheduler = AsyncIOScheduler()

    # Price worker - runs every 15 seconds during market hours
    scheduler.add_job(
        update_prices,
        trigger=IntervalTrigger(seconds=settings.worker_price_interval),
        id="price_worker",
        name="Price Update Worker",
        replace_existing=True,
        max_instances=1,
    )

    # News worker - runs every 15 minutes
    scheduler.add_job(
        update_news,
        trigger=IntervalTrigger(seconds=settings.worker_news_interval),
        id="news_worker",
        name="News Update Worker",
        replace_existing=True,
        max_instances=1,
    )

    # Daily worker - runs at 4:30 PM ET (21:30 UTC)
    # Parse time from settings
    hour, minute = map(int, settings.worker_daily_time.split(":"))
    scheduler.add_job(
        daily_cleanup,
        trigger=CronTrigger(hour=hour + 5, minute=minute),  # Convert ET to UTC
        id="daily_worker",
        name="Daily Cleanup Worker",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info("Background scheduler started")


async def stop_scheduler():
    """Stop the background job scheduler."""
    global scheduler

    if scheduler:
        scheduler.shutdown(wait=False)
        scheduler = None
        logger.info("Background scheduler stopped")


async def daily_cleanup():
    """Daily cleanup task - remove old intraday data."""
    from sqlalchemy import delete
    from datetime import timedelta
    from data_server.db.database import async_session_factory
    from data_server.db.models import IntradayPrice

    logger.info("Running daily cleanup...")

    async with async_session_factory() as session:
        # Delete intraday data older than 7 days
        cutoff = datetime.utcnow() - timedelta(days=7)
        result = await session.execute(
            delete(IntradayPrice).where(IntradayPrice.timestamp < cutoff)
        )
        await session.commit()

        logger.info(f"Deleted {result.rowcount} old intraday records")


def get_scheduler_status() -> dict:
    """Get scheduler status information."""
    if not scheduler:
        return {"running": False, "jobs": []}

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            }
        )

    return {
        "running": scheduler.running,
        "jobs": jobs,
    }

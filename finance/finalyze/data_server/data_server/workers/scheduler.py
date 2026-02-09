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

    # NOTE: Delayed intraday worker removed - EODHD doesn't provide intraday data
    # during market hours. We now use OHLC aggregation from live prices instead.

    # News worker - runs every 15 minutes, starting immediately on startup
    scheduler.add_job(
        update_news,
        trigger=IntervalTrigger(seconds=settings.worker_news_interval),
        id="news_worker",
        name="News Update Worker",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.utcnow(),  # Run immediately on startup
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

    # Fundamentals worker - runs once daily at 5:00 AM ET (10:00 UTC) before market open
    # Updates shares_outstanding for accurate market cap calculation
    scheduler.add_job(
        update_fundamentals,
        trigger=CronTrigger(hour=10, minute=0),  # 5:00 AM ET = 10:00 UTC
        id="fundamentals_worker",
        name="Daily Fundamentals Worker",
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


async def update_fundamentals():
    """Update fundamentals (shares outstanding, etc.) for all tracked stocks.

    Runs once daily to keep shares_outstanding current for accurate market cap calculation.
    After EODHD update, also fetches SEC EDGAR shares history and yfinance fallback.
    """
    from data_server.db.database import async_session_factory
    from data_server.db import cache
    from data_server.api.tracking import get_tracked_tickers
    from data_server.services.eodhd_client import get_eodhd_client

    logger.info("Starting daily fundamentals update...")

    async with async_session_factory() as session:
        tickers = await get_tracked_tickers(session)

    if not tickers:
        logger.debug("No tracked stocks for fundamentals update")
        return

    client = await get_eodhd_client()
    updated_count = 0

    for symbol in tickers:
        ticker = symbol.split(".")[0]
        exchange = symbol.split(".")[-1] if "." in symbol else "US"

        try:
            data = await client.get_fundamentals(symbol)
            if not data:
                continue

            general = data.get("General", {})
            highlights = data.get("Highlights", {})
            shares_stats = data.get("SharesStats", {})

            company_data = {
                "ticker": ticker,
                "name": general.get("Name"),
                "exchange": general.get("Exchange"),
                "sector": general.get("Sector"),
                "industry": general.get("Industry"),
                "market_cap": highlights.get("MarketCapitalization"),
                "shares_outstanding": shares_stats.get("SharesOutstanding"),
                "pe_ratio": highlights.get("PERatio"),
                "eps": highlights.get("EarningsShare"),
            }

            async with async_session_factory() as session:
                await cache.store_company(session, company_data)
                await cache.store_company_highlights(session, ticker, data)
                await session.commit()

            updated_count += 1
            logger.debug(f"Updated EODHD fundamentals for {symbol}")

        except Exception as e:
            logger.error(f"Error updating fundamentals for {symbol}: {e}")

    logger.info(f"Daily fundamentals update complete: {updated_count}/{len(tickers)} stocks")

    # Phase 2: Fetch SEC EDGAR shares history for all tracked tickers
    await _update_shares_history(tickers)


async def _update_shares_history(tickers: list[str]):
    """Fetch shares history from SEC EDGAR (+ yfinance fallback) for tracked tickers."""
    from data_server.db.database import async_session_factory
    from data_server.db import cache
    from data_server.services.sec_edgar import get_sec_edgar_client
    from data_server.services import yfinance_client

    logger.info("Starting shares history update...")
    sec_client = await get_sec_edgar_client()
    updated_count = 0

    for symbol in tickers:
        ticker = symbol.split(".")[0]
        exchange = symbol.split(".")[-1] if "." in symbol else "US"

        try:
            # Try SEC EDGAR first
            entries = await sec_client.get_shares_history(ticker)

            # Fallback to yfinance if SEC EDGAR returned nothing
            if not entries:
                yf_entry = await yfinance_client.get_shares_history_entry(ticker, exchange)
                if yf_entry:
                    entries = [yf_entry]

            if entries:
                async with async_session_factory() as session:
                    await cache.store_shares_history(session, ticker, entries)
                    await cache.update_cache_metadata(
                        session, f"shares_history:{ticker}",
                        "shares_history", ticker, 86400, len(entries),
                    )

                    # Update company_highlights with best shares value
                    best_shares = await cache.get_latest_shares_outstanding(session, ticker)
                    if best_shares:
                        from sqlalchemy.dialects.postgresql import insert as pg_insert
                        from data_server.db.models import CompanyHighlight
                        stmt = (
                            pg_insert(CompanyHighlight)
                            .values(ticker=ticker, shares_outstanding=best_shares, updated_at=datetime.utcnow())
                            .on_conflict_do_update(
                                index_elements=["ticker"],
                                set_={"shares_outstanding": best_shares, "updated_at": datetime.utcnow()},
                            )
                        )
                        await session.execute(stmt)

                    await session.commit()
                updated_count += 1
                logger.debug(f"Updated shares history for {ticker}: {len(entries)} entries")

        except Exception as e:
            logger.error(f"Error updating shares history for {ticker}: {e}")

    logger.info(f"Shares history update complete: {updated_count}/{len(tickers)} stocks")


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

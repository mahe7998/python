"""APScheduler setup for background workers."""

import logging
from datetime import datetime
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from sqlalchemy import select

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

ET_TZ = ZoneInfo("America/New_York")

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

    # News worker - runs once daily at 6:00 AM ET (DST-aware)
    # Individual stock news is fetched on-demand when viewing news tab
    # On startup, check if today's sweep already ran; if not, run immediately
    news_run_time = None
    try:
        news_run_time = await _get_last_news_sweep_time()
    except Exception as e:
        logger.warning(f"Could not check last news sweep: {e}")

    today = datetime.utcnow().date()
    needs_startup_run = (
        news_run_time is None or news_run_time.date() < today
    )

    scheduler.add_job(
        update_news,
        trigger=CronTrigger(hour=6, minute=0, timezone=ET_TZ),
        id="news_worker",
        name="Daily News Worker",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
        next_run_time=datetime.utcnow() if needs_startup_run else None,
    )
    if needs_startup_run:
        logger.info("News sweep not yet done today — scheduling immediate run")

    # Daily worker - runs at configured ET time (default 4:30 PM ET, DST-aware)
    hour, minute = map(int, settings.worker_daily_time.split(":"))
    scheduler.add_job(
        daily_cleanup,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=ET_TZ),
        id="daily_worker",
        name="Daily Cleanup Worker",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # EOD refresh worker - runs at 4:45 PM ET after US market close (DST-aware)
    # Invalidates daily price caches so next request fetches fresh EOD data
    # misfire_grace_time=3600: allow up to 1 hour late execution (APScheduler default is 1s)
    scheduler.add_job(
        refresh_eod_caches,
        trigger=CronTrigger(hour=16, minute=45, timezone=ET_TZ),
        id="eod_refresh_worker",
        name="EOD Refresh Worker",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # Fundamentals worker - runs once daily at 5:00 AM ET before market open (DST-aware)
    # Updates shares_outstanding for accurate market cap calculation
    scheduler.add_job(
        update_fundamentals,
        trigger=CronTrigger(hour=5, minute=0, timezone=ET_TZ),
        id="fundamentals_worker",
        name="Daily Fundamentals Worker",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info("Background scheduler started")


async def _get_last_news_sweep_time() -> Optional[datetime]:
    """Check the most recent last_news_update across all tracked stocks."""
    from sqlalchemy import func
    from data_server.db.database import async_session_factory
    from data_server.db.models import TrackedStock

    async with async_session_factory() as session:
        result = await session.execute(
            select(func.max(TrackedStock.last_news_update))
        )
        return result.scalar()


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


async def refresh_eod_caches():
    """Fetch fresh daily prices, invalidate caches, and sync LivePrice.

    Runs after US market close. Three steps:
    1. Fetch fresh EOD daily prices for all tracked stocks from EODHD API.
    2. Invalidate daily price cache metadata so next request fetches fresh data.
    3. Update LivePrice table from daily_prices so live data reflects final closes.
    """
    from datetime import datetime, date as date_type
    from decimal import Decimal
    from sqlalchemy import delete, select, func, and_
    from data_server.db.database import async_session_factory
    from data_server.db.models import CacheMetadata, LivePrice, DailyPrice
    from data_server.workers.price_worker import update_daily_prices

    logger.info("EOD refresh: fetching daily prices, invalidating caches, syncing LivePrice...")

    # Step 1: Fetch fresh daily prices for all tracked stocks
    try:
        await update_daily_prices()
    except Exception as e:
        logger.error(f"EOD refresh: daily price fetch failed: {e}")

    async with async_session_factory() as session:
        # Step 2: Invalidate EOD cache metadata
        result = await session.execute(
            delete(CacheMetadata).where(CacheMetadata.cache_key.startswith("eod:"))
        )
        deleted = result.rowcount
        logger.info(f"Invalidated {deleted} EOD cache entries")

        # Step 3: Update LivePrice from latest daily_prices
        result = await session.execute(select(LivePrice))
        prices = result.scalars().all()
        if not prices:
            await session.commit()
            return

        live_by_ticker = {p.ticker: p for p in prices}

        latest_dates_subq = (
            select(
                DailyPrice.ticker,
                func.max(DailyPrice.date).label("max_date"),
            )
            .where(DailyPrice.ticker.in_(list(live_by_ticker.keys())))
            .group_by(DailyPrice.ticker)
            .subquery()
        )
        latest_daily = await session.execute(
            select(DailyPrice).join(
                latest_dates_subq,
                and_(
                    DailyPrice.ticker == latest_dates_subq.c.ticker,
                    DailyPrice.date == latest_dates_subq.c.max_date,
                ),
            )
        )

        updated_count = 0
        for dp in latest_daily.scalars().all():
            lp = live_by_ticker.get(dp.ticker)
            if not lp or dp.close is None:
                continue

            lp_date = lp.market_timestamp.date() if lp.market_timestamp else date_type.min
            dp_date = dp.date if isinstance(dp.date, date_type) else dp.date.date()
            # Only update when daily data is newer or same-day with price correction
            # Never roll back newer live data with older daily data
            if dp_date > lp_date or (dp_date == lp_date and lp.price is not None
                                     and abs(float(dp.close) - float(lp.price)) > 0.01):
                prev_result = await session.execute(
                    select(DailyPrice.close)
                    .where(DailyPrice.ticker == dp.ticker, DailyPrice.date < dp.date)
                    .order_by(DailyPrice.date.desc())
                    .limit(1)
                )
                prev_close = prev_result.scalar()

                lp.price = dp.close
                lp.open = dp.open
                lp.high = dp.high
                lp.low = dp.low
                if prev_close is not None:
                    lp.previous_close = prev_close
                    lp.change = dp.close - prev_close
                    if prev_close != 0:
                        lp.change_percent = Decimal(str(
                            float((dp.close - prev_close) / prev_close) * 100
                        ))
                lp.volume = dp.volume
                lp.market_timestamp = datetime.combine(dp_date, datetime.min.time())
                lp.updated_at = datetime.utcnow()
                lp.data_source = "daily_prices_db"
                updated_count += 1

        await session.commit()
        if updated_count:
            logger.info(f"EOD refresh: synced {updated_count} LivePrice entries with daily closes")


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

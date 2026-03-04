"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from data_server.api.routes import router as api_router
from data_server.api.tracking import router as tracking_router
from data_server.db.database import init_db, close_db
from data_server.workers.scheduler import start_scheduler, stop_scheduler
from data_server.ws.manager import manager as ws_manager
from data_server.ws.handlers import router as ws_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def _refresh_stale_live_prices():
    """Refresh stale LivePrice entries from yfinance on startup."""
    from datetime import date as date_type
    from data_server.db.database import async_session_factory
    from data_server.db.models import LivePrice
    from data_server.api.routes import is_exchange_market_open
    from sqlalchemy import select

    async with async_session_factory() as session:
        result = await session.execute(select(LivePrice))
        prices = result.scalars().all()

        stale_open = []
        stale_closed = []
        for p in prices:
            if p.market_timestamp:
                age_days = (date_type.today() - p.market_timestamp.date()).days
                if age_days > 2:
                    exchange_code = p.exchange or (p.ticker.split(".")[-1] if "." in p.ticker else "US")
                    if is_exchange_market_open(exchange_code):
                        stale_open.append(p.ticker)
                    else:
                        stale_closed.append(p.ticker)

        if not stale_open and not stale_closed:
            logger.info("No stale LivePrice entries found")
            return

        yf_data = {}    # code -> (quote, source_label)
        if stale_open:
            logger.info(f"Refreshing {len(stale_open)} stale prices (market open) from yfinance fast_info")
            from data_server.services.yfinance_client import get_live_prices as yf_live
            yf_results = await yf_live(stale_open)
            for quote in yf_results:
                code = quote.get("code")
                if code:
                    yf_data[code] = (quote, "yfinance_fast_info")

        if stale_closed:
            logger.info(f"Refreshing {len(stale_closed)} stale prices (market closed) from yf.download EOD batch")
            from data_server.services.yfinance_client import get_eod_batch
            eod_results = await get_eod_batch(stale_closed)
            for quote in eod_results:
                code = quote.get("code")
                if code:
                    yf_data[code] = (quote, "yfinance_eod_batch")

        if yf_data:
            from datetime import datetime
            from decimal import Decimal
            for p in prices:
                if p.ticker in yf_data:
                    q, source = yf_data[p.ticker]
                    if q.get("close") is not None:
                        p.price = Decimal(str(q["close"]))
                        p.open = Decimal(str(q["open"])) if q.get("open") is not None else p.open
                        p.high = Decimal(str(q["high"])) if q.get("high") is not None else p.high
                        p.low = Decimal(str(q["low"])) if q.get("low") is not None else p.low
                        p.previous_close = Decimal(str(q["previousClose"])) if q.get("previousClose") is not None else p.previous_close
                        p.change = Decimal(str(q["change"])) if q.get("change") is not None else p.change
                        p.change_percent = Decimal(str(q["change_p"])) if q.get("change_p") is not None else p.change_percent
                        p.volume = q.get("volume") or p.volume
                        p.market_timestamp = datetime.utcnow()
                        p.updated_at = datetime.utcnow()
                        p.data_source = source
            await session.commit()
            logger.info(f"Startup: persisted {len(yf_data)} refreshed prices to LivePrice table")


async def _invalidate_stale_eod_caches():
    """Invalidate EOD caches that are missing today's data after market close."""
    from datetime import datetime, timedelta
    from sqlalchemy import delete
    from data_server.db.database import async_session_factory
    from data_server.db.models import CacheMetadata

    # Only invalidate if US market has closed today (after 4:30 PM ET = 21:30 UTC)
    now_utc = datetime.utcnow()
    # ET is UTC-5 (ignoring DST for simplicity)
    now_et = now_utc - timedelta(hours=5)
    market_close_today = now_et.replace(hour=16, minute=30, second=0, microsecond=0)

    if now_et < market_close_today:
        logger.info("US market hasn't closed yet today, skipping EOD cache invalidation")
        return

    async with async_session_factory() as session:
        # Delete EOD caches fetched before today's market close
        cutoff = market_close_today + timedelta(hours=5)  # Convert back to UTC
        result = await session.execute(
            delete(CacheMetadata).where(
                CacheMetadata.cache_key.startswith("eod:"),
                CacheMetadata.last_fetched < cutoff,
            )
        )
        deleted = result.rowcount
        await session.commit()

    if deleted:
        logger.info(f"Startup: invalidated {deleted} stale EOD cache entries (fetched before market close)")
    else:
        logger.info("EOD caches are up to date")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting data server...")
    await init_db()
    await _refresh_stale_live_prices()
    await _invalidate_stale_eod_caches()
    await start_scheduler()
    logger.info("Data server started successfully")

    yield

    # Shutdown
    logger.info("Shutting down data server...")
    await stop_scheduler()
    await ws_manager.disconnect_all()
    await close_db()
    logger.info("Data server shutdown complete")


app = FastAPI(
    title="Data Server",
    description="EODHD caching proxy server with real-time updates",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router, prefix="/api")
app.include_router(tracking_router, prefix="/tracking")
app.include_router(ws_router)  # WebSocket router (no prefix, uses /ws)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Data Server",
        "version": "0.1.0",
        "description": "EODHD caching proxy server",
    }

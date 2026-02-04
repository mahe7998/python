"""Stock tracking management API."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, delete, func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from data_server.db.database import get_session, async_session_factory
from data_server.db.models import TrackedStock, DailyPrice

logger = logging.getLogger(__name__)

router = APIRouter()

# Years of historical data to fetch for new stocks
HISTORICAL_YEARS = 5


class AddStockRequest(BaseModel):
    """Request to add a stock to tracking."""

    ticker: str
    exchange: Optional[str] = "US"
    track_prices: bool = True
    track_news: bool = True


class TrackedStockResponse(BaseModel):
    """Response for a tracked stock."""

    ticker: str
    exchange: Optional[str]
    track_prices: bool
    track_news: bool
    added_at: datetime
    last_price_update: Optional[datetime]
    last_news_update: Optional[datetime]


class TrackingStatusResponse(BaseModel):
    """Response for tracking status."""

    tracked_stocks: list[str]
    total_count: int
    last_price_worker_run: Optional[datetime]
    last_news_worker_run: Optional[datetime]


@router.get("/stocks", response_model=list[TrackedStockResponse])
async def list_tracked_stocks(
    session: AsyncSession = Depends(get_session),
):
    """List all tracked stocks."""
    result = await session.execute(
        select(TrackedStock).order_by(TrackedStock.added_at.desc())
    )
    stocks = result.scalars().all()

    return [
        TrackedStockResponse(
            ticker=s.ticker,
            exchange=s.exchange,
            track_prices=s.track_prices,
            track_news=s.track_news,
            added_at=s.added_at,
            last_price_update=s.last_price_update,
            last_news_update=s.last_news_update,
        )
        for s in stocks
    ]


async def prefetch_historical_data(symbol: str):
    """Fetch 5 years of historical daily data for a new stock.

    Runs in the background so the API doesn't block.
    """
    from data_server.services.eodhd_client import get_eodhd_client
    from data_server.db import cache

    try:
        async with async_session_factory() as session:
            # Check how much data we already have
            result = await session.execute(
                select(func.count(DailyPrice.date)).where(DailyPrice.ticker == symbol)
            )
            existing_count = result.scalar() or 0

            # If we already have substantial data (> 1000 days), skip
            if existing_count > 1000:
                logger.info(f"{symbol}: Already has {existing_count} days of data, skipping prefetch")
                return

            # Fetch 5 years of data
            from_date = (datetime.utcnow() - timedelta(days=HISTORICAL_YEARS * 365)).strftime("%Y-%m-%d")
            to_date = datetime.utcnow().strftime("%Y-%m-%d")

            logger.info(f"{symbol}: Prefetching {HISTORICAL_YEARS}Y historical data ({from_date} to {to_date})")

            client = await get_eodhd_client()
            data = await client.get_eod(symbol, from_date=from_date, to_date=to_date)

            if data:
                count = await cache.store_daily_prices(session, symbol, data)
                await session.commit()
                logger.info(f"{symbol}: Stored {count} days of historical data")
            else:
                logger.warning(f"{symbol}: No historical data returned from EODHD")

    except Exception as e:
        logger.error(f"{symbol}: Error prefetching historical data: {e}")


@router.post("/stocks", response_model=TrackedStockResponse)
async def add_tracked_stock(
    request: AddStockRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Add a stock to tracking and prefetch 5 years of historical data."""
    # Extract exchange from ticker if present (e.g., "9988.HK" -> ticker="9988", exchange="HK")
    ticker = request.ticker
    exchange = request.exchange
    if "." in ticker:
        parts = ticker.split(".")
        ticker = parts[0]
        exchange = parts[1]  # Use exchange from ticker, overrides request exchange

    stmt = insert(TrackedStock).values(
        ticker=ticker,
        exchange=exchange,
        track_prices=request.track_prices,
        track_news=request.track_news,
        added_at=datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={
            "exchange": exchange,
            "track_prices": request.track_prices,
            "track_news": request.track_news,
        },
    )
    await session.execute(stmt)
    await session.commit()

    # Fetch the updated/inserted record
    result = await session.execute(
        select(TrackedStock).where(TrackedStock.ticker == ticker)
    )
    stock = result.scalar_one()

    logger.info(f"Added/updated tracked stock: {ticker}")

    # Prefetch historical data in background
    symbol = f"{ticker}.{exchange}"
    background_tasks.add_task(prefetch_historical_data, symbol)

    return TrackedStockResponse(
        ticker=stock.ticker,
        exchange=stock.exchange,
        track_prices=stock.track_prices,
        track_news=stock.track_news,
        added_at=stock.added_at,
        last_price_update=stock.last_price_update,
        last_news_update=stock.last_news_update,
    )


@router.delete("/stocks/{ticker}")
async def remove_tracked_stock(
    ticker: str,
    session: AsyncSession = Depends(get_session),
):
    """Remove a stock from tracking."""
    result = await session.execute(
        delete(TrackedStock).where(TrackedStock.ticker == ticker)
    )
    await session.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Stock not found in tracking")

    logger.info(f"Removed tracked stock: {ticker}")

    return {"message": f"Removed {ticker} from tracking"}


@router.get("/status", response_model=TrackingStatusResponse)
async def get_tracking_status(
    session: AsyncSession = Depends(get_session),
):
    """Get tracking status and worker information."""
    result = await session.execute(select(TrackedStock))
    stocks = result.scalars().all()

    # Find most recent updates
    last_price = max(
        (s.last_price_update for s in stocks if s.last_price_update), default=None
    )
    last_news = max(
        (s.last_news_update for s in stocks if s.last_news_update), default=None
    )

    return TrackingStatusResponse(
        tracked_stocks=[s.ticker for s in stocks],
        total_count=len(stocks),
        last_price_worker_run=last_price,
        last_news_worker_run=last_news,
    )


async def get_tracked_tickers(session: AsyncSession) -> list[str]:
    """Helper to get list of tracked tickers for workers."""
    result = await session.execute(
        select(TrackedStock.ticker, TrackedStock.exchange).where(
            TrackedStock.track_prices == True
        )
    )
    # Build symbol as ticker.exchange, defaulting to US if exchange is NULL
    # Strip any existing exchange suffix from ticker (defensive)
    return [f"{row.ticker.split('.')[0]}.{row.exchange or 'US'}" for row in result.all()]


async def get_tracked_tickers_for_news(session: AsyncSession) -> list[str]:
    """Helper to get list of tracked tickers for news worker."""
    result = await session.execute(
        select(TrackedStock.ticker, TrackedStock.exchange).where(
            TrackedStock.track_news == True
        )
    )
    # Build symbol as ticker.exchange, defaulting to US if exchange is NULL
    # Strip any existing exchange suffix from ticker (defensive)
    return [f"{row.ticker.split('.')[0]}.{row.exchange or 'US'}" for row in result.all()]


async def update_price_timestamp(session: AsyncSession, ticker: str):
    """Update last price update timestamp for a ticker.

    Only updates existing tracked stocks - does not create new entries.
    Ticker param may include exchange suffix (e.g., AAPL.US) - we strip it.
    """
    # Strip exchange suffix to match stored ticker format
    clean_ticker = ticker.split(".")[0] if "." in ticker else ticker

    stmt = update(TrackedStock).where(
        TrackedStock.ticker == clean_ticker
    ).values(last_price_update=datetime.utcnow())
    await session.execute(stmt)


async def update_news_timestamp(session: AsyncSession, ticker: str):
    """Update last news update timestamp for a ticker.

    Only updates existing tracked stocks - does not create new entries.
    Ticker param may include exchange suffix (e.g., AAPL.US) - we strip it.
    """
    # Strip exchange suffix to match stored ticker format
    clean_ticker = ticker.split(".")[0] if "." in ticker else ticker

    stmt = update(TrackedStock).where(
        TrackedStock.ticker == clean_ticker
    ).values(last_news_update=datetime.utcnow())
    await session.execute(stmt)


class BulkSyncRequest(BaseModel):
    """Request to bulk sync stocks to tracking."""
    stocks: list[dict]  # List of {"ticker": "AAPL", "exchange": "US"}


@router.post("/stocks/sync")
async def sync_tracked_stocks(
    request: BulkSyncRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Bulk sync stocks to tracking - adds any missing stocks and prefetches historical data."""
    added_count = 0
    new_symbols = []

    for stock in request.stocks:
        ticker = stock.get("ticker")
        exchange = stock.get("exchange", "US")

        if not ticker:
            continue

        # Extract exchange from ticker if present (e.g., "9988.HK" -> ticker="9988", exchange="HK")
        if "." in ticker:
            parts = ticker.split(".")
            ticker = parts[0]
            exchange = parts[1]  # Use exchange from ticker, overrides request exchange

        stmt = insert(TrackedStock).values(
            ticker=ticker,
            exchange=exchange,
            track_prices=True,
            track_news=True,
            added_at=datetime.utcnow(),
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["ticker"])
        result = await session.execute(stmt)
        if result.rowcount > 0:
            added_count += 1
            new_symbols.append(f"{ticker}.{exchange}")

    await session.commit()

    # Prefetch historical data for new stocks in background
    for symbol in new_symbols:
        background_tasks.add_task(prefetch_historical_data, symbol)

    # Get total count
    result = await session.execute(select(TrackedStock))
    total = len(result.scalars().all())

    logger.info(f"Synced {added_count} new stocks, total tracked: {total}")

    return {
        "added": added_count,
        "total_tracked": total,
        "prefetching": new_symbols,
    }

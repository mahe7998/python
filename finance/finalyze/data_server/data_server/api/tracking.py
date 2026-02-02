"""Stock tracking management API."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from data_server.db.database import get_session
from data_server.db.models import TrackedStock

logger = logging.getLogger(__name__)

router = APIRouter()


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


@router.post("/stocks", response_model=TrackedStockResponse)
async def add_tracked_stock(
    request: AddStockRequest,
    session: AsyncSession = Depends(get_session),
):
    """Add a stock to tracking."""
    stmt = insert(TrackedStock).values(
        ticker=request.ticker,
        exchange=request.exchange,
        track_prices=request.track_prices,
        track_news=request.track_news,
        added_at=datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={
            "exchange": request.exchange,
            "track_prices": request.track_prices,
            "track_news": request.track_news,
        },
    )
    await session.execute(stmt)
    await session.commit()

    # Fetch the updated/inserted record
    result = await session.execute(
        select(TrackedStock).where(TrackedStock.ticker == request.ticker)
    )
    stock = result.scalar_one()

    logger.info(f"Added/updated tracked stock: {request.ticker}")

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
    return [f"{row.ticker}.{row.exchange}" for row in result.all()]


async def get_tracked_tickers_for_news(session: AsyncSession) -> list[str]:
    """Helper to get list of tracked tickers for news worker."""
    result = await session.execute(
        select(TrackedStock.ticker, TrackedStock.exchange).where(
            TrackedStock.track_news == True
        )
    )
    return [f"{row.ticker}.{row.exchange}" for row in result.all()]


async def update_price_timestamp(session: AsyncSession, ticker: str):
    """Update last price update timestamp for a ticker."""
    await session.execute(
        select(TrackedStock)
        .where(TrackedStock.ticker == ticker)
        .with_for_update()
    )
    stmt = insert(TrackedStock).values(
        ticker=ticker,
        last_price_update=datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={"last_price_update": datetime.utcnow()},
    )
    await session.execute(stmt)


async def update_news_timestamp(session: AsyncSession, ticker: str):
    """Update last news update timestamp for a ticker."""
    stmt = insert(TrackedStock).values(
        ticker=ticker,
        last_news_update=datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={"last_news_update": datetime.utcnow()},
    )
    await session.execute(stmt)

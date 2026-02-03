"""Background worker for price updates."""

import logging
from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from data_server.db.database import async_session_factory
from data_server.db.models import LivePrice, IntradayPrice
from data_server.api.tracking import get_tracked_tickers, update_price_timestamp
from data_server.services.eodhd_client import get_eodhd_client
from data_server.ws.manager import manager

logger = logging.getLogger(__name__)


def is_market_open() -> bool:
    """Check if US stock market is currently open (9:30 AM - 4:00 PM ET).

    Note: This is a simplified check. Does not account for holidays.
    Uses EST (UTC-5) - no DST handling for simplicity.
    """
    from datetime import timedelta

    now_utc = datetime.utcnow()

    # Convert UTC to Eastern Time (EST = UTC-5)
    now_et = now_utc - timedelta(hours=5)

    # Market hours in ET: 9:30 AM - 4:00 PM
    market_open = time(9, 30)
    market_close = time(16, 0)

    current_time_et = now_et.time()

    # Check if it's a weekday in ET (Monday=0, Sunday=6)
    if now_et.weekday() >= 5:  # Saturday or Sunday
        return False

    return market_open <= current_time_et <= market_close


async def update_prices():
    """Update prices for all tracked stocks."""
    # Skip updates when market is closed
    if not is_market_open():
        logger.debug("Market closed, skipping price updates")
        return

    async with async_session_factory() as session:
        # Get tracked tickers
        tickers = await get_tracked_tickers(session)

        if not tickers:
            logger.debug("No tracked stocks for price updates")
            return

        logger.info(f"Updating live prices for {len(tickers)} stocks")

        client = await get_eodhd_client()

        for symbol in tickers:
            try:
                # Fetch real-time quote
                quote = await client.get_real_time(symbol)

                if quote:
                    # Use full symbol (e.g., LULU.US) for consistency
                    ticker = symbol  # Keep full symbol for storage
                    exchange = symbol.split(".")[1] if "." in symbol else "US"

                    # Helper to convert 'NA' or invalid values to None
                    def to_decimal(val):
                        if val is None or val == 'NA' or val == '':
                            return None
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            return None

                    def to_int(val):
                        if val is None or val == 'NA' or val == '':
                            return None
                        try:
                            return int(val)
                        except (ValueError, TypeError):
                            return None

                    # Store live price in database (upsert)
                    market_ts = None
                    ts = quote.get("timestamp")
                    if ts and ts != 'NA':
                        try:
                            market_ts = datetime.fromtimestamp(int(ts))
                        except (ValueError, TypeError):
                            pass

                    # Skip if no valid price data
                    price_val = to_decimal(quote.get("close"))
                    if price_val is None:
                        logger.debug(f"Skipping {ticker} - no valid price data")
                        continue

                    # Update LivePrice (latest price only)
                    stmt = insert(LivePrice).values(
                        ticker=ticker,
                        exchange=exchange,
                        price=price_val,
                        open=to_decimal(quote.get("open")),
                        high=to_decimal(quote.get("high")),
                        low=to_decimal(quote.get("low")),
                        previous_close=to_decimal(quote.get("previousClose")),
                        change=to_decimal(quote.get("change")),
                        change_percent=to_decimal(quote.get("change_p")),
                        volume=to_int(quote.get("volume")),
                        market_timestamp=market_ts,
                        updated_at=datetime.utcnow(),
                    ).on_conflict_do_update(
                        index_elements=["ticker"],
                        set_={
                            "price": price_val,
                            "open": to_decimal(quote.get("open")),
                            "high": to_decimal(quote.get("high")),
                            "low": to_decimal(quote.get("low")),
                            "previous_close": to_decimal(quote.get("previousClose")),
                            "change": to_decimal(quote.get("change")),
                            "change_percent": to_decimal(quote.get("change_p")),
                            "volume": to_int(quote.get("volume")),
                            "market_timestamp": market_ts,
                            "updated_at": datetime.utcnow(),
                        }
                    )
                    await session.execute(stmt)

                    # Also store in IntradayPrice for historical intraday data
                    # Store current price as OHLC so chart resample creates proper bars
                    # (day's open/high/low would make all candles identical)
                    # Note: source='live' indicates this is from price worker, not EODHD
                    intraday_ts = market_ts or datetime.utcnow()
                    intraday_stmt = insert(IntradayPrice).values(
                        ticker=ticker,
                        timestamp=intraday_ts,
                        open=price_val,   # Use current price for proper resampling
                        high=price_val,
                        low=price_val,
                        close=price_val,
                        volume=to_int(quote.get("volume")),
                        source="live",
                        fetched_at=datetime.utcnow(),
                    ).on_conflict_do_update(
                        index_elements=["ticker", "timestamp"],
                        set_={
                            "open": price_val,
                            "high": price_val,
                            "low": price_val,
                            "close": price_val,
                            "volume": to_int(quote.get("volume")),
                            # Don't overwrite source if it's already 'eodhd'
                            "fetched_at": datetime.utcnow(),
                        }
                    )
                    await session.execute(intraday_stmt)

                    # Update tracking timestamp
                    await update_price_timestamp(session, ticker)

                    # Broadcast to WebSocket subscribers
                    price_data = {
                        "price": quote.get("close"),
                        "change": quote.get("change"),
                        "change_percent": quote.get("change_p"),
                        "volume": quote.get("volume"),
                        "timestamp": quote.get("timestamp"),
                    }
                    await manager.broadcast_price_update(ticker, price_data)

                    logger.debug(f"Updated live price for {ticker}: ${quote.get('close')}")

            except Exception as e:
                logger.error(f"Error updating price for {symbol}: {e}")

        await session.commit()
        logger.info(f"Live price update complete for {len(tickers)} stocks")


async def update_daily_prices():
    """Update daily prices for all tracked stocks (called after market close)."""
    async with async_session_factory() as session:
        from data_server.db import cache

        tickers = await get_tracked_tickers(session)

        if not tickers:
            return

        logger.info(f"Updating daily prices for {len(tickers)} stocks")

        client = await get_eodhd_client()

        for symbol in tickers:
            try:
                # Fetch recent daily prices
                data = await client.get_eod(symbol)

                if data:
                    ticker = symbol.split(".")[0]
                    count = await cache.store_daily_prices(session, symbol, data)
                    logger.info(f"Stored {count} daily prices for {ticker}")

            except Exception as e:
                logger.error(f"Error updating daily prices for {symbol}: {e}")

        await session.commit()

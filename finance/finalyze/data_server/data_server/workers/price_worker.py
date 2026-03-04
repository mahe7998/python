"""Background worker for price updates."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from data_server.db.database import async_session_factory
from data_server.db.models import LivePrice, IntradayPrice
from data_server.api.tracking import get_tracked_tickers, update_price_timestamp
from data_server.services.eodhd_client import get_eodhd_client
from data_server.ws.manager import manager
from data_server.utils.exchange_hours import is_market_open as is_exchange_open
from data_server.services.yfinance_client import is_realtime_supported_by_eodhd

logger = logging.getLogger(__name__)

# EODHD data delay in minutes (real-time and intraday are ~15 min behind)
EODHD_DELAY_MINUTES = 15

# In-memory OHLC aggregation for building 1-minute bars from 15-second snapshots
# Structure: {ticker: {"minute": datetime, "open": float, "high": float, "low": float, "close": float, "volume": int}}
_minute_bars: dict[str, dict] = {}

# Track previous cumulative volume to calculate per-minute volume deltas
# EODHD returns cumulative daily volume, we need to store the delta for each minute
# Structure: {ticker: last_cumulative_volume}
_prev_cumulative_volume: dict[str, int] = {}


def is_any_market_open(tickers: set[str]) -> bool:
    """Check if any tracked exchange is currently open.

    Extracts exchange codes from ticker symbols and returns True
    if at least one exchange is within trading hours.
    """
    exchanges = set()
    for ticker in tickers:
        exchange = ticker.split(".")[-1] if "." in ticker else "US"
        exchanges.add(exchange)

    return any(is_exchange_open(ex) for ex in exchanges)


def to_decimal(val):
    """Convert value to decimal, handling NA and invalid values."""
    if val is None or val == 'NA' or val == '':
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def to_int(val):
    """Convert value to int, handling NA and invalid values."""
    if val is None or val == 'NA' or val == '':
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


async def _update_minute_bar(session, ticker: str, price: float, cumulative_volume: int | None):
    """Aggregate 15-second price snapshots into 1-minute OHLC bars.

    Called every 15 seconds per ticker. Builds OHLC bars by:
    - Open: first price of the minute
    - High: max price seen in the minute
    - Low: min price seen in the minute
    - Close: last price (updated each call)
    - Volume: delta from previous cumulative (not cumulative itself)

    When a new minute starts, the previous minute's bar is stored to IntradayPrice.
    """
    global _minute_bars, _prev_cumulative_volume

    now = datetime.utcnow()
    current_minute = now.replace(second=0, microsecond=0)

    # Calculate volume delta from cumulative
    volume_delta = 0
    if cumulative_volume is not None:
        prev_vol = _prev_cumulative_volume.get(ticker, 0)
        if prev_vol > 0 and cumulative_volume >= prev_vol:
            volume_delta = cumulative_volume - prev_vol
        # Update previous cumulative for next calculation
        _prev_cumulative_volume[ticker] = cumulative_volume

    existing_bar = _minute_bars.get(ticker)

    if existing_bar and existing_bar["minute"] == current_minute:
        # Same minute - update running OHLC and accumulate volume delta
        existing_bar["high"] = max(existing_bar["high"], price)
        existing_bar["low"] = min(existing_bar["low"], price)
        existing_bar["close"] = price
        existing_bar["volume"] = (existing_bar["volume"] or 0) + volume_delta
    else:
        # New minute - store previous bar if exists, then start new bar
        if existing_bar:
            # Store completed bar to IntradayPrice
            stmt = insert(IntradayPrice).values(
                ticker=ticker,
                timestamp=existing_bar["minute"],
                open=existing_bar["open"],
                high=existing_bar["high"],
                low=existing_bar["low"],
                close=existing_bar["close"],
                volume=existing_bar["volume"],
                source="live",
                fetched_at=datetime.utcnow(),
            ).on_conflict_do_update(
                index_elements=["ticker", "timestamp"],
                set_={
                    # Only update if source is 'live' (don't overwrite eodhd data)
                    "open": existing_bar["open"],
                    "high": existing_bar["high"],
                    "low": existing_bar["low"],
                    "close": existing_bar["close"],
                    "volume": existing_bar["volume"],
                    "fetched_at": datetime.utcnow(),
                }
            )
            await session.execute(stmt)
            logger.debug(f"Stored 1-min bar for {ticker} at {existing_bar['minute']}: "
                        f"O={existing_bar['open']:.2f} H={existing_bar['high']:.2f} "
                        f"L={existing_bar['low']:.2f} C={existing_bar['close']:.2f}")

        # Start new bar for current minute
        # Open = first price reading of the minute
        # High/low will be updated via max/min as more readings come in
        _minute_bars[ticker] = {
            "minute": current_minute,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": volume_delta,
        }


async def update_prices():
    """Update prices for all tracked stocks using batch API."""
    async with async_session_factory() as session:
        # Get tracked tickers
        tickers = await get_tracked_tickers(session)

        if not tickers:
            logger.debug("No tracked stocks for price updates")
            return

        # Skip updates when no tracked exchange is open
        if not is_any_market_open(tickers):
            logger.debug("All markets closed, skipping price updates")
            return

        # Filter to only tickers whose exchange is currently open
        open_tickers = set()
        for ticker in tickers:
            exchange = ticker.split(".")[-1] if "." in ticker else "US"
            if is_exchange_open(exchange):
                open_tickers.add(ticker)

        if not open_tickers:
            return

        # Split tickers: EODHD-supported vs yfinance-needed (unreliable EODHD real-time)
        eodhd_tickers = set()
        yf_tickers = set()
        for ticker in open_tickers:
            exchange = ticker.split(".")[-1] if "." in ticker else "US"
            if is_realtime_supported_by_eodhd(exchange):
                eodhd_tickers.add(ticker)
            else:
                yf_tickers.add(ticker)

        logger.info(f"Updating live prices for {len(open_tickers)}/{len(tickers)} stocks "
                     f"(EODHD: {len(eodhd_tickers)}, yfinance: {len(yf_tickers)})")

        # Fetch from EODHD for supported exchanges
        quotes = []
        if eodhd_tickers:
            client = await get_eodhd_client()
            try:
                eodhd_quotes = await client.get_real_time_batch(list(eodhd_tickers))
                for q in eodhd_quotes:
                    q["_data_source"] = "eodhd"
                quotes.extend(eodhd_quotes)
                logger.info(f"EODHD batch response: {len(eodhd_quotes)} quotes received")
            except Exception as e:
                logger.error(f"EODHD batch price fetch failed: {e}")

        # Fetch from yfinance for unsupported exchanges
        if yf_tickers:
            try:
                from data_server.services.yfinance_client import get_live_prices
                yf_quotes = await get_live_prices(list(yf_tickers))
                if yf_quotes:
                    for q in yf_quotes:
                        q["_data_source"] = "yfinance_fast_info"
                    quotes.extend(yf_quotes)
                    logger.info(f"yfinance live prices: {len(yf_quotes)} quotes received")
            except Exception as e:
                logger.error(f"yfinance batch price fetch failed: {e}")

        if not quotes:
            return

        for quote in quotes:
            try:
                if not quote:
                    continue

                # Get ticker from quote response (EODHD returns 'code' field)
                ticker = quote.get("code")
                if not ticker:
                    logger.warning(f"Quote missing 'code' field: {quote}")
                    continue

                exchange = ticker.split(".")[1] if "." in ticker else "US"

                # Store live price in database (upsert)
                market_ts = None
                ts = quote.get("timestamp")
                if ts and ts != 'NA':
                    try:
                        market_ts = datetime.utcfromtimestamp(int(ts))
                    except (ValueError, TypeError):
                        pass

                # Skip if no valid price data
                price_val = to_decimal(quote.get("close"))
                if price_val is None:
                    logger.debug(f"Skipping {ticker} - no valid price data")
                    continue

                # Update LivePrice (latest price only)
                source = quote.get("_data_source", "eodhd")
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
                    data_source=source,
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
                        "data_source": source,
                    }
                )
                await session.execute(stmt)

                # Aggregate into 1-minute OHLC bars
                await _update_minute_bar(session, ticker, price_val, to_int(quote.get("volume")))

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
                ticker_name = quote.get("code", "unknown") if quote else "unknown"
                logger.error(f"Error updating price for {ticker_name}: {e}")

        await session.commit()
        logger.info(f"Live price update complete for {len(open_tickers)} stocks")


async def update_intraday_delayed():
    """Fetch intraday OHLC data from 16 minutes ago (when EODHD data becomes available).

    EODHD's intraday data is delayed by ~15 minutes. This function fetches
    exactly 1 minute of data that just became available (16 min ago to avoid edge cases).
    Runs every minute, fetching 1 minute of data each time - no overlap.
    """
    async with async_session_factory() as session:
        tickers = await get_tracked_tickers(session)

        if not tickers:
            return

        # Filter to tickers with open exchanges
        open_tickers = set()
        for ticker in tickers:
            exchange = ticker.split(".")[-1] if "." in ticker else "US"
            if is_exchange_open(exchange):
                open_tickers.add(ticker)

        if not open_tickers:
            logger.debug("All markets closed, skipping delayed intraday fetch")
            return

        client = await get_eodhd_client()
        now = datetime.utcnow()

        # Fetch exactly the 1-minute bar from 16 minutes ago
        # Using 16 min to have a buffer (EODHD delay is ~15 min)
        target_time = now - timedelta(minutes=EODHD_DELAY_MINUTES + 1)  # 16 min ago
        # Round down to the minute
        target_minute = target_time.replace(second=0, microsecond=0)

        from_ts = int(target_minute.timestamp())
        to_ts = from_ts + 60  # 1 minute window

        logger.info(f"Fetching delayed intraday for {target_minute.strftime('%H:%M')} UTC ({len(open_tickers)} stocks)")

        fetched_count = 0
        for ticker in open_tickers:
            try:
                # Fetch 1-minute intraday data for the delayed window
                data = await client.get_intraday(ticker, interval="1m", from_timestamp=from_ts, to_timestamp=to_ts)

                if not data:
                    continue

                # Store each minute's OHLC data
                for bar in data:
                    bar_ts = bar.get("timestamp")
                    if not bar_ts:
                        continue

                    try:
                        bar_datetime = datetime.utcfromtimestamp(int(bar_ts))
                    except (ValueError, TypeError):
                        continue

                    # Store with source='eodhd' - this has real OHLC values
                    stmt = insert(IntradayPrice).values(
                        ticker=ticker,
                        timestamp=bar_datetime,
                        open=to_decimal(bar.get("open")),
                        high=to_decimal(bar.get("high")),
                        low=to_decimal(bar.get("low")),
                        close=to_decimal(bar.get("close")),
                        volume=to_int(bar.get("volume")),
                        source="eodhd",
                        fetched_at=datetime.utcnow(),
                    ).on_conflict_do_update(
                        index_elements=["ticker", "timestamp"],
                        set_={
                            "open": to_decimal(bar.get("open")),
                            "high": to_decimal(bar.get("high")),
                            "low": to_decimal(bar.get("low")),
                            "close": to_decimal(bar.get("close")),
                            "volume": to_int(bar.get("volume")),
                            "source": "eodhd",  # Override 'live' source with real OHLC
                            "fetched_at": datetime.utcnow(),
                        }
                    )
                    await session.execute(stmt)
                    fetched_count += 1

            except Exception as e:
                logger.error(f"Error fetching delayed intraday for {ticker}: {e}")

        await session.commit()
        if fetched_count > 0:
            logger.info(f"Stored {fetched_count} delayed intraday bars")


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

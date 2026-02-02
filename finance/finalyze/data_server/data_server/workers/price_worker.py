"""Background worker for price updates."""

import logging
from datetime import datetime

from data_server.db.database import async_session_factory
from data_server.api.tracking import get_tracked_tickers, update_price_timestamp
from data_server.services.eodhd_client import get_eodhd_client
from data_server.ws.manager import manager

logger = logging.getLogger(__name__)


async def update_prices():
    """Update prices for all tracked stocks."""
    async with async_session_factory() as session:
        # Get tracked tickers
        tickers = await get_tracked_tickers(session)

        if not tickers:
            logger.debug("No tracked stocks for price updates")
            return

        logger.debug(f"Updating prices for {len(tickers)} stocks")

        client = await get_eodhd_client()

        for symbol in tickers:
            try:
                # Fetch real-time quote
                quote = await client.get_real_time(symbol)

                if quote:
                    ticker = symbol.split(".")[0]

                    # Update timestamp
                    await update_price_timestamp(session, ticker)

                    # Broadcast to subscribers
                    price_data = {
                        "price": quote.get("close"),
                        "change": quote.get("change"),
                        "change_percent": quote.get("change_p"),
                        "volume": quote.get("volume"),
                        "timestamp": quote.get("timestamp"),
                    }
                    await manager.broadcast_price_update(ticker, price_data)

                    logger.debug(f"Updated price for {ticker}: {quote.get('close')}")

            except Exception as e:
                logger.error(f"Error updating price for {symbol}: {e}")

        await session.commit()


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

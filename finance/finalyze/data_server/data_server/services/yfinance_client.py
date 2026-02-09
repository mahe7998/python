"""yfinance fallback for shares outstanding when SEC EDGAR is unavailable."""

import asyncio
import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


async def get_shares_outstanding(ticker: str, exchange: str = "US") -> Optional[int]:
    """Get shares outstanding from yfinance as a fallback.

    Args:
        ticker: Stock ticker (e.g., "NVDA")
        exchange: Exchange code (e.g., "US")

    Returns:
        Shares outstanding count, or None if unavailable
    """
    def _fetch() -> Optional[int]:
        try:
            import yfinance as yf
            # yfinance uses standard ticker symbols (no exchange suffix for US)
            symbol = ticker if exchange == "US" else f"{ticker}.{exchange}"
            t = yf.Ticker(symbol)
            info = t.info
            shares = info.get("sharesOutstanding")
            if shares and shares > 0:
                return int(shares)
            return None
        except Exception as e:
            logger.error(f"yfinance error for {ticker}: {e}")
            return None

    return await asyncio.to_thread(_fetch)


async def get_shares_history_entry(ticker: str, exchange: str = "US") -> Optional[dict]:
    """Get a single shares outstanding data point from yfinance.

    Returns a dict compatible with shares_history storage, or None.
    """
    shares = await get_shares_outstanding(ticker, exchange)
    if shares is None:
        return None

    return {
        "shares_outstanding": shares,
        "report_date": date.today(),
        "source": "yfinance",
        "filing_type": None,
        "filed_date": None,
        "fiscal_year": None,
        "fiscal_period": None,
    }

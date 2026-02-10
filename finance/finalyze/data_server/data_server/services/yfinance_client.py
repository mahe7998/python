"""yfinance fallback for shares outstanding and intraday prices."""

import asyncio
import logging
from datetime import date, datetime
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


async def get_intraday_prices(
    ticker: str,
    exchange: str = "US",
    interval: str = "1m",
    target_date: Optional[date] = None,
) -> list[dict]:
    """Get intraday prices from yfinance as a fallback when EODHD is unavailable.

    yfinance provides 1-minute data for the last 7 days, available immediately
    after market close (unlike EODHD which can take hours).

    Args:
        ticker: Stock ticker (e.g., "NVDA")
        exchange: Exchange code (e.g., "US")
        interval: Bar interval (default "1m")
        target_date: Specific date to fetch. If None, fetches most recent day.

    Returns:
        List of dicts with timestamp, open, high, low, close, volume
    """
    def _fetch() -> list[dict]:
        try:
            import yfinance as yf
            import pandas as pd

            symbol = ticker if exchange == "US" else f"{ticker}.{exchange}"
            t = yf.Ticker(symbol)

            # yfinance 1m data: need period="5d" (max for 1m), then filter to target_date
            df = t.history(period="5d", interval=interval)

            if df is None or df.empty:
                logger.warning(f"yfinance returned no intraday data for {symbol}")
                return []

            # Filter to target_date if specified
            if target_date is not None:
                # yfinance returns timezone-aware timestamps
                df_dates = df.index.date
                df = df[df_dates == target_date]

                if df.empty:
                    logger.info(f"yfinance has no data for {symbol} on {target_date}")
                    return []

            # Convert to UTC timestamps and format as dicts
            records = []
            for ts, row in df.iterrows():
                # Convert to UTC naive timestamp (matching EODHD format)
                if ts.tzinfo is not None:
                    ts_utc = ts.tz_convert("UTC").tz_localize(None)
                else:
                    ts_utc = ts

                records.append({
                    "timestamp": ts_utc.isoformat(),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"]),
                })

            logger.info(f"yfinance returned {len(records)} intraday bars for {symbol} ({interval})")
            return records

        except Exception as e:
            logger.error(f"yfinance intraday error for {ticker}: {e}")
            return []

    return await asyncio.to_thread(_fetch)

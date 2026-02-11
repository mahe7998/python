"""Exchange market hours, timezone offsets, and lunch break definitions.

Shared module used by both UI (chart, main_window) and data logic.
A copy of this file also lives in data_server/data_server/utils/ for the
Docker-deployed data server.
"""

from datetime import datetime, timedelta, timezone
from datetime import time as dt_time
from typing import Optional, Tuple

# (utc_offset_hours, open_hour, open_min, close_hour, close_min)
EXCHANGE_MARKET_HOURS = {
    "US": (-5, 9, 30, 16, 0),      # EST
    "KO": (9, 9, 0, 15, 30),       # KST (Korea)
    "AS": (1, 9, 0, 17, 30),       # CET (Amsterdam/Euronext)
    "PA": (1, 9, 0, 17, 30),       # CET (Paris/Euronext)
    "F": (1, 9, 0, 17, 30),        # CET (Frankfurt)
    "SW": (1, 9, 0, 17, 30),       # CET (Swiss)
    "LSE": (0, 8, 0, 16, 30),      # GMT (London)
    "HK": (8, 9, 30, 16, 0),       # HKT (Hong Kong)
    "TSE": (9, 9, 0, 15, 0),       # JST (Tokyo)
    "SHG": (8, 9, 30, 15, 0),      # CST (Shanghai)
    "SHE": (8, 9, 30, 15, 0),      # CST (Shenzhen)
    "NSE": (5.5, 9, 15, 15, 30),   # IST (India NSE)
    "BSE": (5.5, 9, 15, 15, 30),   # IST (India BSE)
    "AU": (11, 10, 0, 16, 0),      # AEDT (Australia)
    "TO": (-5, 9, 30, 16, 0),      # EST (Toronto)
    "SA": (-3, 10, 0, 17, 0),      # BRT (Sao Paulo)
    "SN": (-4, 9, 30, 16, 0),      # CLT (Santiago)
}

# Lunch breaks in LOCAL time: (start_h, start_m, end_h, end_m)
EXCHANGE_LUNCH_BREAKS = {
    "TSE": (11, 30, 12, 30),   # Tokyo: 11:30-12:30 JST
    "SHG": (11, 30, 13, 0),    # Shanghai: 11:30-13:00 CST
    "SHE": (11, 30, 13, 0),    # Shenzhen: 11:30-13:00 CST
    "HK": (12, 0, 13, 0),      # Hong Kong: 12:00-13:00 HKT
}


def get_market_hours(exchange: str) -> Tuple[float, int, int, int, int]:
    """Return (utc_offset, open_hour, open_min, close_hour, close_min)."""
    return EXCHANGE_MARKET_HOURS.get(exchange, EXCHANGE_MARKET_HOURS["US"])


def get_utc_offset(exchange: str) -> timedelta:
    """Get UTC offset as a timedelta for an exchange."""
    hours = EXCHANGE_MARKET_HOURS.get(exchange, EXCHANGE_MARKET_HOURS["US"])[0]
    return timedelta(hours=hours)


def get_local_market_hours(exchange: str) -> Tuple[int, int, int, int]:
    """Return (open_h, open_m, close_h, close_m) in local time."""
    _, oh, om, ch, cm = get_market_hours(exchange)
    return oh, om, ch, cm


def is_market_open(exchange: str = "US") -> bool:
    """Check if a stock exchange is currently open (weekday + within hours)."""
    utc_offset, open_h, open_m, close_h, close_m = get_market_hours(exchange)
    now_utc = datetime.utcnow()
    now_local = now_utc + timedelta(hours=utc_offset)
    if now_local.weekday() >= 5:
        return False
    return dt_time(open_h, open_m) <= now_local.time() <= dt_time(close_h, close_m)


def clear_lunch_break(prices, exchange: str, utc_offset: float, trading_date) -> None:
    """Set OHLC to NaN during an exchange's lunch break (modifies in place).

    Args:
        prices: DataFrame with DatetimeIndex (UTC timestamps) and OHLC columns.
        exchange: Exchange code.
        utc_offset: UTC offset in hours for the exchange.
        trading_date: The local trading date (date object).
    """
    import pandas as pd  # deferred to avoid import at module level for data_server

    lunch = EXCHANGE_LUNCH_BREAKS.get(exchange)
    if not lunch:
        return
    ls_h, ls_m, le_h, le_m = lunch
    lunch_start_utc = datetime(
        trading_date.year, trading_date.month, trading_date.day, ls_h, ls_m
    ) - timedelta(hours=utc_offset)
    lunch_end_utc = datetime(
        trading_date.year, trading_date.month, trading_date.day, le_h, le_m
    ) - timedelta(hours=utc_offset)
    mask = (prices.index >= lunch_start_utc) & (prices.index < lunch_end_utc)
    if mask.any():
        prices.loc[mask, ["open", "high", "low", "close"]] = float("nan")
        if "volume" in prices.columns:
            prices.loc[mask, "volume"] = 0

"""Utility helper functions."""

from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple, List
import math


def format_number(value: float, decimals: int = 2) -> str:
    """
    Format a number with thousands separator.

    Args:
        value: Number to format
        decimals: Number of decimal places

    Returns:
        Formatted string
    """
    if value is None:
        return "N/A"
    return f"{value:,.{decimals}f}"


def format_currency(value: float, currency: str = "USD", decimals: int = 2) -> str:
    """
    Format a value as currency.

    Args:
        value: Amount to format
        currency: Currency code
        decimals: Number of decimal places

    Returns:
        Formatted currency string
    """
    if value is None:
        return "N/A"

    symbols = {
        "USD": "$",
        "EUR": "\u20ac",
        "GBP": "\u00a3",
        "JPY": "\u00a5",
        "CNY": "\u00a5",
    }

    symbol = symbols.get(currency, currency + " ")
    return f"{symbol}{format_number(value, decimals)}"


def format_large_number(value: float, decimals: int = 1) -> str:
    """
    Format large numbers with K, M, B, T suffixes.

    Args:
        value: Number to format
        decimals: Number of decimal places

    Returns:
        Formatted string with suffix
    """
    if value is None:
        return "N/A"

    if abs(value) < 1000:
        return format_number(value, decimals)

    suffixes = ["", "K", "M", "B", "T"]

    magnitude = 0
    while abs(value) >= 1000 and magnitude < len(suffixes) - 1:
        value /= 1000
        magnitude += 1

    return f"{value:.{decimals}f}{suffixes[magnitude]}"


def format_percent(value: float, decimals: int = 2, with_sign: bool = True) -> str:
    """
    Format a value as percentage.

    Args:
        value: Value to format (0.05 = 5%)
        decimals: Number of decimal places
        with_sign: Include + sign for positive values

    Returns:
        Formatted percentage string
    """
    if value is None:
        return "N/A"

    percent = value * 100
    sign = "+" if with_sign and percent > 0 else ""
    return f"{sign}{percent:.{decimals}f}%"


def format_change(value: float, decimals: int = 2) -> str:
    """
    Format a price change with color indicator prefix.

    Args:
        value: Change value
        decimals: Number of decimal places

    Returns:
        Formatted change string
    """
    if value is None:
        return "N/A"

    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}"


def get_color_for_change(change_percent: float) -> str:
    """
    Get hex color for a percentage change.

    Args:
        change_percent: Change as decimal (0.05 = 5%)

    Returns:
        Hex color string
    """
    if change_percent is None:
        return "#FFFFFF"

    change = change_percent * 100

    if change >= 5:
        return "#22C55E"
    elif change >= 2:
        return "#4ADE80"
    elif change >= 0.5:
        return "#86EFAC"
    elif change > -0.5:
        return "#F5F5F5"
    elif change > -2:
        return "#FCA5A5"
    elif change > -5:
        return "#F87171"
    else:
        return "#EF4444"


def interpolate_color(
    value: float,
    min_val: float,
    max_val: float,
    min_color: str,
    mid_color: str,
    max_color: str,
) -> str:
    """
    Interpolate between three colors based on value.

    Args:
        value: Current value
        min_val: Minimum value (maps to min_color)
        max_val: Maximum value (maps to max_color)
        min_color: Color for minimum (hex)
        mid_color: Color for midpoint (hex)
        max_color: Color for maximum (hex)

    Returns:
        Interpolated hex color
    """
    def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def rgb_to_hex(r: int, g: int, b: int) -> str:
        return f"#{r:02x}{g:02x}{b:02x}"

    if value is None:
        return mid_color

    value = max(min_val, min(max_val, value))

    mid_val = (min_val + max_val) / 2

    if value <= mid_val:
        t = (value - min_val) / (mid_val - min_val) if mid_val != min_val else 0
        c1 = hex_to_rgb(min_color)
        c2 = hex_to_rgb(mid_color)
    else:
        t = (value - mid_val) / (max_val - mid_val) if max_val != mid_val else 1
        c1 = hex_to_rgb(mid_color)
        c2 = hex_to_rgb(max_color)

    r = int(c1[0] + t * (c2[0] - c1[0]))
    g = int(c1[1] + t * (c2[1] - c1[1]))
    b = int(c1[2] + t * (c2[2] - c1[2]))

    return rgb_to_hex(r, g, b)


def get_trading_days(start: date, end: date) -> List[date]:
    """
    Get list of trading days (weekdays) between two dates.

    Args:
        start: Start date
        end: End date

    Returns:
        List of trading days
    """
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def get_date_range(period: str, min_trading_days: int = 50) -> Tuple[date, date]:
    """
    Get date range for a period string.

    Args:
        period: Period string (1D, 1W, 1M, 3M, 6M, YTD, 1Y, 2Y, 5Y, MAX)
        min_trading_days: Minimum number of trading days to fetch (default 50)

    Returns:
        Tuple of (start_date, end_date)
    """
    end = date.today()

    # Calculate minimum calendar days needed for min_trading_days
    # Roughly 5 trading days per 7 calendar days, plus buffer for holidays
    if min_trading_days > 0:
        min_calendar_days = int(min_trading_days * 7 / 5) + 10
    else:
        min_calendar_days = 0

    period_map = {
        "1D": timedelta(days=7),  # 7 calendar days to ensure 2+ trading days even over long weekends
        "1W": timedelta(days=max(7, min_calendar_days)),
        "1M": timedelta(days=max(30, min_calendar_days)),
        "3M": timedelta(days=max(90, min_calendar_days)),
        "6M": timedelta(days=max(180, min_calendar_days)),
        "1Y": timedelta(days=365),
        "2Y": timedelta(days=730),
        "5Y": timedelta(days=1825),
    }

    if period == "YTD":
        # Year-to-date: always start from January 1st of current year
        start = date(end.year, 1, 1)
    elif period == "MAX":
        start = date(1990, 1, 1)
    elif period in period_map:
        start = end - period_map[period]
    else:
        start = end - timedelta(days=365)

    return (start, end)


def is_intraday_period(period: str) -> bool:
    """Check if period should use intraday data."""
    return period == "1D"


def get_market_hours(exchange: str = "US") -> Tuple[datetime, datetime]:
    """
    Get market open and close times for today in UTC.

    US Market hours: 9:30 AM - 4:00 PM ET (Eastern Time)

    Args:
        exchange: Exchange code (default "US")

    Returns:
        Tuple of (market_open, market_close) in UTC (timezone-aware)
    """
    today = date.today()

    if exchange == "US":
        # US market hours: 9:30 AM - 4:00 PM ET
        # ET is UTC-5 (EST) or UTC-4 (EDT)
        # For simplicity, assume UTC-5 (winter) - adjust if needed
        # Market open: 14:30 UTC, Market close: 21:00 UTC
        market_open = datetime(today.year, today.month, today.day, 14, 30, tzinfo=timezone.utc)
        market_close = datetime(today.year, today.month, today.day, 21, 0, tzinfo=timezone.utc)
    else:
        # Default to full day
        market_open = datetime(today.year, today.month, today.day, 0, 0, tzinfo=timezone.utc)
        market_close = datetime(today.year, today.month, today.day, 23, 59, tzinfo=timezone.utc)

    return (market_open, market_close)


def get_last_trading_day_hours(exchange: str = "US") -> Tuple[datetime, datetime]:
    """
    Get market hours for the last trading day (or today if market is open).

    Args:
        exchange: Exchange code

    Returns:
        Tuple of (market_open, market_close) in UTC (timezone-aware)
    """
    now = datetime.now(timezone.utc)
    today = now.date()

    # Get today's market hours
    market_open, market_close = get_market_hours(exchange)

    # If we're before today's market open, use yesterday's data
    # Or if it's a weekend, go back to Friday
    if now < market_open or today.weekday() >= 5:  # Saturday=5, Sunday=6
        # Go back to the last weekday
        days_back = 1
        if today.weekday() == 6:  # Sunday
            days_back = 2
        elif today.weekday() == 5:  # Saturday
            days_back = 1
        elif today.weekday() == 0 and now < market_open:  # Monday before open
            days_back = 3
        elif now < market_open:
            days_back = 1

        last_trading = today - timedelta(days=days_back)
        market_open = datetime(last_trading.year, last_trading.month, last_trading.day, 14, 30, tzinfo=timezone.utc)
        market_close = datetime(last_trading.year, last_trading.month, last_trading.day, 21, 0, tzinfo=timezone.utc)

    return (market_open, market_close)


def calculate_change(current: float, previous: float) -> Optional[float]:
    """
    Calculate percentage change between two values.

    Args:
        current: Current value
        previous: Previous value

    Returns:
        Percentage change as decimal (0.05 = 5%)
    """
    if previous is None or previous == 0:
        return None
    return (current - previous) / previous


def calculate_cagr(
    start_value: float,
    end_value: float,
    years: float,
) -> Optional[float]:
    """
    Calculate Compound Annual Growth Rate.

    Args:
        start_value: Starting value
        end_value: Ending value
        years: Number of years

    Returns:
        CAGR as decimal
    """
    if start_value <= 0 or end_value <= 0 or years <= 0:
        return None
    return (end_value / start_value) ** (1 / years) - 1


def is_market_open(exchange: str = "US") -> bool:
    """
    Check if market is currently open (simplified).

    Uses UTC to work correctly regardless of user's local timezone.
    US market hours: 9:30 AM - 4:00 PM ET = 14:30 - 21:00 UTC (EST)

    Args:
        exchange: Exchange code

    Returns:
        True if market is likely open
    """
    now_utc = datetime.now(timezone.utc)

    # Check weekday in ET (UTC-5 for EST)
    # Subtract 5 hours to get approximate ET day
    et_offset = timedelta(hours=5)
    now_et = now_utc - et_offset

    if now_et.weekday() >= 5:  # Saturday or Sunday in ET
        return False

    if exchange == "US":
        # US market: 9:30 AM - 4:00 PM ET = 14:30 - 21:00 UTC
        market_open_utc = now_utc.replace(hour=14, minute=30, second=0, microsecond=0)
        market_close_utc = now_utc.replace(hour=21, minute=0, second=0, microsecond=0)
    else:
        # Default: assume similar hours
        market_open_utc = now_utc.replace(hour=14, minute=0, second=0, microsecond=0)
        market_close_utc = now_utc.replace(hour=22, minute=30, second=0, microsecond=0)

    return market_open_utc <= now_utc <= market_close_utc


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate text to maximum length.

    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def normalize_ticker(ticker: str) -> str:
    """
    Normalize ticker symbol to uppercase.

    Args:
        ticker: Ticker symbol

    Returns:
        Normalized ticker
    """
    return ticker.upper().strip()


def parse_symbol(symbol: str) -> Tuple[str, str]:
    """
    Parse a symbol string into ticker and exchange.

    Args:
        symbol: Symbol string (e.g., "AAPL.US" or "AAPL")

    Returns:
        Tuple of (ticker, exchange)
    """
    if "." in symbol:
        parts = symbol.rsplit(".", 1)
        return (parts[0].upper(), parts[1].upper())
    return (symbol.upper(), "US")

"""REST API routes - EODHD proxy endpoints."""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from data_server.config import get_settings
from data_server.db.database import get_session
from data_server.db import cache
from data_server.services.eodhd_client import get_eodhd_client, get_eodhd_stats
from data_server.utils.exchange_hours import is_market_open as is_exchange_market_open

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory cache for earnings calendar (changes rarely, no need to hit API every time)
# Maps symbol -> (result_dict, timestamp)
_earnings_cache: Dict[str, tuple] = {}
_EARNINGS_CACHE_TTL = 3600  # 1 hour

router = APIRouter()

# EODHD exchange code → native currency mapping
# Used to fix cases where EODHD/yfinance returns ADR data (USD) for non-US listings
_EXCHANGE_TO_CURRENCY = {
    "US": "USD",
    "AS": "EUR",   # Euronext Amsterdam
    "PA": "EUR",   # Euronext Paris
    "BR": "EUR",   # Euronext Brussels
    "LI": "EUR",   # Euronext Lisbon
    "MI": "EUR",   # Borsa Italiana (Milan)
    "MC": "EUR",   # Madrid
    "HE": "EUR",   # Helsinki
    "IR": "EUR",   # Ireland
    "AT": "EUR",   # Athens
    "F": "EUR",    # Frankfurt
    "XETRA": "EUR",  # Xetra
    "LSE": "GBp",  # London (pence)
    "HK": "HKD",   # Hong Kong
    "TO": "CAD",   # Toronto
    "V": "CAD",    # TSX Venture
    "KO": "KRW",   # Korea (KOSPI)
    "KQ": "KRW",   # Korea (KOSDAQ)
    "NSE": "INR",  # India NSE
    "BSE": "INR",  # India BSE
    "SHE": "CNY",  # Shenzhen
    "SHG": "CNY",  # Shanghai
    "TSE": "JPY",  # Tokyo
    "SW": "CHF",   # SIX Swiss
    "AU": "AUD",   # Australia
    "SA": "BRL",   # Sao Paulo
    "SN": "CLP",   # Santiago
    "TW": "TWD",   # Taiwan
    "SG": "SGD",   # Singapore
    "JK": "IDR",   # Jakarta
    "TA": "ILS",   # Tel Aviv
    "WAR": "PLN",  # Warsaw
    "ST": "SEK",   # Stockholm
    "CO": "DKK",   # Copenhagen
    "OL": "NOK",   # Oslo
}

# Fields to compare between EODHD and yfinance quarterly data
COMPARISON_FIELDS = ["total_revenue", "gross_profit", "net_income", "operating_income"]
DISCREPANCY_THRESHOLD = 0.05  # 5%


def _safe_int(value) -> Optional[int]:
    """Safely convert a value to int (for BIGINT columns like market_cap)."""
    if value is None or value == "" or value == "None":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def compare_quarterly_data(
    eodhd_quarters: list[dict], yf_quarters: list[dict]
) -> list[dict]:
    """Compare EODHD vs yfinance quarterly data and return discrepancies.

    Skips records where data_source='yfinance' (already overridden).
    Returns list of discrepancy dicts with field diffs and full yfinance record.
    """
    # Index yfinance quarters by report_date
    yf_by_date = {}
    for yf_q in yf_quarters:
        d = yf_q.get("date")
        if d:
            yf_by_date[d] = yf_q

    discrepancies = []
    for eodhd_q in eodhd_quarters:
        if eodhd_q.get("data_source") == "yfinance":
            continue  # Already overridden, skip

        report_date = eodhd_q.get("report_date")
        if not report_date or report_date not in yf_by_date:
            continue

        yf_q = yf_by_date[report_date]
        yf_income = yf_q.get("income", {})

        # Map comparison fields to yfinance keys
        field_map = {
            "total_revenue": "totalRevenue",
            "gross_profit": "grossProfit",
            "net_income": "netIncome",
            "operating_income": "operatingIncome",
        }

        field_diffs = []
        for field, yf_key in field_map.items():
            eodhd_val = eodhd_q.get(field)
            yf_val = yf_income.get(yf_key)

            if eodhd_val is None or yf_val is None:
                continue
            if eodhd_val == 0 and yf_val == 0:
                continue

            denominator = max(abs(eodhd_val), abs(yf_val))
            if denominator == 0:
                continue

            pct_diff = abs(eodhd_val - yf_val) / denominator
            if pct_diff > DISCREPANCY_THRESHOLD:
                field_diffs.append({
                    "field": field,
                    "eodhd_value": eodhd_val,
                    "yfinance_value": yf_val,
                    "pct_diff": round(pct_diff * 100, 1),
                })

        if field_diffs:
            # Build full yfinance override record
            yf_balance = yf_q.get("balance", {})
            yf_cashflow = yf_q.get("cashflow", {})
            yf_record = {
                "report_date": report_date,
                "total_revenue": yf_income.get("totalRevenue"),
                "gross_profit": yf_income.get("grossProfit"),
                "operating_income": yf_income.get("operatingIncome"),
                "net_income": yf_income.get("netIncome"),
                "ebit": yf_income.get("ebit"),
                "cost_of_revenue": yf_income.get("costOfRevenue"),
                "research_development": yf_income.get("researchDevelopment"),
                "selling_general_admin": yf_income.get("sellingGeneralAdministrative"),
                "interest_expense": yf_income.get("interestExpense"),
                "tax_provision": yf_income.get("taxProvision"),
                "cash": yf_balance.get("cash"),
                "short_term_investments": yf_balance.get("shortTermInvestments"),
                "total_assets": yf_balance.get("totalAssets"),
                "total_current_assets": yf_balance.get("totalCurrentAssets"),
                "total_liabilities": yf_balance.get("totalLiab"),
                "total_current_liabilities": yf_balance.get("totalCurrentLiabilities"),
                "stockholders_equity": yf_balance.get("totalStockholderEquity"),
                "long_term_debt": yf_balance.get("longTermDebt"),
                "retained_earnings": yf_balance.get("retainedEarnings"),
                "operating_cash_flow": yf_cashflow.get("totalCashFromOperatingActivities"),
                "capital_expenditure": yf_cashflow.get("capitalExpenditures"),
                "free_cash_flow": yf_cashflow.get("freeCashFlow"),
                "dividends_paid": yf_cashflow.get("dividendsPaid"),
            }

            discrepancies.append({
                "report_date": report_date,
                "quarter": eodhd_q.get("quarter"),
                "year": eodhd_q.get("year"),
                "field_diffs": field_diffs,
                "yfinance_record": yf_record,
            })

    return discrepancies


def is_us_market_open() -> bool:
    """Check if US stock market is currently open."""
    return is_exchange_market_open("US")

# Per-key locks to prevent concurrent fetches for the same data
_fetch_locks: Dict[str, asyncio.Lock] = {}
_fetch_locks_lock = asyncio.Lock()


async def get_fetch_lock(cache_key: str) -> asyncio.Lock:
    """Get or create a lock for a specific cache key."""
    async with _fetch_locks_lock:
        if cache_key not in _fetch_locks:
            _fetch_locks[cache_key] = asyncio.Lock()
        return _fetch_locks[cache_key]


def log_timing(endpoint: str, cache_hit: bool, cache_time_ms: float, eodhd_time_ms: float = 0, total_time_ms: float = 0):
    """Log cache hit/miss and timing information."""
    status = "CACHE HIT" if cache_hit else "CACHE MISS"
    if cache_hit:
        logger.info(f"[{status}] {endpoint} | cache lookup: {cache_time_ms:.1f}ms | total: {total_time_ms:.1f}ms")
    else:
        logger.info(f"[{status}] {endpoint} | cache lookup: {cache_time_ms:.1f}ms | EODHD fetch: {eodhd_time_ms:.1f}ms | total: {total_time_ms:.1f}ms")


async def _append_live_price_bar(session, symbol: str, data: list, to_date) -> list:
    """Append today's bar from LivePrice if daily data doesn't include it yet.

    After market close (e.g., KRX), yfinance/EODHD may not have published today's
    daily bar yet, but LivePrice (from fast_info) has the OHLCV data.
    """
    from data_server.db.models import LivePrice

    today = datetime.utcnow().date()
    to_date_obj = to_date.date() if to_date else today
    if to_date_obj >= today and data:
        newest = data[-1].get("date", "")
        if newest:
            newest_date = datetime.fromisoformat(newest).date() if isinstance(newest, str) else newest
            if newest_date < today:
                live = await session.get(LivePrice, symbol)
                if live and live.price is not None and live.open is not None:
                    today_bar = {
                        "date": today.isoformat(),
                        "open": float(live.open),
                        "high": float(live.high) if live.high else float(live.price),
                        "low": float(live.low) if live.low else float(live.price),
                        "close": float(live.price),
                        "adjusted_close": float(live.price),
                        "volume": int(live.volume) if live.volume else 0,
                    }
                    data.append(today_bar)
                    logger.info(f"Appended today's bar for {symbol} from LivePrice: "
                                f"O={today_bar['open']} H={today_bar['high']} "
                                f"L={today_bar['low']} C={today_bar['close']}")
    return data


@router.get("/eod/{symbol}")
async def get_eod_prices(
    symbol: str,
    api_token: str = Query(None, description="API token (ignored, uses server key)"),
    from_: Optional[str] = Query(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    period: str = Query("d", description="Period: d, w, m"),
    fmt: str = Query("json", description="Format (always json)"),
    session: AsyncSession = Depends(get_session),
):
    """Get end-of-day prices for a symbol (cached).

    Caching strategy:
    1. First check if we have price records in the database for the requested date range
    2. If we have data covering the range, return it (no EODHD call needed)
    3. Only fetch from EODHD if data is missing
    """
    start_time = time.time()
    endpoint = f"GET /eod/{symbol}?from={from_}&to={to}"

    # Parse dates
    from_date = datetime.fromisoformat(from_) if from_ else None
    to_date = datetime.fromisoformat(to) if to else None

    # First: check if we have actual price data in the database for this range
    cache_start = time.time()
    cached_data = await cache.get_daily_prices(session, symbol, from_date, to_date)
    cache_time = (time.time() - cache_start) * 1000

    if cached_data and len(cached_data) > 0:
        # We have data! Check if it covers the requested range adequately
        # The data is ordered by date ASC, so first item is oldest, last is newest
        oldest_date = cached_data[0].get("date")
        newest_date = cached_data[-1].get("date")

        # Check if we need to fetch more recent data (today's data might be missing)
        today = datetime.now().date()
        to_date_obj = to_date.date() if to_date else today
        from_date_obj = from_date.date() if from_date else None

        # If the newest cached date is recent enough (within 1 day of requested end),
        # AND the oldest cached date covers the requested start, consider it a cache hit
        if newest_date:
            newest_date_obj = datetime.fromisoformat(newest_date).date() if isinstance(newest_date, str) else newest_date
            days_behind = (to_date_obj - newest_date_obj).days

            # Also check that cached data covers the start of requested range
            start_covered = True
            if from_date_obj and oldest_date:
                oldest_date_obj = datetime.fromisoformat(oldest_date).date() if isinstance(oldest_date, str) else oldest_date
                # Allow up to 5 days slack (weekends + holidays)
                if oldest_date_obj > from_date_obj + timedelta(days=5):
                    start_covered = False

            # Cache hit if we're at most ~1 trading day behind
            # Allow 4 days to cover weekends (Fri→Mon=3) and holidays (Fri→Tue=4)
            # Or if the to_date is in the past (historical data won't change)
            if start_covered and (days_behind <= 4 or to_date_obj < today):
                cached_data = await _append_live_price_bar(session, symbol, cached_data, to_date)
                total_time = (time.time() - start_time) * 1000
                log_timing(endpoint, True, cache_time, 0, total_time)
                return cached_data

    # Cache miss - need to fetch from EODHD
    cache_key = f"eod:{symbol}:{from_}:{to}:{period}"
    fetch_lock = await get_fetch_lock(cache_key)
    async with fetch_lock:
        # Expire session cache to see changes from other transactions
        session.expire_all()

        # Double-check cache after acquiring lock (another request may have populated it)
        cached_data = await cache.get_daily_prices(session, symbol, from_date, to_date)
        if cached_data and len(cached_data) > 0:
            oldest_date = cached_data[0].get("date")
            newest_date = cached_data[-1].get("date")
            if newest_date:
                today = datetime.now().date()
                to_date_obj = to_date.date() if to_date else today
                from_date_obj = from_date.date() if from_date else None
                newest_date_obj = datetime.fromisoformat(newest_date).date() if isinstance(newest_date, str) else newest_date
                days_behind = (to_date_obj - newest_date_obj).days
                start_covered = True
                if from_date_obj and oldest_date:
                    oldest_date_obj = datetime.fromisoformat(oldest_date).date() if isinstance(oldest_date, str) else oldest_date
                    if oldest_date_obj > from_date_obj + timedelta(days=5):
                        start_covered = False
                if start_covered and (days_behind <= 1 or to_date_obj < today):
                    cached_data = await _append_live_price_bar(session, symbol, cached_data, to_date)
                    total_time = (time.time() - start_time) * 1000
                    logger.info(f"[CACHE HIT after lock] {endpoint}")
                    return cached_data

        # Check if EODHD supports this exchange
        from data_server.services.yfinance_client import is_exchange_supported_by_eodhd
        exchange_code = symbol.split(".")[-1] if "." in symbol else "US"

        # Fetch from EODHD (only if exchange is supported)
        eodhd_start = time.time()
        data = []
        if is_exchange_supported_by_eodhd(exchange_code):
            client = await get_eodhd_client()
            try:
                data = await client.get_eod(symbol, from_, to, period)
            except Exception as e:
                logger.warning(f"EODHD error for {symbol}: {e}")
                data = []  # Let yfinance fallback handle it
        else:
            logger.info(f"Skipping EODHD for {symbol} (exchange {exchange_code} not supported)")
        eodhd_time = (time.time() - eodhd_start) * 1000

        # If EODHD returned nothing or was skipped, try yfinance as fallback
        if not data:
            try:
                from data_server.services.yfinance_client import get_daily_prices as yf_daily
                ticker_part = symbol.split(".")[0]
                exchange_part = symbol.split(".")[-1] if "." in symbol else "US"
                data = await yf_daily(ticker_part, exchange_part, from_, to)
                if data:
                    logger.info(f"yfinance returned {len(data)} daily bars for {symbol}")
            except Exception as e:
                logger.warning(f"yfinance daily fallback failed for {symbol}: {e}")

        # Store in cache (even if empty, to avoid repeated fetches for missing data)
        count = await cache.store_daily_prices(session, symbol, data)
        await cache.update_cache_metadata(
            session,
            cache_key,
            "daily_prices",
            symbol.split(".")[0],
            settings.cache_daily_prices,
            count,
        )
        await session.commit()

        data = await _append_live_price_bar(session, symbol, data, to_date)

        total_time = (time.time() - start_time) * 1000
        log_timing(endpoint, False, cache_time, eodhd_time, total_time)

        return data


@router.get("/intraday/{symbol}")
async def get_intraday_prices(
    symbol: str,
    api_token: str = Query(None),
    interval: str = Query("1m", description="Interval: 1m, 5m, 1h"),
    from_: Optional[int] = Query(None, alias="from", description="Start timestamp"),
    to: Optional[int] = Query(None, description="End timestamp"),
    fmt: str = Query("json"),
    force_eodhd: bool = Query(False, description="Force fetch from EODHD API (bypass price worker data)"),
    session: AsyncSession = Depends(get_session),
):
    """Get intraday prices for a symbol.

    For today's data: returns data from intraday_prices table (price worker snapshots)
    unless force_eodhd=true, which fetches proper OHLC bars from EODHD API.

    For historical data: fetches from EODHD and caches.

    When market is closed: checks if cached data is from 'live' source.
    If so, tries to fetch from EODHD for proper OHLC data.
    EODHD takes several hours after close to have data, so falls back to cached if unavailable.
    """
    start_time = time.time()
    # Use full symbol (e.g., LULU.US) for consistency with daily prices
    cache_key = f"intraday:{symbol}:{interval}:{from_}:{to}"
    endpoint = f"GET /intraday/{symbol}?interval={interval}"
    from_ts = datetime.utcfromtimestamp(from_) if from_ else None
    to_ts = datetime.utcfromtimestamp(to) if to else None

    # Check if requesting today's data
    today = datetime.utcnow().date()
    is_today = False
    if to_ts:
        is_today = to_ts.date() >= today
    elif from_ts:
        is_today = from_ts.date() >= today
    else:
        is_today = True  # No date filter = today

    # Initialize cache_time for logging
    cache_time = 0

    # Check if market is open for this exchange
    exchange_code = symbol.split(".")[-1] if "." in symbol else "US"
    market_open = is_exchange_market_open(exchange_code)

    # For historical data, use longer cache TTL (24h) since it won't change
    # For today's data, use shorter TTL (60s) to get fresh updates
    cache_ttl = settings.cache_daily_prices if not is_today else settings.cache_intraday_prices

    # Check cached data first
    cache_start = time.time()
    cached_data = await cache.get_intraday_prices(session, symbol, from_ts, to_ts)
    cached_source = await cache.get_intraday_source(session, symbol, from_ts, to_ts)
    cache_time = (time.time() - cache_start) * 1000

    # Check if cached data is stale (for today's data during market hours)
    # If the newest cached bar is more than 5 minutes old, try to refresh
    cache_is_stale = False
    if cached_data and is_today and market_open:
        newest_ts = cached_data[-1].get("timestamp", "")
        if newest_ts:
            try:
                newest_dt = datetime.fromisoformat(newest_ts)
                age_minutes = (datetime.utcnow() - newest_dt).total_seconds() / 60
                if age_minutes > 5:
                    cache_is_stale = True
                    logger.info(f"Cached intraday for {symbol} is stale ({age_minutes:.0f}min old), will refresh")
            except (ValueError, TypeError):
                pass

    # Determine if we should try to fetch better data:
    # 1. force_eodhd=true explicitly requested (but NOT for today's data during market hours)
    # 2. Market is closed AND data is from 'live' source (price worker bars, not real OHLC)
    # Note: EODHD doesn't provide intraday data during market hours, only after market close
    force_eodhd_effective = force_eodhd and not (is_today and market_open)
    should_try_better = force_eodhd_effective or (not market_open and cached_source == "live")

    if not should_try_better and not cache_is_stale:
        # Return cached data if available and fresh
        if cached_data:
            total_time = (time.time() - start_time) * 1000
            log_timing(endpoint, True, cache_time, 0, total_time)
            return cached_data

        # If requesting today and no cached data:
        # - For US stocks during/before market hours: return empty (data accumulates from price worker)
        # - For non-US stocks (or closed markets): try yfinance since their market may have already closed today
        if is_today:
            exchange_code = symbol.split(".")[-1] if "." in symbol else "US"
            if exchange_code == "US" and market_open:
                logger.info(f"No intraday data yet for {symbol} today - data will accumulate from price worker")
                return []
            elif exchange_code == "US":
                # US market closed today, but might not have EODHD data yet - try yfinance
                logger.info(f"US market closed, no cached data for {symbol} today - trying yfinance")
            else:
                # Non-US stock - market may have already closed today, try yfinance
                logger.info(f"Non-US stock {symbol}, no cached data today - trying yfinance fallback")

    # A full US trading day has ~390 1-minute bars (9:30 AM - 4:00 PM ET).
    # Consider data "complete" if it covers at least 80% of the day.
    min_complete_bars = 310

    # If we already have complete EODHD data, return it
    if cached_source == "eodhd" and cached_data and len(cached_data) >= min_complete_bars:
        total_time = (time.time() - start_time) * 1000
        log_timing(endpoint, True, cache_time, 0, total_time)
        logger.info(f"[CACHE HIT] EODHD data for {symbol} ({len(cached_data)} bars)")
        return cached_data

    if cached_source == "eodhd" and cached_data:
        logger.info(f"Cached EODHD data for {symbol} is incomplete ({len(cached_data)} bars < {min_complete_bars}), retrying")

    logger.info(f"Will try EODHD for {symbol} (market_open={market_open}, cached_source={cached_source})")

    # Try to fetch from EODHD
    fetch_lock = await get_fetch_lock(cache_key)
    async with fetch_lock:
        # Check if EODHD supports this exchange
        from data_server.services.yfinance_client import is_exchange_supported_by_eodhd
        eodhd_supported = is_exchange_supported_by_eodhd(exchange_code)

        # Fetch from EODHD (only if exchange is supported)
        eodhd_start = time.time()
        data = []
        if eodhd_supported:
            logger.info(f"Fetching {symbol} from EODHD")
            client = await get_eodhd_client()
            try:
                data = await client.get_intraday(symbol, interval, from_, to)
            except Exception as e:
                logger.warning(f"EODHD error for {symbol}: {e}")
                data = []  # Let yfinance fallback handle it below
        else:
            logger.info(f"Skipping EODHD for {symbol} (exchange {exchange_code} not supported)")
        eodhd_time = (time.time() - eodhd_start) * 1000

        # If EODHD data is missing or incomplete, try yfinance as fallback
        # Always try yfinance if EODHD returned nothing (exchange may not be supported)
        eodhd_count = len(data) if data else 0
        eodhd_is_complete = eodhd_count >= min_complete_bars
        if not eodhd_is_complete and (not market_open or eodhd_count == 0):
            logger.info(f"EODHD data incomplete for {symbol} ({eodhd_count} bars), trying yfinance fallback")

            try:
                from data_server.services.yfinance_client import get_intraday_prices as yf_intraday

                # Determine target date from the request timestamps
                target_date = from_ts.date() if from_ts else today
                ticker_part = symbol.split(".")[0]
                exchange_part = symbol.split(".")[-1] if "." in symbol else "US"

                yf_data = await yf_intraday(
                    ticker=ticker_part,
                    exchange=exchange_part,
                    interval=interval,
                    target_date=target_date,
                )

                if yf_data and len(yf_data) > eodhd_count:
                    logger.info(f"yfinance returned {len(yf_data)} bars for {symbol} (vs EODHD {eodhd_count})")
                    data = yf_data
                else:
                    logger.info(f"yfinance returned {len(yf_data) if yf_data else 0} bars, not better than EODHD")
            except Exception as e:
                logger.warning(f"yfinance fallback failed for {symbol}: {e}")

        if not data:
            logger.info(f"No intraday data from any source for {symbol}, falling back to cached")
            if cached_data:
                # If cached bars are flat (price worker snapshots with identical OHLC),
                # replace with a single summary bar from LivePrice for a meaningful chart
                prices = set(b.get("close") for b in cached_data if b.get("close") is not None)
                if len(prices) <= 1 and is_today:
                    from data_server.db.models import LivePrice
                    live = await session.get(LivePrice, symbol)
                    if live and live.open is not None and live.price is not None:
                        # Use first and last cached timestamps for the summary bar range
                        first_ts = cached_data[0].get("timestamp", "")
                        last_ts = cached_data[-1].get("timestamp", "")
                        summary_bar = {
                            "timestamp": first_ts,
                            "open": float(live.open),
                            "high": float(live.high) if live.high else float(live.price),
                            "low": float(live.low) if live.low else float(live.price),
                            "close": float(live.price),
                            "volume": int(live.volume) if live.volume else 0,
                        }
                        logger.info(f"Replacing {len(cached_data)} flat bars with LivePrice summary for {symbol}: "
                                    f"O={summary_bar['open']} H={summary_bar['high']} "
                                    f"L={summary_bar['low']} C={summary_bar['close']}")
                        return [summary_bar]
                return cached_data
            return []

        # Only mark as 'eodhd' source if data covers most of the trading day.
        # Otherwise keep as 'live' so we retry on next request.
        is_complete = len(data) >= min_complete_bars
        source_label = "eodhd" if is_complete else "live"
        if not is_complete:
            logger.info(f"Storing incomplete data for {symbol} ({len(data)} bars), keeping source='live' for retry")

            # If cached data has more records, prefer it
            if cached_data and len(cached_data) >= len(data):
                logger.info(f"Cached data has more records ({len(cached_data)} vs {len(data)}), keeping cached")
                return cached_data

        count = await cache.store_intraday_prices(session, symbol, data, source=source_label)
        await cache.update_cache_metadata(
            session,
            cache_key,
            "intraday_prices",
            symbol,
            cache_ttl,
            count,
        )
        await session.commit()

        total_time = (time.time() - start_time) * 1000
        log_timing(endpoint, False, cache_time, eodhd_time, total_time)

        return data


@router.get("/real-time/{symbol}")
async def get_real_time_quote(
    symbol: str,
    api_token: str = Query(None),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Get real-time quote for a symbol (from cached live_prices or EODHD).

    When market is closed, returns cached data without calling EODHD.
    """
    from sqlalchemy import select
    from data_server.db.models import LivePrice

    # Determine exchange from symbol (e.g., "005930.KO" -> "KO", "AAPL.US" -> "US")
    exchange_code = symbol.split(".")[-1] if "." in symbol else "US"
    market_open = is_exchange_market_open(exchange_code)

    # Check if we have a cached live price in the database
    result = await session.execute(
        select(LivePrice).where(LivePrice.ticker == symbol)
    )
    live_price = result.scalar_one_or_none()

    # Helper to format live price response
    def format_live_price(lp):
        return {
            "code": symbol,
            "timestamp": int(lp.market_timestamp.timestamp()) if lp.market_timestamp else None,
            "gmtoffset": 0,
            "open": float(lp.open) if lp.open else None,
            "high": float(lp.high) if lp.high else None,
            "low": float(lp.low) if lp.low else None,
            "close": float(lp.price) if lp.price else None,
            "volume": lp.volume,
            "previousClose": float(lp.previous_close) if lp.previous_close else None,
            "change": float(lp.change) if lp.change else None,
            "change_p": float(lp.change_percent) if lp.change_percent else None,
        }

    # If market is closed, return cached data (no EODHD call needed)
    if not market_open:
        if live_price:
            logger.info(f"[MARKET CLOSED] Returning cached price for {symbol}")
            return format_live_price(live_price)
        else:
            # No cached data and market closed - return empty response
            logger.info(f"[MARKET CLOSED] No cached price for {symbol}")
            return {"code": symbol, "close": None, "change": None, "change_p": None}

    # Market is open - check if cached price is fresh enough (less than 30 seconds old)
    if live_price and live_price.updated_at:
        age = (datetime.utcnow() - live_price.updated_at).total_seconds()
        if age < 30:
            logger.debug(f"Returning cached live price for {symbol} (age: {age:.1f}s)")
            return format_live_price(live_price)

    # Market is open and cached price is stale - fetch from EODHD
    client = await get_eodhd_client()
    try:
        data = await client.get_real_time(symbol)
    except Exception as e:
        logger.error(f"EODHD error: {e}")
        raise HTTPException(status_code=502, detail="Error fetching from EODHD API")

    return data


@router.get("/live-prices")
async def get_all_live_prices(
    api_token: str = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Get all cached live prices for tracked stocks."""
    from sqlalchemy import select
    from data_server.db.models import LivePrice

    result = await session.execute(select(LivePrice))
    prices = result.scalars().all()

    return [
        {
            "ticker": p.ticker,
            "exchange": p.exchange,
            "price": float(p.price) if p.price else None,
            "open": float(p.open) if p.open else None,
            "high": float(p.high) if p.high else None,
            "low": float(p.low) if p.low else None,
            "previous_close": float(p.previous_close) if p.previous_close else None,
            "change": float(p.change) if p.change else None,
            "change_percent": float(p.change_percent) if p.change_percent else None,
            "volume": p.volume,
            "market_timestamp": p.market_timestamp.isoformat() if p.market_timestamp else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in prices
    ]


async def _enrich_with_live_market_cap(session: AsyncSession, symbol: str, company: dict) -> dict:
    """Calculate market cap dynamically using shares_outstanding × current_price."""
    shares = company.get("shares_outstanding")
    if not shares:
        return company  # Can't calculate without shares

    # Get live price
    from data_server.db.models import LivePrice
    result = await session.execute(
        select(LivePrice).where(LivePrice.ticker == symbol)
    )
    live_price = result.scalar_one_or_none()

    if live_price and live_price.price:
        # Calculate dynamic market cap
        company = dict(company)  # Make a copy
        company["market_cap"] = int(shares * float(live_price.price))

    return company


async def _enrich_highlights_market_cap(session: AsyncSession, symbol: str, highlights: dict) -> dict:
    """Calculate market cap dynamically using best shares_outstanding × current_price.

    Priority: SEC EDGAR shares > yfinance shares > EODHD shares (from highlights).
    Non-USD market caps are converted to USD using live forex rates.
    """
    ticker = symbol.split(".")[0]

    # Try shares_history first (SEC EDGAR > yfinance > EODHD)
    best_shares = await cache.get_latest_shares_outstanding(session, ticker)
    if not best_shares:
        best_shares = highlights.get("shares_outstanding")

    if not best_shares:
        return highlights

    from data_server.db.models import LivePrice
    result = await session.execute(
        select(LivePrice).where(LivePrice.ticker == symbol)
    )
    live_price = result.scalar_one_or_none()

    highlights = dict(highlights)
    highlights["shares_outstanding"] = best_shares

    currency = highlights.get("currency", "USD")

    # Get forex rate once (needed for both live and fallback paths)
    fx_rate = None
    if currency and currency != "USD":
        from data_server.services.eodhd_client import get_forex_rate_to_usd
        fx_rate = await get_forex_rate_to_usd(currency)
        if fx_rate:
            highlights["fx_rate_to_usd"] = fx_rate

    if live_price and live_price.price:
        market_cap_local = int(best_shares * float(live_price.price))

        # Convert to USD if the stock trades in a non-USD currency
        if fx_rate:
            highlights["market_cap"] = int(market_cap_local * fx_rate)
        else:
            highlights["market_cap"] = market_cap_local
    elif best_shares:
        # No live price — use latest cached EOD close for shares × price calculation
        from data_server.db.models import DailyPrice
        last_close = None
        try:
            result = await session.execute(
                select(DailyPrice.close)
                .where(DailyPrice.ticker == symbol)
                .order_by(DailyPrice.date.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row:
                last_close = float(row)
        except Exception as e:
            logger.warning(f"Failed to query cached EOD close for {symbol}: {e}")

        if last_close and last_close > 0:
            market_cap_local = int(best_shares * last_close)
            if fx_rate:
                highlights["market_cap"] = int(market_cap_local * fx_rate)
            else:
                highlights["market_cap"] = market_cap_local
        elif fx_rate and highlights.get("market_cap"):
            # Fall back to converting raw EODHD market cap if no cached EOD data
            highlights["market_cap"] = int(highlights["market_cap"] * fx_rate)

    return highlights


@router.get("/fundamentals/{symbol}")
async def get_fundamentals(
    symbol: str,
    api_token: str = Query(None),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Get company fundamentals (cached).

    Returns structured response:
    {
        "highlights": { ... company highlights ... },
        "quarterly_financials": [ ... quarterly rows ... ]
    }
    """
    start_time = time.time()
    ticker = symbol.split(".")[0]
    cache_key = f"fundamentals:{symbol}"
    endpoint = f"GET /fundamentals/{symbol}"

    # Check cache validity
    cache_start = time.time()
    is_valid = await cache.is_cache_valid(session, cache_key, settings.cache_fundamentals)
    cache_time = (time.time() - cache_start) * 1000

    if is_valid:
        highlights = await cache.get_company_highlights(session, ticker)
        quarterly = await cache.get_quarterly_financials(session, ticker)
        if highlights:
            # Fix currency from exchange mapping if wrong (e.g., ADR data cached)
            exchange_part_cached = symbol.split(".")[-1] if "." in symbol else "US"
            expected_cur = _EXCHANGE_TO_CURRENCY.get(exchange_part_cached)
            if expected_cur and highlights.get("currency") != expected_cur:
                highlights["currency"] = expected_cur
                highlights["exchange"] = exchange_part_cached
            # Enrich highlights with dynamic market cap
            highlights = await _enrich_highlights_market_cap(session, symbol, highlights)
            # Extract ETF fields from highlights
            asset_type = highlights.pop("asset_type", None)
            etf_data = highlights.pop("etf_data", None)
            total_time = (time.time() - start_time) * 1000
            log_timing(endpoint, True, cache_time, 0, total_time)
            return {
                "highlights": highlights,
                "quarterly_financials": quarterly or [],
                "discrepancies": [],
                "asset_type": asset_type,
                "etf_data": etf_data,
            }

    # Fetch from EODHD + yfinance quarterly in parallel (for cross-validation)
    from data_server.services.yfinance_client import (
        get_fundamentals as yf_fundamentals,
        get_quarterly_financials as yf_quarterly,
    )
    exchange_part = symbol.split(".")[-1] if "." in symbol else "US"

    eodhd_start = time.time()
    client = await get_eodhd_client()

    async def _fetch_eodhd():
        try:
            return await client.get_fundamentals(symbol)
        except Exception as e:
            logger.warning(f"EODHD fundamentals failed for {symbol}: {e}")
            return None

    async def _fetch_yf_quarterly():
        try:
            return await yf_quarterly(ticker, exchange_part)
        except Exception as e:
            logger.warning(f"yfinance quarterly fetch failed for {symbol}: {e}")
            return []

    data, yf_quarters = await asyncio.gather(_fetch_eodhd(), _fetch_yf_quarterly())
    eodhd_time = (time.time() - eodhd_start) * 1000

    # Fallback to yfinance when EODHD has no data
    if not data:
        try:
            data = await yf_fundamentals(ticker, exchange_part)
            if data:
                logger.info(f"Using yfinance fundamentals fallback for {symbol}")
        except Exception as e:
            logger.warning(f"yfinance fundamentals fallback failed for {symbol}: {e}")

    if not data:
        total_time = (time.time() - start_time) * 1000
        log_timing(endpoint, False, cache_time, eodhd_time, total_time)
        return {"highlights": {}, "quarterly_financials": [], "discrepancies": [], "asset_type": None, "etf_data": None}

    # Fix currency when EODHD/yfinance returns wrong currency for the requested exchange
    # e.g., ASML.AS returns currency=USD (ADR) instead of EUR, ASML.US returns EUR instead of USD
    general = data.get("General", {})
    expected_currency = _EXCHANGE_TO_CURRENCY.get(exchange_part)
    if expected_currency:
        returned_currency = general.get("CurrencyCode", "USD")
        if returned_currency != expected_currency:
            logger.info(
                f"Fixing currency for {symbol}: {returned_currency} → {expected_currency} "
                f"(exchange {exchange_part})"
            )
            general["CurrencyCode"] = expected_currency
            # Also fix the exchange if it was wrong (e.g., NASDAQ for an AS listing)
            general["Exchange"] = exchange_part

    # Store into all tables
    highlights_raw = data.get("Highlights", {})
    shares_stats = data.get("SharesStats", {})

    # 1. Store company table (backward compat)
    company_data = {
        "ticker": ticker,
        "name": general.get("Name"),
        "exchange": general.get("Exchange"),
        "sector": general.get("Sector"),
        "industry": general.get("Industry"),
        "market_cap": highlights_raw.get("MarketCapitalization") or _safe_int(data.get("ETF_Data", {}).get("TotalAssets")),
        "shares_outstanding": shares_stats.get("SharesOutstanding"),
        "pe_ratio": highlights_raw.get("PERatio"),
        "eps": highlights_raw.get("EarningsShare"),
    }
    await cache.store_company(session, company_data)

    # 2. Store company highlights
    await cache.store_company_highlights(session, ticker, data)

    # 3. Store quarterly financials
    q_count = await cache.store_quarterly_financials(session, ticker, data)

    # 3b. If EODHD had no quarterly data, use already-fetched yfinance data
    if q_count == 0 and yf_quarters:
        try:
            income_q, balance_q, cashflow_q = {}, {}, {}
            for q in yf_quarters:
                d = q["date"]
                income_q[d] = q.get("income", {})
                balance_q[d] = q.get("balance", {})
                cashflow_q[d] = q.get("cashflow", {})
            eodhd_compat = {
                "Financials": {
                    "Income_Statement": {"quarterly": income_q},
                    "Balance_Sheet": {"quarterly": balance_q},
                    "Cash_Flow": {"quarterly": cashflow_q},
                }
            }
            q_count = await cache.store_quarterly_financials(
                session, ticker, eodhd_compat, data_source="yfinance"
            )
            logger.info(f"Stored {q_count} quarterly records from yfinance for {symbol}")
        except Exception as e:
            logger.warning(f"yfinance quarterly storage failed for {symbol}: {e}")

    await cache.update_cache_metadata(
        session, cache_key, "fundamentals", ticker,
        settings.cache_fundamentals, q_count,
    )
    await session.commit()

    # 4. Fetch SEC EDGAR shares history in background (don't block response)
    async def _fetch_shares_bg():
        try:
            from data_server.db.database import async_session_factory
            from data_server.services.sec_edgar import get_sec_edgar_client
            sec_client = await get_sec_edgar_client()
            entries = await sec_client.get_shares_history(ticker)
            if entries:
                async with async_session_factory() as bg_session:
                    await cache.store_shares_history(bg_session, ticker, entries)
                    await cache.update_cache_metadata(
                        bg_session, f"shares_history:{ticker}",
                        "shares_history", ticker, 86400, len(entries),
                    )
                    await bg_session.commit()
                logger.info(f"Background SEC EDGAR fetch: {len(entries)} entries for {ticker}")
        except Exception as e:
            logger.debug(f"Background SEC EDGAR fetch failed for {ticker}: {e}")

    asyncio.create_task(_fetch_shares_bg())

    # Read back from DB for consistent response format
    highlights = await cache.get_company_highlights(session, ticker)
    quarterly = await cache.get_quarterly_financials(session, ticker)

    if highlights:
        highlights = await _enrich_highlights_market_cap(session, symbol, highlights)

    # Cross-validate EODHD vs yfinance quarterly data
    discrepancies = []
    if yf_quarters and quarterly:
        try:
            discrepancies = compare_quarterly_data(quarterly, yf_quarters)
            if discrepancies:
                logger.info(
                    f"Found {len(discrepancies)} quarterly discrepancies for {symbol}"
                )
        except Exception as e:
            logger.warning(f"Quarterly comparison failed for {symbol}: {e}")

    # Extract ETF fields from highlights
    asset_type = highlights.pop("asset_type", None) if highlights else None
    etf_data = highlights.pop("etf_data", None) if highlights else None

    total_time = (time.time() - start_time) * 1000
    log_timing(endpoint, False, cache_time, eodhd_time, total_time)

    return {
        "highlights": highlights or {},
        "quarterly_financials": quarterly or [],
        "discrepancies": discrepancies,
        "asset_type": asset_type,
        "etf_data": etf_data,
    }


@router.post("/fundamentals/{symbol}/override-quarterly")
async def override_quarterly_financials(
    symbol: str,
    request: dict,
    session: AsyncSession = Depends(get_session),
):
    """Override quarterly financial records with yfinance data.

    Request body:
    {
        "overrides": [
            {"report_date": "2025-03-31", "total_revenue": 184700000, ...},
            ...
        ]
    }

    Sets data_source='yfinance' on overridden records so they are not
    compared again on subsequent fetches.
    """
    ticker = symbol.split(".")[0]
    overrides = request.get("overrides", [])

    if not overrides:
        return {"count": 0, "quarterly_financials": []}

    count = await cache.override_quarterly_financials(session, ticker, overrides)
    await session.commit()

    logger.info(f"Overrode {count} quarterly records for {symbol} with yfinance data")

    # Return updated quarterly financials
    quarterly = await cache.get_quarterly_financials(session, ticker)
    return {
        "count": count,
        "quarterly_financials": quarterly or [],
    }


@router.get("/calendar/earnings/{symbol}")
async def get_earnings_calendar(
    symbol: str,
    session: AsyncSession = Depends(get_session),
):
    """Get upcoming and recent earnings dates for a symbol.

    Returns the next earnings date/estimate and last reported earnings.
    Cached in memory for 1 hour since earnings dates change rarely.
    """
    # Check in-memory cache
    cached = _earnings_cache.get(symbol)
    if cached:
        result, cached_at = cached
        if time.time() - cached_at < _EARNINGS_CACHE_TTL:
            return result

    from datetime import date as date_type

    client = await get_eodhd_client()

    # Fetch earnings from 6 months ago to 1 year ahead
    today = date_type.today()
    from_date = (today - timedelta(days=180)).isoformat()
    to_date = (today + timedelta(days=365)).isoformat()

    try:
        earnings = await client.get_earnings_calendar(
            symbol, from_date=from_date, to_date=to_date
        )
    except Exception as e:
        logger.error(f"Earnings calendar failed for {symbol}: {e}")
        earnings = []

    # Split into past (reported) and upcoming
    last_reported = None
    next_earnings = None

    for e in earnings:
        report_date = e.get("report_date")
        if not report_date:
            continue
        try:
            rd = date_type.fromisoformat(report_date)
        except ValueError:
            continue

        actual = e.get("actual")
        # EODHD uses actual=0 + percent=-100 as placeholder for unreported earnings
        is_reported = (
            actual is not None
            and not (actual == 0 and e.get("percent") == -100)
        )

        if is_reported:
            # Reported — keep the most recent
            if last_reported is None or rd > date_type.fromisoformat(last_reported["report_date"]):
                last_reported = e
        else:
            # Upcoming or very recent unreported (within 7 days)
            if rd >= today - timedelta(days=7):
                if next_earnings is None or rd < date_type.fromisoformat(next_earnings["report_date"]):
                    next_earnings = e

    # Fallback to yfinance if EODHD has no next earnings
    if not next_earnings:
        try:
            from data_server.services.yfinance_client import get_next_earnings_date
            ticker = symbol.split(".")[0]
            exchange = symbol.split(".")[-1] if "." in symbol else "US"
            yf_earnings = await get_next_earnings_date(ticker, exchange)
            if yf_earnings:
                next_earnings = yf_earnings
                logger.info(f"Using yfinance earnings date for {symbol}: {yf_earnings.get('report_date')}")
        except Exception as e:
            logger.debug(f"yfinance earnings fallback failed for {symbol}: {e}")

    result = {
        "symbol": symbol,
        "next_earnings": next_earnings,
        "last_reported": last_reported,
    }

    # Store in cache
    _earnings_cache[symbol] = (result, time.time())

    return result


@router.get("/shares-history/{symbol}")
async def get_shares_history(
    symbol: str,
    session: AsyncSession = Depends(get_session),
):
    """Get historical shares outstanding data for a symbol.

    On cache miss: fetches from SEC EDGAR, falls back to yfinance.
    """
    start_time = time.time()
    ticker = symbol.split(".")[0]
    exchange = symbol.split(".")[-1] if "." in symbol else "US"
    cache_key = f"shares_history:{ticker}"
    endpoint = f"GET /shares-history/{symbol}"

    # Check cache — refresh daily
    cache_start = time.time()
    is_valid = await cache.is_cache_valid(session, cache_key, 86400)
    cache_time = (time.time() - cache_start) * 1000

    if is_valid:
        history = await cache.get_shares_history(session, ticker)
        if history:
            latest = await cache.get_latest_shares_outstanding(session, ticker)
            total_time = (time.time() - start_time) * 1000
            log_timing(endpoint, True, cache_time, 0, total_time)
            return {
                "ticker": ticker,
                "shares_history": history,
                "latest_shares_outstanding": latest,
            }

    # Fetch from SEC EDGAR
    fetch_start = time.time()
    entries = []
    try:
        from data_server.services.sec_edgar import get_sec_edgar_client
        sec_client = await get_sec_edgar_client()
        entries = await sec_client.get_shares_history(ticker)
    except Exception as e:
        logger.error(f"SEC EDGAR error for {ticker}: {e}")

    # Fallback to yfinance if SEC EDGAR returned nothing
    if not entries:
        try:
            from data_server.services.yfinance_client import get_shares_history_entry
            yf_entry = await get_shares_history_entry(ticker, exchange)
            if yf_entry:
                entries = [yf_entry]
        except Exception as e:
            logger.error(f"yfinance error for {ticker}: {e}")

    fetch_time = (time.time() - fetch_start) * 1000

    # Store results
    if entries:
        await cache.store_shares_history(session, ticker, entries)
        await cache.update_cache_metadata(
            session, cache_key, "shares_history", ticker, 86400, len(entries)
        )
        await session.commit()

    # Read back
    history = await cache.get_shares_history(session, ticker)
    latest = await cache.get_latest_shares_outstanding(session, ticker)

    total_time = (time.time() - start_time) * 1000
    log_timing(endpoint, False, cache_time, fetch_time, total_time)

    return {
        "ticker": ticker,
        "shares_history": history,
        "latest_shares_outstanding": latest,
    }


@router.get("/news")
async def get_news(
    api_token: str = Query(None),
    s: Optional[str] = Query(None, description="Symbol (e.g., AAPL.US)"),
    from_: Optional[str] = Query(None, alias="from", description="Start date"),
    to: Optional[str] = Query(None, description="End date"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Get news articles from cache only.

    News is populated by the background news worker every 15 minutes.
    This endpoint only returns cached data - it never fetches from EODHD directly.
    """
    start_time = time.time()
    ticker = s.split(".")[0] if s else None
    endpoint = f"GET /news?s={s}&limit={limit}"

    if not ticker:
        # General news not supported in cache-only mode
        return []

    # Return cached news only
    fetch_start = time.time()
    cached_data = await cache.get_news_for_ticker(session, ticker, limit, offset)
    fetch_time = (time.time() - fetch_start) * 1000
    total_time = (time.time() - start_time) * 1000

    logger.info(f"[CACHE] {endpoint} | fetch: {fetch_time:.1f}ms | total: {total_time:.1f}ms | {len(cached_data)} articles")
    return cached_data


@router.post("/news/update")
async def update_news():
    """Trigger a bulk news update for all tracked stocks."""
    from data_server.workers.news_worker import update_news as run_news_update

    result = await run_news_update()
    return result or {"total_articles": 0, "tickers": 0, "errors": 0}


@router.post("/fundamentals/update")
async def update_all_fundamentals():
    """Bulk-update quarterly financials for all tracked stocks.

    Bypasses the cache TTL and fetches fresh data from EODHD + yfinance
    for every tracked ticker.  After storing EODHD data it cross-validates
    against yfinance:
      - Quarters that yfinance has but EODHD doesn't → auto-stored from yfinance
      - Quarters where EODHD and yfinance differ >5% → auto-overridden with yfinance
    """
    from data_server.api.tracking import get_tracked_tickers
    from data_server.db.database import async_session_factory
    from data_server.services.yfinance_client import (
        get_fundamentals as yf_fundamentals,
        get_quarterly_financials as yf_quarterly,
    )

    async with async_session_factory() as session:
        symbols = await get_tracked_tickers(session)

    if not symbols:
        return {"updated": 0, "tickers": 0, "errors": 0, "quarters": 0,
                "yf_missing_filled": 0, "yf_overrides": 0}

    logger.info(f"Starting bulk fundamentals update for {len(symbols)} stocks")

    updated = 0
    errors = 0
    total_quarters = 0
    total_yf_missing = 0
    total_yf_overrides = 0

    client = await get_eodhd_client()

    for symbol in symbols:
        ticker = symbol.split(".")[0]
        exchange_part = symbol.split(".")[-1] if "." in symbol else "US"

        try:
            # Fetch EODHD + yfinance in parallel
            async def _fetch_eodhd(s=symbol):
                try:
                    return await client.get_fundamentals(s)
                except Exception as e:
                    logger.warning(f"EODHD fundamentals failed for {s}: {e}")
                    return None

            async def _fetch_yf(t=ticker, ex=exchange_part):
                try:
                    return await yf_quarterly(t, ex)
                except Exception:
                    return []

            data, yf_quarters = await asyncio.gather(_fetch_eodhd(), _fetch_yf())

            # Fallback to yfinance fundamentals if EODHD empty
            if not data:
                try:
                    data = await yf_fundamentals(ticker, exchange_part)
                except Exception:
                    pass

            if not data:
                logger.debug(f"No fundamentals data for {symbol}")
                continue

            async with async_session_factory() as session:
                # Store company + highlights
                general = data.get("General", {})
                highlights_raw = data.get("Highlights", {})
                shares_stats = data.get("SharesStats", {})
                company_data = {
                    "ticker": ticker,
                    "name": general.get("Name"),
                    "exchange": general.get("Exchange"),
                    "sector": general.get("Sector"),
                    "industry": general.get("Industry"),
                    "market_cap": highlights_raw.get("MarketCapitalization") or _safe_int(data.get("ETF_Data", {}).get("TotalAssets")),
                    "shares_outstanding": shares_stats.get("SharesOutstanding"),
                    "pe_ratio": highlights_raw.get("PERatio"),
                    "eps": highlights_raw.get("EarningsShare"),
                }
                await cache.store_company(session, company_data)
                await cache.store_company_highlights(session, ticker, data)

                # Store quarterly financials from EODHD
                q_count = await cache.store_quarterly_financials(session, ticker, data)

                if yf_quarters:
                    # Get the set of EODHD quarter dates we just stored
                    financials = data.get("Financials", {})
                    eodhd_dates = set()
                    for section in ("Income_Statement", "Balance_Sheet", "Cash_Flow"):
                        eodhd_dates |= set(
                            financials.get(section, {}).get("quarterly", {}).keys()
                        )

                    yf_dates = {q["date"] for q in yf_quarters if q.get("date")}

                    # --- Fill missing quarters from yfinance ---
                    missing_dates = yf_dates - eodhd_dates
                    if missing_dates:
                        missing_qs = [q for q in yf_quarters if q.get("date") in missing_dates]
                        income_q, balance_q, cashflow_q = {}, {}, {}
                        for q in missing_qs:
                            d = q["date"]
                            income_q[d] = q.get("income", {})
                            balance_q[d] = q.get("balance", {})
                            cashflow_q[d] = q.get("cashflow", {})
                        eodhd_compat = {
                            "Financials": {
                                "Income_Statement": {"quarterly": income_q},
                                "Balance_Sheet": {"quarterly": balance_q},
                                "Cash_Flow": {"quarterly": cashflow_q},
                            }
                        }
                        filled = await cache.store_quarterly_financials(
                            session, ticker, eodhd_compat, data_source="yfinance"
                        )
                        q_count += filled
                        total_yf_missing += filled
                        if filled:
                            logger.info(
                                f"{symbol}: filled {filled} missing quarter(s) from yfinance "
                                f"({', '.join(sorted(missing_dates))})"
                            )

                    # --- Cross-validate and auto-override discrepancies ---
                    stored_quarters = await cache.get_quarterly_financials(session, ticker)
                    if stored_quarters:
                        discrepancies = compare_quarterly_data(stored_quarters, yf_quarters)
                        if discrepancies:
                            overrides = [d["yfinance_record"] for d in discrepancies]
                            override_count = await cache.override_quarterly_financials(
                                session, ticker, overrides
                            )
                            total_yf_overrides += override_count
                            if override_count:
                                logger.info(
                                    f"{symbol}: auto-overrode {override_count} quarter(s) "
                                    f"with yfinance data (>5% discrepancy)"
                                )

                elif q_count == 0:
                    # No yfinance quarterly and EODHD had nothing either
                    logger.debug(f"No quarterly data from any source for {symbol}")

                # Update cache metadata so GET endpoint knows it's fresh
                cache_key = f"fundamentals:{symbol}"
                await cache.update_cache_metadata(
                    session, cache_key, "fundamentals", ticker,
                    settings.cache_fundamentals, q_count,
                )
                await session.commit()

            total_quarters += q_count
            updated += 1

            # Small delay to avoid overwhelming APIs
            await asyncio.sleep(0.2)

        except Exception as e:
            logger.warning(f"Failed to update fundamentals for {symbol}: {e}")
            errors += 1

    logger.info(
        f"Bulk fundamentals update complete: {updated}/{len(symbols)} stocks, "
        f"{total_quarters} quarters, {errors} errors, "
        f"{total_yf_missing} yf-filled, {total_yf_overrides} yf-overrides"
    )
    return {
        "updated": updated,
        "tickers": len(symbols),
        "errors": errors,
        "quarters": total_quarters,
        "yf_missing_filled": total_yf_missing,
        "yf_overrides": total_yf_overrides,
    }


@router.get("/search/{query}")
async def search_symbols(
    query: str,
    api_token: str = Query(None),
    limit: int = Query(15, ge=1, le=50),
    exchange: Optional[str] = Query(None),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Search for symbols from EODHD + yfinance, merged and deduplicated."""
    import asyncio as _asyncio
    from data_server.services.yfinance_client import search as yf_search

    # Search both sources in parallel
    client = await get_eodhd_client()

    async def _eodhd_search():
        try:
            return await client.search(query, limit, exchange)
        except Exception as e:
            logger.error(f"EODHD search error: {e}")
            return []

    eodhd_results, yf_results = await _asyncio.gather(
        _eodhd_search(),
        yf_search(query, max_results=limit, exchange=exchange),
    )

    # Merge: deduplicate by ticker+exchange, interleave so yfinance-only
    # results (e.g. Japanese stocks) appear near the top, not pushed out
    # by dozens of obscure EODHD exchange variants.
    seen = set()
    eodhd_deduped = []
    for item in eodhd_results:
        key = (item.get("Code", "").upper(), item.get("Exchange", "").upper())
        if key not in seen:
            seen.add(key)
            eodhd_deduped.append(item)

    yf_unique = []
    for item in yf_results:
        key = (item.get("Code", "").upper(), item.get("Exchange", "").upper())
        if key not in seen:
            seen.add(key)
            yf_unique.append(item)

    # Interleave: take from each source alternately, EODHD first
    merged = []
    ei, yi = 0, 0
    while ei < len(eodhd_deduped) or yi < len(yf_unique):
        # Take 2 from EODHD, then 1 from yfinance
        for _ in range(2):
            if ei < len(eodhd_deduped):
                merged.append(eodhd_deduped[ei])
                ei += 1
        if yi < len(yf_unique):
            merged.append(yf_unique[yi])
            yi += 1

    return merged[:limit]


@router.get("/exchanges-list")
async def get_exchanges_list(
    api_token: str = Query(None),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Get list of exchanges (cached)."""
    cache_key = "exchanges-list"

    # Check cache validity
    if await cache.is_cache_valid(session, cache_key, settings.cache_company_info):
        logger.debug(f"Cache hit for {cache_key}")
        # For exchanges, we don't store in DB, just use cache metadata
        pass

    # Fetch from EODHD
    client = await get_eodhd_client()
    try:
        data = await client.get_exchanges_list()
    except Exception as e:
        logger.error(f"EODHD error: {e}")
        raise HTTPException(status_code=502, detail="Error fetching from EODHD API")

    # Update cache metadata
    await cache.update_cache_metadata(
        session, cache_key, "exchanges", None, settings.cache_company_info, len(data)
    )
    await session.commit()

    return data


@router.get("/exchange-symbol-list/{exchange}")
async def get_exchange_symbols(
    exchange: str,
    api_token: str = Query(None),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Get symbols for an exchange (cached)."""
    cache_key = f"exchange-symbols:{exchange}"

    # Check cache validity
    if await cache.is_cache_valid(session, cache_key, settings.cache_company_info):
        logger.debug(f"Cache hit for {cache_key}")
        pass

    # Fetch from EODHD
    client = await get_eodhd_client()
    try:
        data = await client.get_exchange_symbol_list(exchange)
    except Exception as e:
        logger.error(f"EODHD error: {e}")
        raise HTTPException(status_code=502, detail="Error fetching from EODHD API")

    # Update cache metadata
    await cache.update_cache_metadata(
        session, cache_key, "exchange_symbols", None, settings.cache_company_info, len(data)
    )
    await session.commit()

    return data


# Content API (new endpoints)
@router.get("/content/{content_id}")
async def get_content(
    content_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get full content by ID."""
    content = await cache.get_content(session, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    return content


@router.post("/content/batch")
async def get_content_batch(
    content_ids: list[str],
    session: AsyncSession = Depends(get_session),
):
    """Get multiple content items by IDs."""
    return await cache.get_content_batch(session, content_ids)


# Batch API (for treemap optimization)
@router.post("/batch/daily-changes")
async def get_batch_daily_changes(
    request: dict,
    session: AsyncSession = Depends(get_session),
):
    """
    Get daily price changes for multiple symbols in a single call.

    Request body:
    {
        "symbols": ["AAPL.US", "GOOGL.US", ...],
        "start_date": "2026-01-03",
        "end_date": "2026-02-02",
        "daily_change": false
    }

    When daily_change=true, compares the last 2 trading days (prev close vs last close).
    When daily_change=false (default), compares start of range to end of range.

    Returns:
    {
        "AAPL.US": {"start_price": 150.0, "end_price": 155.0, "change": 0.0333},
        ...
    }
    """
    start_time = time.time()
    symbols = request.get("symbols", [])
    start_date = request.get("start_date")
    end_date = request.get("end_date")
    daily_change = request.get("daily_change", False)

    if not symbols:
        return {}

    logger.info(f"Batch daily changes: {len(symbols)} symbols, {start_date} to {end_date}, daily_change={daily_change}")

    # Parse dates
    from_date = datetime.fromisoformat(start_date) if start_date else None
    to_date = datetime.fromisoformat(end_date) if end_date else None

    results = {}
    client = await get_eodhd_client()
    symbols_to_fetch = []

    # First pass: check cache for all symbols
    for symbol in symbols:
        try:
            # Get all prices in the date range from cache
            prices = await cache.get_daily_prices(session, symbol, from_date, to_date)

            if prices and len(prices) >= 2:
                if daily_change:
                    # Compare last 2 trading days (1D change)
                    start_price = prices[-2].get("adjusted_close") or prices[-2].get("close")
                    end_price = prices[-1].get("close")
                else:
                    # Compare start to end of range
                    start_price = prices[0].get("adjusted_close") or prices[0].get("close")
                    end_price = prices[-1].get("close")

                if start_price is not None and end_price is not None and start_price != 0:
                    change = (end_price - start_price) / start_price
                    results[symbol] = {
                        "start_price": float(start_price),
                        "end_price": float(end_price),
                        "change": float(change)
                    }
                else:
                    # Have data but missing prices, try to fetch fresh
                    symbols_to_fetch.append(symbol)
            else:
                # Less than 2 days in cache, need to fetch from EODHD
                symbols_to_fetch.append(symbol)
        except Exception as e:
            logger.debug(f"Cache lookup failed for {symbol}: {e}")
            symbols_to_fetch.append(symbol)

    cache_time = (time.time() - start_time) * 1000
    logger.info(f"Batch cache lookup: {len(results)} hits, {len(symbols_to_fetch)} misses in {cache_time:.1f}ms")

    # Second pass: fetch missing symbols from EODHD concurrently
    if symbols_to_fetch:
        async def fetch_symbol(symbol: str):
            try:
                data = await client.get_eod(symbol, start_date, end_date)
                if data and len(data) > 0:
                    await cache.store_daily_prices(session, symbol, data)
                    # Data is ordered by date ASC from EODHD
                    if daily_change and len(data) >= 2:
                        # Compare last 2 trading days
                        start_price = data[-2].get("adjusted_close") or data[-2].get("close")
                        end_price = data[-1].get("close")
                    else:
                        # Compare start to end of range
                        start_price = data[0].get("adjusted_close") or data[0].get("close")
                        end_price = data[-1].get("close")

                    if start_price is not None and end_price is not None and start_price != 0:
                        change = (end_price - start_price) / start_price
                        return symbol, {
                            "start_price": float(start_price),
                            "end_price": float(end_price),
                            "change": float(change)
                        }
                    elif end_price is not None:
                        return symbol, {
                            "start_price": None,
                            "end_price": float(end_price),
                            "change": 0
                        }
                return symbol, None
            except Exception as e:
                logger.debug(f"EODHD fetch failed for {symbol}: {e}")
                return symbol, None

        # Limit concurrent EODHD requests
        semaphore = asyncio.Semaphore(10)

        async def fetch_with_semaphore(symbol):
            async with semaphore:
                return await fetch_symbol(symbol)

        tasks = [fetch_with_semaphore(symbol) for symbol in symbols_to_fetch]
        fetch_results = await asyncio.gather(*tasks)

        for symbol, data in fetch_results:
            if data is not None:
                results[symbol] = data

        await session.commit()

    total_time = (time.time() - start_time) * 1000
    logger.info(f"Batch daily changes completed: {len(results)}/{len(symbols)} symbols in {total_time:.1f}ms")

    return results


@router.post("/cache/coverage")
async def get_cache_coverage(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    """Return date-range coverage for daily and intraday data per symbol.

    Request body: {"symbols": ["AAPL.US", "NVDA.US", ...]}
    """
    symbols = body.get("symbols", [])
    if not symbols:
        return {"daily": {}, "intraday": {}}

    daily = await cache.get_daily_coverage(session, symbols)
    intraday = await cache.get_intraday_coverage(session, symbols)

    return {"daily": daily, "intraday": intraday}


@router.get("/forex/rates/{currency}")
async def get_forex_rates(
    currency: str,
    from_date: str = Query(None),
    to_date: str = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Get stored FX rates for a currency within a date range.

    Extends from_date back 7 days so the client can forward-fill
    when stock trading days don't align with FX trading days
    (different holidays, weekends, etc.).

    Returns {date: rate_to_usd} dict for use in historical price conversion.
    """
    from data_server.db.models import ForexRate
    from datetime import date as date_type

    if currency == "USD":
        return {"currency": "USD", "rates": {}}

    query = select(ForexRate).where(ForexRate.currency == currency)
    if from_date:
        # Extend back 7 days to cover weekends + holidays gap
        extended = date_type.fromisoformat(from_date) - timedelta(days=7)
        query = query.where(ForexRate.date >= extended)
    if to_date:
        query = query.where(ForexRate.date <= date_type.fromisoformat(to_date))
    query = query.order_by(ForexRate.date)

    result = await session.execute(query)
    rows = result.scalars().all()

    rates = {row.date.isoformat(): float(row.rate_to_usd) for row in rows}
    return {"currency": currency, "rates": rates}


@router.post("/forex/update")
async def update_forex_rates(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    """Fetch and store historical FX rates for given currencies.

    Request body: {"currencies": ["EUR", "KRW", ...]}
    Automatically determines date range from daily_prices table.
    Only fetches the missing gap per currency (incremental update).
    """
    from datetime import date as date_type
    from data_server.db.models import DailyPrice, ForexRate
    from data_server.services.eodhd_client import fetch_and_store_forex_history

    currencies = body.get("currencies", [])
    currencies = [c for c in currencies if c and c != "USD"]

    if not currencies:
        return {"status": "ok", "message": "No non-USD currencies to update", "results": {}}

    # Find global date range from daily_prices
    result = await session.execute(
        select(
            func.min(DailyPrice.date),
            func.max(DailyPrice.date),
        )
    )
    row = result.one_or_none()
    if not row or not row[0] or not row[1]:
        return {"status": "ok", "message": "No daily price data in database", "results": {}}

    global_from = row[0]
    global_to = row[1]
    today = date_type.today()
    # Extend to today in case daily prices haven't been fetched yet today
    target_to = max(global_to, today)

    logger.info(f"Updating forex rates for {currencies} (price range {global_from} to {global_to})")

    results = {}
    for currency in currencies:
        try:
            # Check existing coverage for this currency
            cov = await session.execute(
                select(
                    func.min(ForexRate.date),
                    func.max(ForexRate.date),
                ).where(ForexRate.currency == currency)
            )
            cov_row = cov.one_or_none()
            existing_min = cov_row[0] if cov_row else None
            existing_max = cov_row[1] if cov_row else None

            if existing_min and existing_max:
                # Only fetch gaps: before existing_min and after existing_max
                total_stored = 0

                # Gap at the start (older data we don't have yet)
                # Allow 7-day tolerance for holidays/weekends at the boundary
                if (existing_min - global_from).days > 7:
                    gap_to = existing_min - timedelta(days=1)
                    count = await fetch_and_store_forex_history(
                        currency, global_from.isoformat(), gap_to.isoformat(),
                    )
                    total_stored += count
                    logger.info(f"FX {currency}: filled start gap {global_from} to {gap_to} ({count} rates)")

                # Gap at the end (newer data)
                if existing_max < target_to:
                    gap_from = existing_max + timedelta(days=1)
                    count = await fetch_and_store_forex_history(
                        currency, gap_from.isoformat(), target_to.isoformat(),
                    )
                    total_stored += count
                    if count:
                        logger.info(f"FX {currency}: filled end gap {gap_from} to {target_to} ({count} rates)")

                if total_stored == 0:
                    results[currency] = {"status": "up_to_date", "range": f"{existing_min} to {existing_max}"}
                else:
                    results[currency] = {"stored": total_stored, "range": f"{global_from} to {target_to}"}
            else:
                # No existing data — full fetch
                count = await fetch_and_store_forex_history(
                    currency, global_from.isoformat(), target_to.isoformat(),
                )
                results[currency] = {"stored": count, "range": f"{global_from} to {target_to}"}
        except Exception as e:
            logger.warning(f"Forex update failed for {currency}: {e}")
            results[currency] = {"error": str(e)}

    return {"status": "ok", "results": results}


@router.get("/server-status")
async def get_server_status():
    """Get data server status including EODHD API call statistics."""
    from data_server.workers.scheduler import get_scheduler_status

    eodhd_stats = get_eodhd_stats()
    scheduler_status = get_scheduler_status()

    return {
        "status": "connected",
        "eodhd_api_calls": eodhd_stats["api_calls"],
        "server_start_time": eodhd_stats["server_start_time"],
        "uptime_seconds": eodhd_stats["uptime_seconds"],
        "scheduler": scheduler_status,
    }

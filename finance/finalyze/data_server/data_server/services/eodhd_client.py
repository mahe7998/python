"""EODHD API client for making actual API calls."""

import logging
import time
from datetime import datetime
from typing import Any, Optional

import httpx
from sqlalchemy import select

from data_server.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# File logger for EODHD requests - can be watched with tail -f
# Mounted volume: ./logs:/tmp/logs in docker-compose.yml
EODHD_LOG_FILE = "/tmp/logs/eodhd_requests.log"

# Global counter for EODHD API calls (since server startup)
_eodhd_call_count = 0
_server_start_time = datetime.utcnow()

# Tickers that returned 404 on individual real-time requests (skip in future batches)
_bad_realtime_tickers: set[str] = set()


def get_eodhd_stats() -> dict:
    """Get EODHD API statistics."""
    return {
        "api_calls": _eodhd_call_count,
        "server_start_time": _server_start_time.isoformat(),
        "uptime_seconds": (datetime.utcnow() - _server_start_time).total_seconds(),
    }


def _log_eodhd_request(endpoint: str, params: dict, response_size: int = 0, error: str = None):
    """Log EODHD request to file for monitoring."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Mask API key in params
    safe_params = {k: v for k, v in params.items() if k != "api_token"}
    if error:
        line = f"[{timestamp}] ERROR {endpoint} params={safe_params} error={error}\n"
    else:
        line = f"[{timestamp}] OK {endpoint} params={safe_params} response_size={response_size}\n"
    try:
        with open(EODHD_LOG_FILE, "a") as f:
            f.write(line)
    except Exception:
        pass  # Don't fail if logging fails


class EODHDClient:
    """Client for EODHD API."""

    def __init__(self):
        self.base_url = settings.eodhd_base_url
        self.api_key = settings.eodhd_api_key
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    def _build_url(self, endpoint: str) -> str:
        """Build full URL for an endpoint."""
        return f"{self.base_url}/{endpoint}"

    async def _request(
        self,
        endpoint: str,
        params: Optional[dict] = None,
    ) -> Any:
        """Make a request to EODHD API."""
        url = self._build_url(endpoint)
        params = params or {}
        params["api_token"] = self.api_key
        params["fmt"] = "json"

        logger.debug(f"EODHD request: {endpoint} with params {params}")

        try:
            global _eodhd_call_count
            _eodhd_call_count += 1
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            # Log successful request
            response_size = len(data) if isinstance(data, list) else 1
            _log_eodhd_request(endpoint, params, response_size=response_size)
            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"EODHD HTTP error: {e.response.status_code} - {e.response.text}")
            _log_eodhd_request(endpoint, params, error=f"HTTP {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"EODHD request error: {e}")
            _log_eodhd_request(endpoint, params, error=str(e))
            raise

    # Daily Prices
    async def get_eod(
        self,
        symbol: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        period: str = "d",
    ) -> list[dict]:
        """Get end-of-day prices."""
        params = {"period": period}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        data = await self._request(f"eod/{symbol}", params)
        return data if isinstance(data, list) else []

    # Intraday Prices
    async def get_intraday(
        self,
        symbol: str,
        interval: str = "1m",
        from_timestamp: Optional[int] = None,
        to_timestamp: Optional[int] = None,
    ) -> list[dict]:
        """Get intraday prices."""
        params = {"interval": interval}
        if from_timestamp:
            params["from"] = from_timestamp
        if to_timestamp:
            params["to"] = to_timestamp

        data = await self._request(f"intraday/{symbol}", params)
        return data if isinstance(data, list) else []

    # Real-time Quote
    async def get_real_time(self, symbol: str) -> dict:
        """Get real-time quote for a single symbol."""
        data = await self._request("real-time/" + symbol, {})
        return data if isinstance(data, dict) else {}

    async def get_real_time_batch(self, symbols: list[str], chunk_size: int = 25) -> list[dict]:
        """Get real-time quotes for multiple symbols in chunked batch requests.

        EODHD batch endpoint: /real-time/{first_symbol}?s=sym1,sym2,sym3
        Sends symbols in chunks to avoid URL length limits and isolate
        failures from bad/delisted tickers. Failed chunks fall back to
        individual requests; tickers that 404 individually are cached to
        avoid retrying every 15 seconds.
        """
        global _bad_realtime_tickers

        if not symbols:
            return []

        # Filter out known-bad tickers
        good_symbols = [s for s in symbols if s not in _bad_realtime_tickers]
        if not good_symbols:
            return []

        if len(good_symbols) == 1:
            quote = await self.get_real_time(good_symbols[0])
            return [quote] if quote else []

        # Split into chunks to avoid URL length limits and isolate bad tickers
        all_quotes = []
        failed_symbols = []
        for i in range(0, len(good_symbols), chunk_size):
            chunk = good_symbols[i:i + chunk_size]
            try:
                first_symbol = chunk[0]
                params = {"s": ",".join(chunk)}
                data = await self._request(f"real-time/{first_symbol}", params)

                if isinstance(data, list):
                    all_quotes.extend(data)
                elif isinstance(data, dict):
                    all_quotes.append(data)
            except Exception as e:
                logger.warning(f"Batch chunk failed ({len(chunk)} symbols), falling back to individual")
                failed_symbols.extend(chunk)

        # Retry failed symbols individually so valid tickers still get updates
        if failed_symbols:
            recovered = 0
            for sym in failed_symbols:
                try:
                    quote = await self.get_real_time(sym)
                    if quote:
                        all_quotes.append(quote)
                        recovered += 1
                except Exception:
                    _bad_realtime_tickers.add(sym)
                    logger.info(f"Marked {sym} as bad for real-time (will skip in future batches)")
            logger.info(f"Recovered {recovered}/{len(failed_symbols)} quotes via individual fallback "
                       f"({len(_bad_realtime_tickers)} total bad tickers cached)")

        return all_quotes

    # Fundamentals
    async def get_fundamentals(self, symbol: str) -> dict:
        """Get company fundamentals."""
        data = await self._request(f"fundamentals/{symbol}")
        return data if isinstance(data, dict) else {}

    # News
    async def get_news(
        self,
        symbol: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Get news articles."""
        params = {"limit": limit, "offset": offset}
        if symbol:
            params["s"] = symbol
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        data = await self._request("news", params)
        return data if isinstance(data, list) else []

    # Calendar / Earnings
    async def get_earnings_calendar(
        self,
        symbol: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> list[dict]:
        """Get upcoming and historical earnings dates."""
        params = {"symbols": symbol}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        data = await self._request("calendar/earnings", params)
        if isinstance(data, dict):
            return data.get("earnings", [])
        return []

    # Search
    async def search(
        self,
        query: str,
        limit: int = 15,
        exchange: Optional[str] = None,
    ) -> list[dict]:
        """Search for tickers."""
        params = {"query_string": query, "limit": limit}
        if exchange:
            params["exchange"] = exchange

        data = await self._request("search/" + query, params)
        return data if isinstance(data, list) else []

    # Exchanges
    async def get_exchanges_list(self) -> list[dict]:
        """Get list of exchanges."""
        data = await self._request("exchanges-list")
        return data if isinstance(data, list) else []

    async def get_exchange_symbol_list(self, exchange: str) -> list[dict]:
        """Get symbols for an exchange."""
        data = await self._request(f"exchange-symbol-list/{exchange}")
        return data if isinstance(data, list) else []


# Global client instance
_client: Optional[EODHDClient] = None


async def get_eodhd_client() -> EODHDClient:
    """Get or create EODHD client instance."""
    global _client
    if _client is None:
        _client = EODHDClient()
    return _client


async def close_eodhd_client():
    """Close the EODHD client."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


# --- Forex rate cache ---
_forex_cache: dict[str, tuple[float, float]] = {}  # currency -> (rate_to_usd, monotonic_ts)
_FOREX_CACHE_TTL = 3600  # 1 hour


async def get_forex_rate_to_usd(currency: str) -> Optional[float]:
    """Get the latest exchange rate from currency to USD (e.g., HKD -> 0.128).

    Returns 1.0 for USD. Uses three-tier caching:
    1. In-memory cache (1 hour TTL) — fastest
    2. Database cache (latest row, 1 day TTL) — persists across restarts
    3. EODHD API fetch — refreshes both caches
    """
    if currency == "USD":
        return 1.0

    now = time.monotonic()

    # Tier 1: In-memory cache
    if currency in _forex_cache:
        rate, ts = _forex_cache[currency]
        if now - ts < _FOREX_CACHE_TTL:
            return rate

    # Tier 2: Database cache (latest row, 1 day TTL)
    try:
        from data_server.db.database import async_session_factory
        from data_server.db.models import ForexRate
        from datetime import datetime as dt, timedelta

        async with async_session_factory() as session:
            result = await session.execute(
                select(ForexRate)
                .where(ForexRate.currency == currency)
                .order_by(ForexRate.date.desc())
                .limit(1)
            )
            cached = result.scalar_one_or_none()
            if cached and cached.updated_at:
                age = dt.utcnow() - cached.updated_at
                if age < timedelta(days=1):
                    rate = float(cached.rate_to_usd)
                    _forex_cache[currency] = (rate, now)
                    logger.debug(f"Forex rate {currency}/USD = {rate:.8f} (from DB date={cached.date}, age={age})")
                    return rate
    except Exception as e:
        logger.debug(f"DB forex cache lookup failed for {currency}: {e}")

    # Tier 3: Fetch latest from EODHD API (last 10 days)
    from datetime import datetime as dt
    today = dt.utcnow().date()
    from_date = today - timedelta(days=10)
    rates = await _fetch_forex_history_from_eodhd(currency, from_date.isoformat(), today.isoformat())

    if rates:
        # Store all fetched rates in DB
        await _store_forex_rates_in_db(currency, rates)
        # Use the latest rate
        latest_date = max(rates.keys())
        rate = rates[latest_date]
        _forex_cache[currency] = (rate, now)
        return rate

    # Fallback to stale in-memory or DB value
    if currency in _forex_cache:
        return _forex_cache[currency][0]

    return None


async def _fetch_forex_history_from_eodhd(
    currency: str, from_date: str, to_date: str,
) -> dict[str, float]:
    """Fetch forex rate history from EODHD API.

    Returns dict of {date_str: rate_to_usd} using the inverse pair USD/{currency}.
    """
    client = await get_eodhd_client()
    rates: dict[str, float] = {}

    # Handle GBp (pence) → use GBP pair and divide by 100
    forex_currency = currency
    pence_divisor = 1.0
    if currency == "GBp":
        forex_currency = "GBP"
        pence_divisor = 100.0

    # Strategy 1: EOD inverse pair USD{currency}.FOREX → compute 1/rate per day
    try:
        eod_data = await client.get_eod(
            f"USD{forex_currency}.FOREX",
            from_date=from_date,
            to_date=to_date,
        )
        if eod_data:
            for bar in eod_data:
                inverse_rate = float(bar.get("close", 0))
                bar_date = bar.get("date", "")
                if inverse_rate > 0 and bar_date:
                    rates[bar_date] = (1.0 / inverse_rate) / pence_divisor
            if rates:
                logger.info(
                    f"Forex history {currency}/USD: {len(rates)} days "
                    f"({from_date} to {to_date})"
                )
                return rates
    except Exception as e:
        logger.warning(f"EOD forex history USD{forex_currency}.FOREX failed: {e}")

    # Strategy 2: Real-time for today only
    try:
        data = await client.get_real_time(f"{forex_currency}USD.FOREX")
        rate = float(data.get("close", 0))
        if rate > 0:
            from datetime import datetime as dt
            rate = rate / pence_divisor
            rates[dt.utcnow().strftime("%Y-%m-%d")] = rate
            logger.info(f"Forex rate {currency}/USD = {rate} (real-time fallback)")
            return rates
    except Exception as e:
        logger.warning(f"Real-time forex {currency}USD.FOREX failed: {e}")

    return rates


async def _store_forex_rates_in_db(currency: str, rates: dict[str, float]) -> int:
    """Store forex rate history in the database. Returns number of rows stored."""
    from data_server.db.database import async_session_factory
    from data_server.db.models import ForexRate
    from sqlalchemy.dialects.postgresql import insert
    from datetime import datetime as dt, date as date_type

    stored = 0
    try:
        async with async_session_factory() as session:
            now = dt.utcnow()
            for date_str, rate in rates.items():
                d = date_type.fromisoformat(date_str)
                stmt = insert(ForexRate).values(
                    currency=currency,
                    date=d,
                    rate_to_usd=rate,
                    updated_at=now,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["currency", "date"],
                    set_={"rate_to_usd": rate, "updated_at": now},
                )
                await session.execute(stmt)
                stored += 1
            await session.commit()
            logger.info(f"Stored {stored} forex rates for {currency}")
    except Exception as e:
        logger.warning(f"Failed to store forex rates in DB for {currency}: {e}")
    return stored


async def fetch_and_store_forex_history(
    currency: str, from_date: str, to_date: str,
) -> int:
    """Public API: fetch full forex rate history and store in DB.

    Called during "Update Database" to populate historical FX rates.
    Returns number of rates stored.
    """
    if currency == "USD":
        return 0

    rates = await _fetch_forex_history_from_eodhd(currency, from_date, to_date)
    if not rates:
        return 0

    stored = await _store_forex_rates_in_db(currency, rates)

    # Update in-memory cache with latest rate
    if rates:
        latest_date = max(rates.keys())
        _forex_cache[currency] = (rates[latest_date], time.monotonic())

    return stored

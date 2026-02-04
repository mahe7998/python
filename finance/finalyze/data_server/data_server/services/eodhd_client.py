"""EODHD API client for making actual API calls."""

import logging
from datetime import datetime
from typing import Any, Optional

import httpx

from data_server.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# File logger for EODHD requests - can be watched with tail -f
# Mounted volume: ./logs:/tmp/logs in docker-compose.yml
EODHD_LOG_FILE = "/tmp/logs/eodhd_requests.log"

# Global counter for EODHD API calls (since server startup)
_eodhd_call_count = 0
_server_start_time = datetime.utcnow()


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

    async def get_real_time_batch(self, symbols: list[str]) -> list[dict]:
        """Get real-time quotes for multiple symbols in one request.

        EODHD batch endpoint: /real-time/{first_symbol}?s=sym1,sym2,sym3
        Returns a list of quotes, one per symbol.
        """
        if not symbols:
            return []

        if len(symbols) == 1:
            # Single symbol - use regular endpoint
            quote = await self.get_real_time(symbols[0])
            return [quote] if quote else []

        # Batch request - use first symbol in path, all symbols in 's' param
        first_symbol = symbols[0]
        params = {"s": ",".join(symbols)}
        data = await self._request(f"real-time/{first_symbol}", params)

        # EODHD returns a list for batch requests
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # Single result returned as dict
            return [data]
        return []

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

        data = await self._request("search/" + query, {})
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

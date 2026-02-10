"""EODHD data provider implementation.

This provider connects to the data server (caching proxy) instead of
directly to EODHD. The data server handles all caching and rate limiting.
"""

import hashlib
import os
import time
from datetime import date, datetime
from typing import Optional, List, Dict, Any, Tuple

import requests
import pandas as pd
from loguru import logger

from investment_tool.data.models import CompanyInfo, NewsArticle, SentimentData
from investment_tool.data.providers.base import (
    DataProviderBase,
    ProviderError,
    RateLimitError,
    AuthenticationError,
    DataNotFoundError,
)


class EODHDProvider(DataProviderBase):
    """EODHD API data provider via data server proxy.

    Connects to DATA_SERVER_URL which provides caching and rate limiting.
    """

    # Use data server URL from environment, with fallback to direct EODHD
    # DATA_SERVER_URL should be the base URL (e.g., http://localhost:8000)
    # We append /api to get the API endpoint
    _data_server_url = os.getenv("DATA_SERVER_URL", "").rstrip("/")
    if _data_server_url:
        # Data server URL provided - append /api
        BASE_URL = f"{_data_server_url}/api"
    else:
        # Fallback to direct EODHD API
        BASE_URL = "https://eodhd.com/api"
    RATE_LIMIT_DELAY = 0.1  # Reduced since data server handles rate limiting

    # TTL for cached fundamentals/shares data (seconds)
    _CACHE_TTL = 300  # 5 minutes

    def __init__(self, api_key: str, cache: Optional[Any] = None):
        super().__init__(api_key, cache)
        self._last_request_time = 0.0
        self.api_call_count = 0

        # Session-level caches to avoid redundant API calls
        self._split_cache: Dict[str, List[Dict]] = {}
        self._fundamentals_cache: Dict[str, Tuple[float, Any]] = {}
        self._shares_cache: Dict[str, Tuple[float, Any]] = {}

        # Log which server we're using
        if "eodhd.com" in self.BASE_URL:
            logger.warning("DATA_SERVER_URL not set, using direct EODHD API")
        else:
            logger.info(f"Using data server at: {self.BASE_URL}")

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Make API request with rate limiting and error handling.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response data
        """
        self._rate_limit()

        if params is None:
            params = {}
        params["api_token"] = self.api_key
        params["fmt"] = "json"

        url = f"{self.BASE_URL}/{endpoint}"

        try:
            self.api_call_count += 1
            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 401:
                raise AuthenticationError(self.name)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                raise RateLimitError(
                    self.name,
                    int(retry_after) if retry_after else None
                )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            result = response.json()
            logger.debug(f"Response from {url}: status={response.status_code}, records={len(result) if isinstance(result, list) else 'N/A'}")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"EODHD request failed: {e}")
            raise ProviderError(self.name, str(e))
        except Exception as e:
            logger.error(f"EODHD unexpected error: {e}")
            raise ProviderError(self.name, str(e))

    def format_symbol(self, ticker: str, exchange: str) -> str:
        """Format symbol for EODHD API."""
        return f"{ticker}.{exchange}"

    def get_daily_prices(
        self,
        ticker: str,
        exchange: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Fetch daily OHLCV data from EODHD."""
        symbol = self.format_symbol(ticker, exchange)

        data = self._request(
            f"eod/{symbol}",
            params={
                "from": start.isoformat(),
                "to": end.isoformat(),
            }
        )

        if not data:
            raise DataNotFoundError(self.name, ticker, "daily_prices")

        df = pd.DataFrame(data)

        if df.empty:
            return df

        df["date"] = pd.to_datetime(df["date"]).dt.date

        columns = ["date", "open", "high", "low", "close", "adjusted_close", "volume"]
        for col in columns:
            if col not in df.columns:
                df[col] = None

        # Apply split adjustment to OHLC prices only
        # EODHD provides unadjusted OHLC but adjusted_close accounts for splits
        # Volume from EODHD is already in original shares, we don't adjust it
        # (volume comparisons across splits aren't meaningful anyway)
        if "adjusted_close" in df.columns and "close" in df.columns:
            # Avoid division by zero
            df["adj_factor"] = df["adjusted_close"] / df["close"].replace(0, float('nan'))
            df["adj_factor"] = df["adj_factor"].fillna(1.0)

            # Adjust OHLC prices to match adjusted_close scale
            df["open"] = df["open"] * df["adj_factor"]
            df["high"] = df["high"] * df["adj_factor"]
            df["low"] = df["low"] * df["adj_factor"]
            df["close"] = df["adjusted_close"]  # Use adjusted close

            df = df.drop(columns=["adj_factor"])

        return df[columns]

    def get_intraday_prices(
        self,
        ticker: str,
        exchange: str,
        interval: str,
        start: datetime,
        end: datetime,
        force_eodhd: bool = False,
    ) -> pd.DataFrame:
        """Fetch intraday OHLCV data from EODHD.

        Args:
            force_eodhd: If True, bypass price worker cache and fetch from EODHD API.
                        Useful when market is closed to get proper OHLC bars.
        """
        symbol = self.format_symbol(ticker, exchange)

        interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1h",
        }

        eodhd_interval = interval_map.get(interval, "5m")

        params = {
            "interval": eodhd_interval,
            "from": int(start.timestamp()),
            "to": int(end.timestamp()),
        }
        if force_eodhd:
            params["force_eodhd"] = "true"

        data = self._request(
            f"intraday/{symbol}",
            params=params
        )

        logger.debug(f"Intraday response for {symbol}: type={type(data)}, len={len(data) if data else 0}")

        if not data:
            logger.warning(f"No intraday data returned for {symbol}, data={data}")
            raise DataNotFoundError(self.name, ticker, "intraday_prices")

        df = pd.DataFrame(data)

        if df.empty:
            return df

        # Handle both formats: EODHD returns 'datetime', cache returns 'timestamp'
        if "datetime" in df.columns:
            df["timestamp"] = pd.to_datetime(df["datetime"])
        elif "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        else:
            logger.error(f"Intraday data missing timestamp field, columns: {df.columns.tolist()}")
            return pd.DataFrame()

        columns = ["timestamp", "open", "high", "low", "close", "volume"]

        for col in columns:
            if col not in df.columns:
                df[col] = None

        return df[columns]

    def _get_cached_fundamentals(self, ticker: str, exchange: str) -> Any:
        """Get fundamentals data with TTL cache."""
        key = f"{ticker}.{exchange}"
        now = time.time()
        if key in self._fundamentals_cache:
            cached_time, cached_data = self._fundamentals_cache[key]
            if now - cached_time < self._CACHE_TTL:
                logger.debug(f"Fundamentals cache hit for {key}")
                return cached_data

        symbol = self.format_symbol(ticker, exchange)
        data = self._request(f"fundamentals/{symbol}")
        if data is not None:
            self._fundamentals_cache[key] = (now, data)
        return data

    def get_company_info(self, ticker: str, exchange: str) -> CompanyInfo:
        """Fetch company metadata from EODHD or data server."""
        data = self._get_cached_fundamentals(ticker, exchange)

        if not data:
            raise DataNotFoundError(self.name, ticker, "company_info")

        # Handle structured format (data server with highlights key)
        if "highlights" in data:
            h = data["highlights"]
            return CompanyInfo(
                ticker=ticker,
                name=h.get("name", ticker),
                exchange=exchange,
                sector=h.get("sector"),
                industry=h.get("industry"),
                market_cap=h.get("market_cap"),
                country=None,
                currency=h.get("currency"),
                pe_ratio=h.get("pe_ratio"),
                eps=h.get("eps"),
                last_updated=datetime.now(),
            )
        elif "General" in data:
            # Original EODHD format (direct API)
            general = data.get("General", {})
            highlights = data.get("Highlights", {})
            return CompanyInfo(
                ticker=ticker,
                name=general.get("Name", ticker),
                exchange=exchange,
                sector=general.get("Sector"),
                industry=general.get("Industry"),
                market_cap=highlights.get("MarketCapitalization"),
                country=general.get("CountryISO"),
                currency=general.get("CurrencyCode"),
                pe_ratio=highlights.get("PERatio"),
                eps=highlights.get("EarningsShare"),
                last_updated=datetime.now(),
            )
        else:
            # Legacy data server simplified format
            return CompanyInfo(
                ticker=ticker,
                name=data.get("name", ticker),
                exchange=exchange,
                sector=data.get("sector"),
                industry=data.get("industry"),
                market_cap=data.get("market_cap"),
                country=data.get("country"),
                currency=data.get("currency"),
                pe_ratio=data.get("pe_ratio"),
                eps=data.get("eps"),
                last_updated=datetime.now(),
            )

    def get_fundamentals(self, ticker: str, exchange: str) -> Dict[str, Any]:
        """Fetch fundamental data from EODHD."""
        data = self._get_cached_fundamentals(ticker, exchange)

        if not data:
            raise DataNotFoundError(self.name, ticker, "fundamentals")

        return data

    def get_news(
        self,
        ticker: str,
        limit: int = 50,
        offset: int = 0,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[NewsArticle]:
        """Fetch news with sentiment from EODHD."""
        params = {
            "s": ticker,
            "limit": limit,
            "offset": offset,
        }
        if from_date:
            params["from"] = from_date.isoformat()
        if to_date:
            params["to"] = to_date.isoformat()

        data = self._request(f"news", params=params)

        if not data:
            return []

        articles = []
        for item in data:
            sentiment = item.get("sentiment", {})

            eodhd_sentiment = None
            if sentiment:
                eodhd_sentiment = SentimentData(
                    polarity=sentiment.get("polarity", 0),
                    positive=sentiment.get("pos", 0),
                    negative=sentiment.get("neg", 0),
                    neutral=sentiment.get("neu", 0),
                    source="eodhd",
                )

            article_id = hashlib.md5(
                f"{item.get('title', '')}{item.get('date', '')}".encode()
            ).hexdigest()

            published_at_str = item.get("date", "")
            if published_at_str:
                published_at = datetime.fromisoformat(
                    published_at_str.replace("Z", "+00:00")
                )
                # Convert to naive datetime for consistency
                if published_at.tzinfo is not None:
                    published_at = published_at.replace(tzinfo=None)
            else:
                published_at = datetime.now()

            articles.append(NewsArticle(
                id=article_id,
                ticker=ticker,
                title=item.get("title", ""),
                summary=item.get("content", "") if item.get("content") else "",
                published_at=published_at,
                source=item.get("source", "Unknown"),
                url=item.get("link", ""),
                eodhd_sentiment=eodhd_sentiment,
            ))

        return articles

    def get_split_history(self, ticker: str, exchange: str) -> List[Dict[str, Any]]:
        """Detect stock splits from raw daily price data.

        Compares adjusted_close/close ratio between consecutive days.
        A significant change in this ratio indicates a split.

        Returns list of {"date": "YYYY-MM-DD", "ratio": int} (e.g. ratio=10 for 10:1 split).
        """
        key = f"{ticker}.{exchange}"
        if key in self._split_cache:
            logger.debug(f"Split cache hit for {key}")
            return self._split_cache[key]

        symbol = self.format_symbol(ticker, exchange)

        # Fetch raw EOD data (data server returns both close and adjusted_close)
        data = self._request(
            f"eod/{symbol}",
            params={"from": "2000-01-01", "to": date.today().isoformat()},
        )
        if not data or len(data) < 2:
            self._split_cache[key] = []
            return []

        splits = []
        prev_ratio = None
        for i, row in enumerate(data):
            close = row.get("close")
            adj = row.get("adjusted_close")
            if not close or not adj or close == 0:
                continue
            ratio = adj / close
            if prev_ratio is not None and prev_ratio != 0:
                factor = ratio / prev_ratio
                rounded = round(factor)
                if rounded >= 2 and abs(factor - rounded) / rounded < 0.05:
                    splits.append({
                        "date": row["date"],
                        "ratio": rounded,
                    })
            prev_ratio = ratio

        self._split_cache[key] = splits
        return splits

    def get_shares_history(self, ticker: str, exchange: str) -> Dict[str, Any]:
        """Get shares outstanding history from data server."""
        key = f"{ticker}.{exchange}"
        now = time.time()
        if key in self._shares_cache:
            cached_time, cached_data = self._shares_cache[key]
            if now - cached_time < self._CACHE_TTL:
                logger.debug(f"Shares cache hit for {key}")
                return cached_data

        empty_result = {"ticker": ticker, "shares_history": [], "latest_shares_outstanding": None}

        if "eodhd.com" in self.BASE_URL:
            self._shares_cache[key] = (now, empty_result)
            return empty_result

        symbol = self.format_symbol(ticker, exchange)
        data = self._request(f"shares-history/{symbol}")
        if not data:
            self._shares_cache[key] = (now, empty_result)
            return empty_result
        self._shares_cache[key] = (now, data)
        return data

    def get_batch_daily_changes(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date,
        daily_change: bool = False,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch daily price changes for multiple symbols in a single call.

        This is optimized for the treemap which needs start/end prices for many stocks.
        Only works when using the data server (not direct EODHD API).

        Args:
            symbols: List of symbols like ["AAPL.US", "GOOGL.US"]
            start_date: Start date for price comparison
            end_date: End date for price comparison
            daily_change: If True, compare last 2 trading days instead of full range

        Returns:
            Dict mapping symbol to {"start_price": float, "end_price": float, "change": float}
        """
        # This endpoint only works with the data server
        if "eodhd.com" in self.BASE_URL:
            logger.warning("Batch daily changes not available with direct EODHD API")
            return {}

        url = f"{self.BASE_URL}/batch/daily-changes"

        try:
            self.api_call_count += 1
            response = requests.post(
                url,
                json={
                    "symbols": symbols,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "daily_change": daily_change,
                },
                timeout=60,  # Longer timeout for batch requests
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Batch daily changes request failed: {e}")
            return {}
        except Exception as e:
            logger.error(f"Batch daily changes unexpected error: {e}")
            return {}

    def get_all_live_prices(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all live prices from the data server.

        Returns:
            Dict mapping "TICKER.EXCHANGE" to price data
        """
        # This endpoint only works with the data server
        if "eodhd.com" in self.BASE_URL:
            logger.debug("Live prices not available with direct EODHD API")
            return {}

        url = f"{self.BASE_URL}/live-prices"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Convert list to dict keyed by symbol
            result = {}
            for item in data:
                ticker = item.get("ticker", "")
                exchange = item.get("exchange", "US")
                # Ticker may already include exchange suffix (e.g., "NVDA.US")
                # Only append exchange if ticker doesn't already have it
                if "." in ticker:
                    symbol = ticker
                else:
                    symbol = f"{ticker}.{exchange}"
                result[symbol] = {
                    "price": item.get("price"),
                    "change": item.get("change"),
                    "change_percent": item.get("change_percent"),
                    "previous_close": item.get("previous_close"),
                    "volume": item.get("volume"),
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                }
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Live prices request failed: {e}")
            return {}
        except Exception as e:
            logger.error(f"Live prices unexpected error: {e}")
            return {}

    def get_bulk_prices(
        self,
        exchange: str,
        date_val: Optional[date] = None,
    ) -> pd.DataFrame:
        """Bulk download all prices for an exchange."""
        params = {}
        if date_val:
            params["date"] = date_val.isoformat()

        data = self._request(f"eod-bulk-last-day/{exchange}", params=params)

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)

        if df.empty:
            return df

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date

        return df

    def search_tickers(
        self,
        query: str,
        limit: int = 50,
        asset_type: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> List[CompanyInfo]:
        """Search for tickers by name or symbol.

        Args:
            query: Search query (ticker, company name, or ISIN)
            limit: Maximum number of results (default 50, max 500)
            asset_type: Filter by type: stock, etf, fund, bond, index, crypto
            exchange: Filter by exchange code
        """
        # EODHD search API requires query in URL path: /api/search/{query}
        params = {"limit": limit}
        if asset_type:
            params["type"] = asset_type
        if exchange:
            params["exchange"] = exchange

        # URL-encode the query for the path
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        data = self._request(f"search/{encoded_query}", params=params)

        if not data:
            return []

        results = []
        for item in data:
            results.append(CompanyInfo(
                ticker=item.get("Code", ""),
                name=item.get("Name", ""),
                exchange=item.get("Exchange", ""),
                country=item.get("Country"),
                currency=item.get("Currency"),
                asset_type=item.get("Type"),
                isin=item.get("ISIN"),
                previous_close=item.get("previousClose"),
            ))

        return results

    def get_live_price(self, ticker: str, exchange: str) -> Optional[Dict[str, Any]]:
        """Get real-time/delayed quote for a symbol."""
        symbol = self.format_symbol(ticker, exchange)

        data = self._request(f"real-time/{symbol}")

        if not data:
            return None

        return {
            "ticker": ticker,
            "exchange": exchange,
            "price": data.get("close"),
            "open": data.get("open"),
            "high": data.get("high"),
            "low": data.get("low"),
            "volume": data.get("volume"),
            "previous_close": data.get("previousClose"),
            "change": data.get("change"),
            "change_percent": data.get("change_p"),
            "timestamp": datetime.fromtimestamp(data.get("timestamp", 0)),
        }

    def get_exchanges(self) -> List[Dict[str, str]]:
        """Get list of supported exchanges."""
        data = self._request("exchanges-list")

        if not data:
            return []

        return [
            {
                "code": ex.get("Code", ""),
                "name": ex.get("Name", ""),
                "country": ex.get("Country", ""),
                "currency": ex.get("Currency", ""),
            }
            for ex in data
        ]

    def get_exchange_symbols(self, exchange: str) -> List[Dict[str, str]]:
        """Get all symbols for an exchange."""
        data = self._request(f"exchange-symbol-list/{exchange}")

        if not data:
            return []

        return [
            {
                "ticker": sym.get("Code", ""),
                "name": sym.get("Name", ""),
                "exchange": sym.get("Exchange", exchange),
                "country": sym.get("Country", ""),
                "currency": sym.get("Currency", ""),
                "type": sym.get("Type", ""),
            }
            for sym in data
        ]

    def get_server_status(self) -> Optional[Dict[str, Any]]:
        """Get data server status including EODHD API call statistics.

        Returns:
            Server status dict with keys:
            - status: "connected" or error
            - eodhd_api_calls: number of EODHD API calls since server start
            - server_start_time: ISO timestamp of server start
            - uptime_seconds: server uptime in seconds
        """
        try:
            url = f"{self.BASE_URL}/server-status"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.debug(f"Failed to get server status: {e}")
            return None

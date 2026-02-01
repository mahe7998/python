"""EODHD data provider implementation."""

import hashlib
import time
from datetime import date, datetime
from typing import Optional, List, Dict, Any

import requests
import pandas as pd
from loguru import logger

from investment_tool.data.models import CompanyInfo, NewsArticle, SentimentData
from investment_tool.data.cache import CacheManager
from investment_tool.data.providers.base import (
    DataProviderBase,
    ProviderError,
    RateLimitError,
    AuthenticationError,
    DataNotFoundError,
)


class EODHDProvider(DataProviderBase):
    """EODHD API data provider."""

    BASE_URL = "https://eodhd.com/api"
    RATE_LIMIT_DELAY = 0.25

    def __init__(self, api_key: str, cache: CacheManager):
        super().__init__(api_key, cache)
        self._last_request_time = 0.0
        self.api_call_count = 0

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
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"EODHD request failed: {e}")
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
    ) -> pd.DataFrame:
        """Fetch intraday OHLCV data from EODHD."""
        symbol = self.format_symbol(ticker, exchange)

        interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1h",
        }

        eodhd_interval = interval_map.get(interval, "5m")

        data = self._request(
            f"intraday/{symbol}",
            params={
                "interval": eodhd_interval,
                "from": int(start.timestamp()),
                "to": int(end.timestamp()),
            }
        )

        if not data:
            raise DataNotFoundError(self.name, ticker, "intraday_prices")

        df = pd.DataFrame(data)

        if df.empty:
            return df

        df["timestamp"] = pd.to_datetime(df["datetime"])
        columns = ["timestamp", "open", "high", "low", "close", "volume"]

        for col in columns:
            if col not in df.columns:
                df[col] = None

        return df[columns]

    def get_company_info(self, ticker: str, exchange: str) -> CompanyInfo:
        """Fetch company metadata from EODHD."""
        symbol = self.format_symbol(ticker, exchange)

        data = self._request(f"fundamentals/{symbol}")

        if not data:
            raise DataNotFoundError(self.name, ticker, "company_info")

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

    def get_fundamentals(self, ticker: str, exchange: str) -> Dict[str, Any]:
        """Fetch fundamental data from EODHD."""
        symbol = self.format_symbol(ticker, exchange)

        data = self._request(f"fundamentals/{symbol}")

        if not data:
            raise DataNotFoundError(self.name, ticker, "fundamentals")

        return data

    def get_news(
        self,
        ticker: str,
        limit: int = 50,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[NewsArticle]:
        """Fetch news with sentiment from EODHD."""
        params = {
            "s": ticker,
            "limit": limit,
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
                summary=item.get("content", "")[:500] if item.get("content") else "",
                published_at=published_at,
                source=item.get("source", "Unknown"),
                url=item.get("link", ""),
                eodhd_sentiment=eodhd_sentiment,
            ))

        return articles

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

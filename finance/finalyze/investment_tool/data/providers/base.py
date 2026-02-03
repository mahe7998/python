"""Abstract base class for data providers."""

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Optional, List, Dict, Any

import pandas as pd

from investment_tool.data.models import CompanyInfo, NewsArticle


class DataProviderBase(ABC):
    """Abstract base class for all data providers."""

    def __init__(self, api_key: str, cache: Optional[Any] = None):
        self.api_key = api_key
        self.cache = cache  # Optional, data server handles caching
        self.name = self.__class__.__name__

    @abstractmethod
    def get_daily_prices(
        self,
        ticker: str,
        exchange: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """
        Fetch daily OHLCV data.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange code (e.g., 'US', 'XETRA', 'HK')
            start: Start date
            end: End date

        Returns:
            DataFrame with columns: date, open, high, low, close, adjusted_close, volume
        """
        pass

    @abstractmethod
    def get_intraday_prices(
        self,
        ticker: str,
        exchange: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Fetch intraday OHLCV data.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange code
            interval: Time interval ('1m', '5m', '15m', '1h')
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        pass

    @abstractmethod
    def get_company_info(self, ticker: str, exchange: str) -> CompanyInfo:
        """
        Fetch company metadata.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange code

        Returns:
            CompanyInfo object with company details
        """
        pass

    @abstractmethod
    def get_fundamentals(self, ticker: str, exchange: str) -> Dict[str, Any]:
        """
        Fetch fundamental data.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange code

        Returns:
            Dictionary with fundamental data
        """
        pass

    @abstractmethod
    def get_news(
        self,
        ticker: str,
        limit: int = 50,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[NewsArticle]:
        """
        Fetch news with sentiment.

        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of articles to return
            from_date: Start date for news (optional)
            to_date: End date for news (optional)

        Returns:
            List of NewsArticle objects
        """
        pass

    @abstractmethod
    def get_bulk_prices(
        self,
        exchange: str,
        date: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        Bulk download all prices for an exchange.

        Args:
            exchange: Exchange code
            date: Specific date (optional, defaults to latest)

        Returns:
            DataFrame with prices for all stocks on the exchange
        """
        pass

    @abstractmethod
    def search_tickers(
        self,
        query: str,
        limit: int = 50,
        asset_type: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> List[CompanyInfo]:
        """
        Search for tickers by name or symbol.

        Args:
            query: Search query (ticker, company name, or ISIN)
            limit: Maximum number of results
            asset_type: Filter by type: stock, etf, fund, bond, index, crypto
            exchange: Filter by exchange code

        Returns:
            List of matching CompanyInfo objects
        """
        pass

    def format_symbol(self, ticker: str, exchange: str) -> str:
        """
        Format symbol for this provider's API.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange code

        Returns:
            Formatted symbol string
        """
        return f"{ticker}.{exchange}"

    def is_available(self) -> bool:
        """
        Check if provider is available/configured.

        Returns:
            True if API key is set and provider is ready
        """
        return bool(self.api_key)


class ProviderError(Exception):
    """Base exception for provider errors."""

    def __init__(self, provider: str, message: str):
        self.provider = provider
        self.message = message
        super().__init__(f"[{provider}] {message}")


class RateLimitError(ProviderError):
    """Raised when API rate limit is exceeded."""

    def __init__(self, provider: str, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        message = "Rate limit exceeded"
        if retry_after:
            message += f", retry after {retry_after} seconds"
        super().__init__(provider, message)


class AuthenticationError(ProviderError):
    """Raised when API authentication fails."""

    def __init__(self, provider: str):
        super().__init__(provider, "Authentication failed - check API key")


class DataNotFoundError(ProviderError):
    """Raised when requested data is not found."""

    def __init__(self, provider: str, ticker: str, data_type: str):
        self.ticker = ticker
        self.data_type = data_type
        super().__init__(provider, f"Data not found: {data_type} for {ticker}")

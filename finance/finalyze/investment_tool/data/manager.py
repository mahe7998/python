"""Data manager that orchestrates data providers.

All caching is handled by the data server. This manager simply
forwards requests to providers and handles fallback.
"""

from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

import pandas as pd
from loguru import logger

from investment_tool.config.settings import AppConfig
from investment_tool.data.models import CompanyInfo, DailySentiment, NewsArticle
from investment_tool.data.storage import UserDataStore
from investment_tool.data.providers.base import DataProviderBase, ProviderError
from investment_tool.data.providers.eodhd import EODHDProvider


class DataManager:
    """Orchestrates data providers. Caching is handled by data server."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.providers: Dict[str, DataProviderBase] = {}
        self.provider_priority: List[str] = []

        # Local storage for user data only (watchlists, etc.)
        self.user_store = UserDataStore(config.data.user_data_dir)

        self._setup_providers()

    @property
    def api_call_count(self) -> int:
        """Get total API calls across all providers (local count only)."""
        total = 0
        for provider in self.providers.values():
            if hasattr(provider, 'api_call_count'):
                total += provider.api_call_count
        return total

    def get_server_status(self) -> Optional[dict]:
        """Get data server status including EODHD API call statistics.

        Returns server status from data server, or None if unavailable.
        """
        eodhd = self.providers.get("eodhd")
        if eodhd and hasattr(eodhd, 'get_server_status'):
            return eodhd.get_server_status()
        return None

    def _setup_providers(self) -> None:
        """Initialize configured data providers."""
        if self.config.api_keys.eodhd:
            self.providers["eodhd"] = EODHDProvider(self.config.api_keys.eodhd)
            self.provider_priority.append("eodhd")
            logger.info("EODHD provider initialized")

    def get_provider(self, name: str) -> Optional[DataProviderBase]:
        """Get a specific provider by name."""
        return self.providers.get(name)

    def is_connected(self) -> bool:
        """Check if at least one provider is available."""
        return any(p.is_available() for p in self.providers.values())

    def get_daily_prices(
        self,
        ticker: str,
        exchange: str,
        start: date,
        end: date,
        use_cache: bool = True,  # Ignored - data server handles caching
    ) -> Optional[pd.DataFrame]:
        """Get daily prices from data server."""
        data = self._fetch_from_providers(
            "get_daily_prices",
            ticker=ticker,
            exchange=exchange,
            start=start,
            end=end,
        )

        if data is not None and not data.empty:
            if "date" in data.columns:
                data = data.set_index("date")

        return data

    def get_intraday_prices(
        self,
        ticker: str,
        exchange: str,
        interval: str,
        start: datetime,
        end: datetime,
        use_cache: bool = True,
        force_refresh: bool = False,
    ) -> Optional[pd.DataFrame]:
        """Get intraday prices from data server.

        Args:
            force_refresh: If True, fetch from EODHD API (proper OHLC bars)
                          instead of price worker snapshots.
        """
        return self._fetch_from_providers(
            "get_intraday_prices",
            ticker=ticker,
            exchange=exchange,
            interval=interval,
            start=start,
            end=end,
            force_eodhd=force_refresh,
        )

    def get_company_info(
        self,
        ticker: str,
        exchange: str,
        use_cache: bool = True,
    ) -> Optional[CompanyInfo]:
        """Get company information.

        Always fetches from the data server (which handles its own caching)
        to ensure market_cap reflects the latest shares_outstanding × live_price.
        Local cache is only used as fallback when the server is unavailable.
        """
        company = self._fetch_from_providers(
            "get_company_info",
            ticker=ticker,
            exchange=exchange,
        )

        if company is not None:
            self.user_store.store_company(company)
            return company

        # Fallback to local cache if server is unavailable
        if use_cache:
            cached = self.user_store.get_company(ticker)
            if cached is not None:
                return cached

        return None

    def get_news(
        self,
        ticker: str,
        limit: int = 50,
        offset: int = 0,
        use_cache: bool = True,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[NewsArticle]:
        """Get news articles from data server."""
        articles = self._fetch_from_providers(
            "get_news",
            ticker=ticker,
            limit=limit,
            offset=offset,
            from_date=from_date,
            to_date=to_date,
        )
        return articles or []

    def get_daily_sentiment(
        self,
        ticker: str,
        days: int = 30,
        use_cache: bool = True,
        articles: Optional[List[NewsArticle]] = None,
    ) -> List[DailySentiment]:
        """Get daily sentiment data for a ticker.

        Args:
            ticker: Stock ticker symbol
            days: Number of days to analyze
            use_cache: Whether to use cache (ignored, kept for compatibility)
            articles: Pre-fetched articles to avoid duplicate API calls.
                      If None, articles will be fetched.
        """
        from investment_tool.analysis.sentiment import SentimentAggregator

        # Use pre-fetched articles if provided, otherwise fetch
        if articles is None:
            end = date.today()
            start = end - timedelta(days=days)

            articles = self.get_news(
                ticker,
                limit=1000,
                use_cache=use_cache,
                from_date=start,
                to_date=end,
            )

        if not articles:
            return []

        aggregator = SentimentAggregator()
        return aggregator.get_sentiment_trend(ticker, articles, days=days)

    def get_fundamentals(
        self,
        ticker: str,
        exchange: str,
    ) -> Optional[Dict[str, Any]]:
        """Get fundamental data."""
        return self._fetch_from_providers(
            "get_fundamentals",
            ticker=ticker,
            exchange=exchange,
        )

    def search_tickers(
        self,
        query: str,
        limit: int = 50,
        asset_type: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> List[CompanyInfo]:
        """Search for tickers."""
        results = self._fetch_from_providers(
            "search_tickers",
            query=query,
            limit=limit,
            asset_type=asset_type,
            exchange=exchange,
        )
        return results or []

    def get_bulk_prices(
        self,
        exchange: str,
        date_val: Optional[date] = None,
    ) -> Optional[pd.DataFrame]:
        """Get bulk prices for an exchange."""
        return self._fetch_from_providers(
            "get_bulk_prices",
            exchange=exchange,
            date_val=date_val,
        )

    def get_live_price(
        self,
        ticker: str,
        exchange: str,
    ) -> Optional[Dict[str, Any]]:
        """Get real-time price quote."""
        eodhd = self.providers.get("eodhd")
        if eodhd and isinstance(eodhd, EODHDProvider):
            try:
                return eodhd.get_live_price(ticker, exchange)
            except ProviderError as e:
                logger.warning(f"Failed to get live price: {e}")
        return None

    def get_shares_history(
        self,
        ticker: str,
        exchange: str,
    ) -> Dict[str, Any]:
        """Get shares outstanding history."""
        return self._fetch_from_providers(
            "get_shares_history",
            ticker=ticker,
            exchange=exchange,
        ) or {"ticker": ticker, "shares_history": [], "latest_shares_outstanding": None}

    def get_split_history(self, ticker: str, exchange: str) -> List[Dict]:
        """Get stock split history detected from daily price data."""
        return self._fetch_from_providers(
            "get_split_history",
            ticker=ticker,
            exchange=exchange,
        ) or []

    def get_batch_daily_changes(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date,
        daily_change: bool = False,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get daily price changes for multiple symbols in a single call.

        This is optimized for the treemap which needs start/end prices for many stocks.

        Args:
            symbols: List of symbols like ["AAPL.US", "GOOGL.US"]
            start_date: Start date for price comparison
            end_date: End date for price comparison
            daily_change: If True, compare last 2 trading days instead of full range

        Returns:
            Dict mapping symbol to {"start_price": float, "end_price": float, "change": float}
        """
        eodhd = self.providers.get("eodhd")
        if eodhd and isinstance(eodhd, EODHDProvider):
            try:
                return eodhd.get_batch_daily_changes(symbols, start_date, end_date, daily_change)
            except Exception as e:
                logger.warning(f"Failed to get batch daily changes: {e}")
        return {}

    def get_all_live_prices(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all live prices from the data server.

        Returns:
            Dict mapping "TICKER.EXCHANGE" to price data with change_percent
        """
        eodhd = self.providers.get("eodhd")
        if eodhd and isinstance(eodhd, EODHDProvider):
            try:
                return eodhd.get_all_live_prices()
            except Exception as e:
                logger.warning(f"Failed to get live prices: {e}")
        return {}

    def _fetch_from_providers(
        self,
        method: str,
        **kwargs: Any,
    ) -> Any:
        """Try providers in priority order until one succeeds."""
        for provider_name in self.provider_priority:
            provider = self.providers.get(provider_name)
            if provider and provider.is_available():
                try:
                    func = getattr(provider, method)
                    result = func(**kwargs)
                    if result is not None:
                        return result
                except ProviderError as e:
                    logger.warning(f"Provider {provider_name} failed for {method}: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error from {provider_name}: {e}")
                    continue
        return None

    # ---- Watchlist methods (delegated to user store) ----

    def create_watchlist(self, name: str):
        return self.user_store.create_watchlist(name)

    def get_watchlists(self):
        return self.user_store.get_watchlists()

    def delete_watchlist(self, watchlist_id: int):
        return self.user_store.delete_watchlist(watchlist_id)

    def add_to_watchlist(self, watchlist_id: int, ticker: str, notes: Optional[str] = None):
        return self.user_store.add_to_watchlist(watchlist_id, ticker, notes)

    def remove_from_watchlist(self, watchlist_id: int, ticker: str):
        return self.user_store.remove_from_watchlist(watchlist_id, ticker)

    def get_watchlist_items(self, watchlist_id: int):
        return self.user_store.get_watchlist_items(watchlist_id)

    def get_all_companies(self):
        return self.user_store.get_all_companies()


_data_manager: Optional[DataManager] = None


def get_data_manager() -> DataManager:
    """Get the global data manager instance."""
    global _data_manager
    if _data_manager is None:
        from investment_tool.config.settings import get_config
        config = get_config()
        _data_manager = DataManager(config)
    return _data_manager


def set_data_manager(manager: DataManager) -> None:
    """Set the global data manager instance."""
    global _data_manager
    _data_manager = manager

"""Data manager that orchestrates multiple data providers."""

from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

import pandas as pd
from loguru import logger

from investment_tool.config.settings import AppConfig
from investment_tool.data.cache import CacheManager
from investment_tool.data.models import CompanyInfo, NewsArticle
from investment_tool.data.providers.base import DataProviderBase, ProviderError
from investment_tool.data.providers.eodhd import EODHDProvider


class DataManager:
    """Orchestrates multiple data providers with caching and fallback."""

    def __init__(self, cache: CacheManager, config: AppConfig):
        self.cache = cache
        self.config = config
        self.providers: Dict[str, DataProviderBase] = {}
        self.provider_priority: List[str] = []
        self._setup_providers()

    @property
    def api_call_count(self) -> int:
        """Get total API calls across all providers."""
        total = 0
        for provider in self.providers.values():
            if hasattr(provider, 'api_call_count'):
                total += provider.api_call_count
        return total

    def _setup_providers(self) -> None:
        """Initialize configured data providers."""
        if self.config.api_keys.eodhd:
            self.providers["eodhd"] = EODHDProvider(
                self.config.api_keys.eodhd, self.cache
            )
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
        use_cache: bool = True,
    ) -> Optional[pd.DataFrame]:
        """
        Get daily prices with smart caching and provider fallback.

        1. Check cache for existing data
        2. Fetch only missing date ranges
        3. Try providers in priority order
        4. Cache new data
        """
        if use_cache:
            cached = self.cache.get_daily_prices(ticker, exchange, start, end)

            if cached is not None and len(cached) > 0:
                # Check if cache has reasonable coverage for the period
                # Only check for longer periods (> 30 days) to avoid slowing down point queries
                days_requested = (end - start).days

                if days_requested > 30:
                    # Expect ~252 trading days per year
                    expected_records = int(days_requested * 252 / 365 * 0.8)  # 80% coverage threshold

                    if len(cached) < expected_records:
                        # Cache has gaps, force full fetch and replace cache
                        logger.info(f"Cache has gaps for {ticker}.{exchange}: {len(cached)} records vs {expected_records} expected, fetching full range")
                    data = self._fetch_from_providers(
                        "get_daily_prices",
                        ticker=ticker,
                        exchange=exchange,
                        start=start,
                        end=end,
                    )
                    if data is not None and not data.empty:
                        self.cache.store_daily_prices(data, ticker, exchange)
                        if "date" in data.columns:
                            data = data.set_index("date")
                        return data
                    return cached  # Fall back to partial cache if fetch failed

                missing_ranges = self._find_missing_ranges(cached, start, end)

                if not missing_ranges:
                    logger.debug(f"Cache hit for {ticker}.{exchange}")
                    return cached

                for range_start, range_end in missing_ranges:
                    # Skip ranges that are only weekends
                    if range_start.weekday() >= 5 and range_end.weekday() >= 5:
                        logger.debug(f"Skipping weekend-only range {range_start} to {range_end}")
                        continue
                    logger.info(
                        f"Fetching missing range {range_start} to {range_end} "
                        f"for {ticker}.{exchange}"
                    )
                    new_data = self._fetch_from_providers(
                        "get_daily_prices",
                        ticker=ticker,
                        exchange=exchange,
                        start=range_start,
                        end=range_end,
                    )
                    if new_data is not None and not new_data.empty:
                        self.cache.store_daily_prices(new_data, ticker, exchange)
                        # Normalize new_data to have date as index before concat
                        if "date" in new_data.columns:
                            new_data = new_data.set_index("date")
                        cached = pd.concat([cached, new_data]).drop_duplicates()

                return cached.sort_index() if cached is not None else None

        data = self._fetch_from_providers(
            "get_daily_prices",
            ticker=ticker,
            exchange=exchange,
            start=start,
            end=end,
        )

        if data is not None and not data.empty:
            if use_cache:
                self.cache.store_daily_prices(data, ticker, exchange)
            # Normalize to have date as index for consistent return format
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
        """Get intraday prices with caching.

        Args:
            force_refresh: If True, skip reading from cache but still store new data.
        """
        if use_cache and not force_refresh:
            cached = self.cache.get_intraday_prices(ticker, start, end)
            if cached is not None and not cached.empty:
                return cached

        data = self._fetch_from_providers(
            "get_intraday_prices",
            ticker=ticker,
            exchange=exchange,
            interval=interval,
            start=start,
            end=end,
        )

        if data is not None and not data.empty and use_cache:
            self.cache.store_intraday_prices(data, ticker)

        return data

    def get_company_info(
        self,
        ticker: str,
        exchange: str,
        use_cache: bool = True,
    ) -> Optional[CompanyInfo]:
        """Get company information with caching."""
        if use_cache:
            cached = self.cache.get_company(ticker)
            if cached is not None:
                cache_age = datetime.now() - (cached.last_updated or datetime.min)
                if cache_age < timedelta(days=self.config.data.max_cache_age_days):
                    return cached

        company = self._fetch_from_providers(
            "get_company_info",
            ticker=ticker,
            exchange=exchange,
        )

        if company is not None and use_cache:
            self.cache.store_company(company)

        return company

    def get_news(
        self,
        ticker: str,
        limit: int = 50,
        use_cache: bool = True,
    ) -> List[NewsArticle]:
        """Get news articles with caching."""
        if use_cache:
            cached = self.cache.get_news(ticker=ticker, limit=limit)
            if cached:
                return cached

        articles = self._fetch_from_providers(
            "get_news",
            ticker=ticker,
            limit=limit,
        )

        if articles and use_cache:
            self.cache.store_news(articles)

        return articles or []

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

    def search_tickers(self, query: str) -> List[CompanyInfo]:
        """Search for tickers across providers."""
        results = self._fetch_from_providers("search_tickers", query=query)
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

    def refresh_company_data(
        self,
        ticker: str,
        exchange: str,
    ) -> bool:
        """Force refresh all data for a company."""
        try:
            company = self.get_company_info(ticker, exchange, use_cache=False)
            if company:
                self.cache.store_company(company)

            end = date.today()
            start = end - timedelta(days=365 * 2)
            prices = self.get_daily_prices(ticker, exchange, start, end, use_cache=False)
            if prices is not None and not prices.empty:
                self.cache.store_daily_prices(prices, ticker, exchange)

            news = self.get_news(ticker, use_cache=False)
            if news:
                self.cache.store_news(news)

            return True

        except ProviderError as e:
            logger.error(f"Failed to refresh data for {ticker}.{exchange}: {e}")
            return False

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

    def _find_missing_ranges(
        self,
        cached_df: pd.DataFrame,
        start: date,
        end: date,
    ) -> List[Tuple[date, date]]:
        """Find date ranges missing from cached data.

        Only fetches from edges (before cache start, after cache end).
        Gaps in the middle (holidays) are ignored to avoid unnecessary API calls.
        Skips weekends and today (data may not be available yet).
        """
        if cached_df is None or cached_df.empty:
            return [(start, end)]

        # Get the actual date range in cache
        cache_start = cached_df.index.min()
        cache_end = cached_df.index.max()

        # Convert to date if they're datetime/Timestamp
        if hasattr(cache_start, 'date'):
            cache_start = cache_start.date() if callable(cache_start.date) else cache_start
        if hasattr(cache_end, 'date'):
            cache_end = cache_end.date() if callable(cache_end.date) else cache_end

        # Don't fetch recent data (today or last few days) - it may not be available yet
        today = date.today()
        effective_end = min(end, today - timedelta(days=1))

        # Skip back to last weekday for effective_end
        while effective_end.weekday() >= 5:
            effective_end -= timedelta(days=1)

        # If requested range is fully covered by cache, nothing to fetch
        if start >= cache_start and effective_end <= cache_end:
            return []

        missing_ranges = []

        # Fetch data before cache start if needed
        if start < cache_start:
            missing_ranges.append((start, cache_start - timedelta(days=1)))

        # Fetch data after cache end if needed (skipping weekends)
        if effective_end > cache_end:
            fetch_start = cache_end + timedelta(days=1)
            # Skip weekends
            while fetch_start.weekday() >= 5:
                fetch_start += timedelta(days=1)

            if fetch_start <= effective_end:
                missing_ranges.append((fetch_start, effective_end))

        return missing_ranges

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "size_bytes": self.cache.get_cache_size(),
            "size_mb": round(self.cache.get_cache_size() / (1024 * 1024), 2),
            "companies": len(self.cache.get_all_companies()),
        }


_data_manager: Optional[DataManager] = None


def get_data_manager() -> DataManager:
    """Get the global data manager instance."""
    global _data_manager
    if _data_manager is None:
        from investment_tool.config.settings import get_config

        config = get_config()
        cache = CacheManager(config.data.database_path)
        _data_manager = DataManager(cache, config)
    return _data_manager


def set_data_manager(manager: DataManager) -> None:
    """Set the global data manager instance."""
    global _data_manager
    _data_manager = manager

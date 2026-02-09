"""SEC EDGAR client for fetching shares outstanding data from SEC filings."""

import asyncio
import logging
import time
from datetime import datetime, date
from typing import Optional

import httpx

from data_server.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory CIK mapping cache
_cik_cache: dict[str, str] = {}
_cik_cache_updated: float = 0
_CIK_CACHE_TTL = 86400  # 24 hours


class SECEdgarClient:
    """Client for SEC EDGAR Company Facts API."""

    def __init__(self):
        self._last_request_time: float = 0
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": settings.sec_edgar_user_agent},
                timeout=30.0,
            )
        return self._client

    async def _rate_limit(self) -> None:
        """Enforce SEC EDGAR rate limit (10 req/sec)."""
        elapsed = time.monotonic() - self._last_request_time
        delay = settings.sec_edgar_rate_limit - elapsed
        if delay > 0:
            await asyncio.sleep(delay)
        self._last_request_time = time.monotonic()

    async def _refresh_cik_cache(self) -> None:
        """Fetch ticker->CIK mapping from SEC."""
        global _cik_cache, _cik_cache_updated

        now = time.monotonic()
        if _cik_cache and (now - _cik_cache_updated) < _CIK_CACHE_TTL:
            return

        await self._rate_limit()
        client = await self._get_client()

        try:
            resp = await client.get("https://www.sec.gov/files/company_tickers.json")
            resp.raise_for_status()
            data = resp.json()

            new_cache: dict[str, str] = {}
            for entry in data.values():
                ticker = entry.get("ticker", "").upper()
                cik = str(entry.get("cik_str", ""))
                if ticker and cik:
                    new_cache[ticker] = cik

            _cik_cache = new_cache
            _cik_cache_updated = now
            logger.info(f"SEC EDGAR CIK cache refreshed: {len(_cik_cache)} tickers")

        except Exception as e:
            logger.error(f"Failed to refresh SEC CIK cache: {e}")
            if not _cik_cache:
                raise

    async def get_cik(self, ticker: str) -> Optional[str]:
        """Get CIK number for a ticker."""
        await self._refresh_cik_cache()
        return _cik_cache.get(ticker.upper())

    async def get_shares_history(self, ticker: str) -> list[dict]:
        """Fetch all historical shares outstanding data from SEC EDGAR.

        Returns list of dicts with keys:
            shares_outstanding, report_date, filing_type, filed_date,
            fiscal_year, fiscal_period
        """
        cik = await self.get_cik(ticker)
        if not cik:
            logger.debug(f"No CIK found for {ticker}")
            return []

        cik_padded = cik.zfill(10)
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"

        await self._rate_limit()
        client = await self._get_client()

        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug(f"No SEC EDGAR data for {ticker} (CIK {cik})")
                return []
            logger.error(f"SEC EDGAR HTTP error for {ticker}: {e}")
            return []
        except Exception as e:
            logger.error(f"SEC EDGAR request failed for {ticker}: {e}")
            return []

        # Parse shares outstanding from company facts
        # Primary: dei:EntityCommonStockSharesOutstanding (most companies)
        # Fallback: us-gaap:CommonStockSharesOutstanding (multi-class stocks like GOOG)
        shares_data = (
            data.get("facts", {})
            .get("dei", {})
            .get("EntityCommonStockSharesOutstanding", {})
            .get("units", {})
            .get("shares", [])
        )

        if not shares_data:
            shares_data = (
                data.get("facts", {})
                .get("us-gaap", {})
                .get("CommonStockSharesOutstanding", {})
                .get("units", {})
                .get("shares", [])
            )
            if shares_data:
                logger.info(f"Using us-gaap:CommonStockSharesOutstanding for {ticker}")

        # Fallback 2: WeightedAverageNumberOfSharesOutstandingBasic
        # Some companies (e.g., META) don't report point-in-time shares at all
        if not shares_data:
            shares_data = (
                data.get("facts", {})
                .get("us-gaap", {})
                .get("WeightedAverageNumberOfSharesOutstandingBasic", {})
                .get("units", {})
                .get("shares", [])
            )
            if shares_data:
                logger.info(f"Using us-gaap:WeightedAverageNumberOfSharesOutstandingBasic for {ticker}")

        if not shares_data:
            logger.debug(f"No shares outstanding data in SEC EDGAR for {ticker}")
            return []

        # Check if this is a foreign private issuer (files 20-F instead of 10-K).
        # Foreign issuers report ordinary shares, but US-listed price is the ADR price.
        # Mixing ordinary shares × ADR price gives wildly wrong market caps.
        # Skip SEC EDGAR for these — yfinance handles ADR conversion correctly.
        foreign_forms = {"20-F", "20-F/A"}
        filing_forms = {e.get("form", "") for e in shares_data}
        if filing_forms and filing_forms.issubset(foreign_forms):
            logger.info(f"Skipping SEC EDGAR for {ticker}: foreign issuer (20-F), ADR shares need conversion")
            return []

        results = []
        seen = set()
        for entry in shares_data:
            val = entry.get("val")
            end_date = entry.get("end")
            if not val or not end_date:
                continue

            # Deduplicate by (end_date, form) — SEC can have multiple filings for same period
            form = entry.get("form", "")
            dedup_key = (end_date, form)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            try:
                report_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                continue

            filed_date = None
            if entry.get("filed"):
                try:
                    filed_date = datetime.strptime(entry["filed"], "%Y-%m-%d").date()
                except ValueError:
                    pass

            results.append({
                "shares_outstanding": int(val),
                "report_date": report_date,
                "source": "sec_edgar",
                "filing_type": form if form else None,
                "filed_date": filed_date,
                "fiscal_year": entry.get("fy"),
                "fiscal_period": entry.get("fp"),
            })

        # Sort by report_date
        results.sort(key=lambda x: x["report_date"])
        logger.info(f"SEC EDGAR: {len(results)} shares data points for {ticker}")
        return results

    async def get_latest_shares(self, ticker: str) -> Optional[int]:
        """Get the most recent shares outstanding from SEC EDGAR."""
        history = await self.get_shares_history(ticker)
        if not history:
            return None
        return history[-1]["shares_outstanding"]

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Module-level singleton
_sec_client: Optional[SECEdgarClient] = None


async def get_sec_edgar_client() -> SECEdgarClient:
    """Get or create the SEC EDGAR client singleton."""
    global _sec_client
    if _sec_client is None:
        _sec_client = SECEdgarClient()
    return _sec_client

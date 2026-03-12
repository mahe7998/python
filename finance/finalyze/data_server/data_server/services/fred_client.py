"""FRED API client for fetching CPI (inflation) data."""

import logging
from typing import Optional

import httpx

from data_server.config import get_settings

logger = logging.getLogger(__name__)

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
CPI_SERIES_ID = "CPIAUCSL"  # Consumer Price Index for All Urban Consumers


async def get_cpi_series(
    start: str,
    end: str,
    series_id: str = CPI_SERIES_ID,
    api_key: Optional[str] = None,
) -> list[dict]:
    """Fetch CPI/price index observations from FRED API.

    Args:
        start: Start date (YYYY-MM-DD)
        end: End date (YYYY-MM-DD)
        series_id: FRED series (CPIAUCSL, CPILFESL, PCEPI)
        api_key: FRED API key (uses settings if not provided)

    Returns:
        List of {date, value} dicts with monthly observations.
    """
    key = api_key or get_settings().fred_api_key
    if not key:
        logger.warning("No FRED API key configured")
        return []

    params = {
        "series_id": series_id,
        "observation_start": start,
        "observation_end": end,
        "api_key": key,
        "file_type": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(FRED_BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        observations = data.get("observations", [])
        result = []
        for obs in observations:
            value = obs.get("value", ".")
            if value == ".":
                continue
            result.append({
                "date": obs["date"],
                "value": float(value),
            })

        logger.info(f"FRED CPI: fetched {len(result)} observations ({start} to {end})")
        return result

    except Exception as e:
        logger.error(f"FRED API error: {e}")
        return []

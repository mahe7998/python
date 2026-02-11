"""Simple JSON-based storage for user data (watchlists, settings).

All market data caching is handled by the data server.
This module only stores user-specific data locally.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from investment_tool.data.models import (
    Watchlist,
    WatchlistItem,
    CompanyInfo,
)


class UserDataStore:
    """Simple JSON storage for user data."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._watchlists_file = data_dir / "watchlists.json"
        self._companies_file = data_dir / "companies.json"
        self._load_data()

    def _load_data(self) -> None:
        """Load data from JSON files."""
        self._watchlists: Dict[int, Dict] = {}
        self._watchlist_items: Dict[int, List[Dict]] = {}
        self._companies: Dict[str, Dict] = {}

        if self._watchlists_file.exists():
            try:
                data = json.loads(self._watchlists_file.read_text())
                self._watchlists = {int(k): v for k, v in data.get("watchlists", {}).items()}
                self._watchlist_items = {int(k): v for k, v in data.get("items", {}).items()}
            except Exception:
                pass

        if self._companies_file.exists():
            try:
                self._companies = json.loads(self._companies_file.read_text())
            except Exception:
                pass

        # Migrate: backfill missing exchange in watchlist items from companies data
        migrated = False
        for wl_id, items in self._watchlist_items.items():
            for item in items:
                if "exchange" not in item:
                    company = self._companies.get(item["ticker"], {})
                    item["exchange"] = company.get("exchange", "US")
                    migrated = True
        if migrated:
            self._save_watchlists()

    def _save_watchlists(self) -> None:
        """Save watchlists to JSON file."""
        data = {
            "watchlists": self._watchlists,
            "items": self._watchlist_items,
        }
        self._watchlists_file.write_text(json.dumps(data, indent=2, default=str))

    def _save_companies(self) -> None:
        """Save companies to JSON file."""
        self._companies_file.write_text(json.dumps(self._companies, indent=2, default=str))

    # ---- Watchlist Methods ----

    def create_watchlist(self, name: str) -> Watchlist:
        """Create a new watchlist."""
        watchlist_id = max(self._watchlists.keys(), default=0) + 1
        now = datetime.now()
        self._watchlists[watchlist_id] = {
            "id": watchlist_id,
            "name": name,
            "created_at": now.isoformat(),
        }
        self._watchlist_items[watchlist_id] = []
        self._save_watchlists()
        return Watchlist(id=watchlist_id, name=name, created_at=now)

    def get_watchlists(self) -> List[Watchlist]:
        """Get all watchlists."""
        return [
            Watchlist(
                id=w["id"],
                name=w["name"],
                created_at=datetime.fromisoformat(w["created_at"]) if isinstance(w["created_at"], str) else w["created_at"],
            )
            for w in self._watchlists.values()
        ]

    def delete_watchlist(self, watchlist_id: int) -> None:
        """Delete a watchlist and its items."""
        self._watchlists.pop(watchlist_id, None)
        self._watchlist_items.pop(watchlist_id, None)
        self._save_watchlists()

    def add_to_watchlist(
        self, watchlist_id: int, ticker: str, exchange: str = "US", notes: Optional[str] = None
    ) -> None:
        """Add a stock to a watchlist."""
        if watchlist_id not in self._watchlist_items:
            self._watchlist_items[watchlist_id] = []

        # Remove if exists, then add
        self._watchlist_items[watchlist_id] = [
            item for item in self._watchlist_items[watchlist_id]
            if item["ticker"] != ticker
        ]
        self._watchlist_items[watchlist_id].append({
            "ticker": ticker,
            "exchange": exchange,
            "added_at": datetime.now().isoformat(),
            "notes": notes,
        })
        self._save_watchlists()

    def remove_from_watchlist(self, watchlist_id: int, ticker: str) -> None:
        """Remove a stock from a watchlist."""
        if watchlist_id in self._watchlist_items:
            self._watchlist_items[watchlist_id] = [
                item for item in self._watchlist_items[watchlist_id]
                if item["ticker"] != ticker
            ]
            self._save_watchlists()

    def get_watchlist_items(self, watchlist_id: int) -> List[WatchlistItem]:
        """Get all items in a watchlist."""
        items = self._watchlist_items.get(watchlist_id, [])
        return [
            WatchlistItem(
                watchlist_id=watchlist_id,
                ticker=item["ticker"],
                exchange=item.get("exchange", "US"),
                added_at=datetime.fromisoformat(item["added_at"]) if isinstance(item["added_at"], str) else item["added_at"],
                notes=item.get("notes"),
            )
            for item in items
        ]

    # ---- Company Cache (simple local cache for UI) ----

    def store_company(self, company: CompanyInfo) -> None:
        """Store company information locally for quick UI access."""
        self._companies[company.ticker] = {
            "ticker": company.ticker,
            "name": company.name,
            "exchange": company.exchange,
            "sector": company.sector,
            "industry": company.industry,
            "market_cap": company.market_cap,
            "country": company.country,
            "currency": company.currency,
            "pe_ratio": company.pe_ratio,
            "eps": company.eps,
            "last_updated": datetime.now().isoformat(),
        }
        self._save_companies()

    def get_company(self, ticker: str) -> Optional[CompanyInfo]:
        """Get company information from local cache."""
        data = self._companies.get(ticker)
        if not data:
            return None
        return CompanyInfo(
            ticker=data["ticker"],
            name=data["name"],
            exchange=data["exchange"],
            sector=data.get("sector"),
            industry=data.get("industry"),
            market_cap=data.get("market_cap"),
            country=data.get("country"),
            currency=data.get("currency"),
            pe_ratio=data.get("pe_ratio"),
            eps=data.get("eps"),
            last_updated=datetime.fromisoformat(data["last_updated"]) if data.get("last_updated") else None,
        )

    def get_all_companies(self) -> List[CompanyInfo]:
        """Get all companies from local cache."""
        return [
            CompanyInfo(
                ticker=data["ticker"],
                name=data["name"],
                exchange=data["exchange"],
                sector=data.get("sector"),
                industry=data.get("industry"),
                market_cap=data.get("market_cap"),
                country=data.get("country"),
                currency=data.get("currency"),
                pe_ratio=data.get("pe_ratio"),
                eps=data.get("eps"),
            )
            for data in self._companies.values()
        ]

"""Stock categories management."""

import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field

RESOURCES_DIR = Path(__file__).parent.parent / "resources"
DEFAULT_CATEGORIES_FILE = RESOURCES_DIR / "default_categories.json"


@dataclass
class StockReference:
    """Reference to a stock within a category."""
    ticker: str
    exchange: str

    def to_dict(self) -> Dict[str, str]:
        return {"ticker": self.ticker, "exchange": self.exchange}

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "StockReference":
        return cls(ticker=data["ticker"], exchange=data["exchange"])


@dataclass
class Category:
    """A category of stocks."""
    id: int
    name: str
    color: str
    stocks: List[StockReference] = field(default_factory=list)
    description: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "stocks": [s.to_dict() for s in self.stocks],
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Category":
        return cls(
            id=data["id"],
            name=data["name"],
            color=data["color"],
            stocks=[StockReference.from_dict(s) for s in data.get("stocks", [])],
            description=data.get("description"),
        )


class CategoryManager:
    """Manages stock categories."""

    def __init__(self):
        self._categories: Dict[int, Category] = {}
        self._next_id: int = 1

    def load_default_categories(self) -> None:
        """Load default categories from JSON file."""
        if DEFAULT_CATEGORIES_FILE.exists():
            self.load_from_file(DEFAULT_CATEGORIES_FILE)

    def load_from_file(self, path: Path) -> None:
        """Load categories from a JSON file."""
        with open(path, "r") as f:
            data = json.load(f)

        for cat_data in data.get("categories", []):
            category = Category.from_dict(cat_data)
            self._categories[category.id] = category
            if category.id >= self._next_id:
                self._next_id = category.id + 1

    def save_to_file(self, path: Path) -> None:
        """Save categories to a JSON file."""
        data = {
            "categories": [cat.to_dict() for cat in self._categories.values()]
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def get_category(self, category_id: int) -> Optional[Category]:
        """Get a category by ID."""
        return self._categories.get(category_id)

    def get_all_categories(self) -> List[Category]:
        """Get all categories."""
        return list(self._categories.values())

    def get_category_by_name(self, name: str) -> Optional[Category]:
        """Get a category by name."""
        for category in self._categories.values():
            if category.name.lower() == name.lower():
                return category
        return None

    def add_category(
        self,
        name: str,
        color: str,
        stocks: Optional[List[StockReference]] = None,
        description: Optional[str] = None,
    ) -> Category:
        """Add a new category."""
        category = Category(
            id=self._next_id,
            name=name,
            color=color,
            stocks=stocks or [],
            description=description,
        )
        self._categories[category.id] = category
        self._next_id += 1
        return category

    def update_category(self, category: Category) -> None:
        """Update an existing category."""
        if category.id in self._categories:
            self._categories[category.id] = category

    def delete_category(self, category_id: int) -> bool:
        """Delete a category by ID."""
        if category_id in self._categories:
            del self._categories[category_id]
            return True
        return False

    def add_stock_to_category(
        self, category_id: int, ticker: str, exchange: str
    ) -> bool:
        """Add a stock to a category."""
        category = self._categories.get(category_id)
        if category is None:
            return False

        stock_ref = StockReference(ticker=ticker, exchange=exchange)
        if stock_ref not in category.stocks:
            category.stocks.append(stock_ref)
            return True
        return False

    def remove_stock_from_category(
        self, category_id: int, ticker: str, exchange: str
    ) -> bool:
        """Remove a stock from a category."""
        category = self._categories.get(category_id)
        if category is None:
            return False

        stock_ref = StockReference(ticker=ticker, exchange=exchange)
        if stock_ref in category.stocks:
            category.stocks.remove(stock_ref)
            return True
        return False

    def get_stocks_in_category(self, category_id: int) -> List[StockReference]:
        """Get all stocks in a category."""
        category = self._categories.get(category_id)
        return category.stocks if category else []

    def get_categories_for_stock(
        self, ticker: str, exchange: str
    ) -> List[Category]:
        """Get all categories that contain a stock."""
        stock_ref = StockReference(ticker=ticker, exchange=exchange)
        return [
            cat for cat in self._categories.values() if stock_ref in cat.stocks
        ]


_category_manager: Optional[CategoryManager] = None

USER_CATEGORIES_FILE = Path.home() / ".investment_tool" / "categories.json"


def get_category_manager() -> CategoryManager:
    """Get the global category manager instance."""
    global _category_manager
    if _category_manager is None:
        _category_manager = CategoryManager()
        # If user categories file doesn't exist, copy defaults to user file
        if not USER_CATEGORIES_FILE.exists() and DEFAULT_CATEGORIES_FILE.exists():
            import shutil
            USER_CATEGORIES_FILE.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(DEFAULT_CATEGORIES_FILE, USER_CATEGORIES_FILE)
        # Load from user categories file
        if USER_CATEGORIES_FILE.exists():
            _category_manager.load_from_file(USER_CATEGORIES_FILE)
        else:
            _category_manager.load_default_categories()
    return _category_manager

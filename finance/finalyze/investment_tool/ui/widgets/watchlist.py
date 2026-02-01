"""Watchlist widget for managing stock watchlists."""

from typing import Optional, List, Dict, Any
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QModelIndex, QSortFilterProxyModel
from PySide6.QtGui import QColor, QBrush, QAction
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTableView,
    QPushButton,
    QMenu,
    QInputDialog,
    QMessageBox,
    QHeaderView,
    QAbstractItemView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QLabel,
)
from PySide6.QtCore import QAbstractTableModel

from investment_tool.data.cache import CacheManager
from investment_tool.data.models import Watchlist, WatchlistItem
from investment_tool.utils.helpers import format_percent, format_large_number


class WatchlistTableModel(QAbstractTableModel):
    """Table model for watchlist data."""

    COLUMNS = ["Ticker", "Price", "Change", "Change %", "Volume", "Market Cap"]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._data: List[Dict[str, Any]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.COLUMNS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ) -> Any:
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._data):
            return None

        row_data = self._data[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:  # Ticker
                return row_data.get("ticker", "")
            elif col == 1:  # Price
                price = row_data.get("price")
                return f"${price:.2f}" if price else "--"
            elif col == 2:  # Change
                change = row_data.get("change")
                if change is not None:
                    sign = "+" if change >= 0 else ""
                    return f"{sign}{change:.2f}"
                return "--"
            elif col == 3:  # Change %
                change_pct = row_data.get("change_percent")
                if change_pct is not None:
                    return format_percent(change_pct)
                return "--"
            elif col == 4:  # Volume
                volume = row_data.get("volume")
                return format_large_number(volume) if volume else "--"
            elif col == 5:  # Market Cap
                mcap = row_data.get("market_cap")
                return format_large_number(mcap) if mcap else "--"

        elif role == Qt.ForegroundRole:
            if col in [2, 3]:  # Change columns
                change = row_data.get("change_percent", 0)
                if change > 0:
                    return QBrush(QColor("#22C55E"))
                elif change < 0:
                    return QBrush(QColor("#EF4444"))

        elif role == Qt.TextAlignmentRole:
            if col > 0:  # Right-align numeric columns
                return Qt.AlignRight | Qt.AlignVCenter

        elif role == Qt.UserRole:
            # Return full row data
            return row_data

        return None

    def set_data(self, data: List[Dict[str, Any]]) -> None:
        """Set the table data."""
        self.beginResetModel()
        self._data = data
        self.endResetModel()

    def get_ticker_at(self, row: int) -> Optional[str]:
        """Get ticker at row index."""
        if 0 <= row < len(self._data):
            return self._data[row].get("ticker")
        return None

    def remove_row(self, row: int) -> None:
        """Remove a row from the model."""
        if 0 <= row < len(self._data):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._data[row]
            self.endRemoveRows()


class SparklineDelegate(QStyledItemDelegate):
    """Delegate for rendering sparkline in table cells."""

    def paint(self, painter, option, index) -> None:
        # For now, just use default painting
        # Sparklines will be added in a future iteration
        super().paint(painter, option, index)


class WatchlistWidget(QWidget):
    """Widget for managing stock watchlists."""

    stock_selected = Signal(str, str)  # ticker, exchange
    stock_double_clicked = Signal(str, str)

    def __init__(
        self,
        cache: Optional[CacheManager] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.cache = cache
        self._watchlists: Dict[int, Watchlist] = {}
        self._current_watchlist_id: Optional[int] = None

        self._setup_ui()
        self._load_watchlists()

    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toolbar
        toolbar = QHBoxLayout()

        self.add_list_btn = QPushButton("+ New List")
        self.add_list_btn.clicked.connect(self._on_create_watchlist)
        toolbar.addWidget(self.add_list_btn)

        self.add_stock_btn = QPushButton("+ Add Stock")
        self.add_stock_btn.clicked.connect(self._on_add_stock)
        toolbar.addWidget(self.add_stock_btn)

        toolbar.addStretch()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_current)
        toolbar.addWidget(self.refresh_btn)

        layout.addLayout(toolbar)

        # Tab widget for multiple watchlists
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._on_close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_widget.customContextMenuRequested.connect(self._on_tab_context_menu)
        layout.addWidget(self.tab_widget)

    def set_cache(self, cache: CacheManager) -> None:
        """Set the cache manager."""
        self.cache = cache
        self._load_watchlists()

    def _load_watchlists(self) -> None:
        """Load watchlists from database."""
        if not self.cache:
            return

        watchlists = self.cache.get_watchlists()

        # Clear existing tabs
        self.tab_widget.clear()
        self._watchlists.clear()

        if not watchlists:
            # Create default watchlist
            default = self.cache.create_watchlist("My Watchlist")
            watchlists = [default]

        for wl in watchlists:
            self._watchlists[wl.id] = wl
            self._create_watchlist_tab(wl)

        if watchlists:
            self._current_watchlist_id = watchlists[0].id

    def _create_watchlist_tab(self, watchlist: Watchlist) -> QWidget:
        """Create a tab for a watchlist."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        # Table view
        table = QTableView()
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos, t=table: self._on_table_context_menu(t, pos)
        )
        table.doubleClicked.connect(
            lambda idx, t=table: self._on_row_double_clicked(t, idx)
        )
        table.clicked.connect(
            lambda idx, t=table: self._on_row_clicked(t, idx)
        )

        # Configure header
        header = table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)

        # Set model
        model = WatchlistTableModel()
        proxy = QSortFilterProxyModel()
        proxy.setSourceModel(model)
        table.setModel(proxy)

        # Store reference
        table.setProperty("watchlist_id", watchlist.id)
        table.setProperty("model", model)

        layout.addWidget(table)

        self.tab_widget.addTab(tab, watchlist.name)

        # Load items for this watchlist
        self._refresh_watchlist(watchlist.id, table)

        return tab

    def _refresh_watchlist(
        self, watchlist_id: int, table: Optional[QTableView] = None
    ) -> None:
        """Refresh data for a watchlist."""
        if not self.cache:
            return

        if table is None:
            table = self._get_table_for_watchlist(watchlist_id)
            if table is None:
                return

        items = self.cache.get_watchlist_items(watchlist_id)

        # Build data with placeholder values
        # In a real implementation, we'd fetch live prices
        data = []
        for item in items:
            data.append({
                "ticker": item.ticker,
                "exchange": "US",  # TODO: store exchange in watchlist items
                "price": None,
                "change": None,
                "change_percent": None,
                "volume": None,
                "market_cap": None,
                "notes": item.notes,
            })

        model = table.property("model")
        if model:
            model.set_data(data)

    def _get_table_for_watchlist(self, watchlist_id: int) -> Optional[QTableView]:
        """Get the table view for a watchlist."""
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            table = tab.findChild(QTableView)
            if table and table.property("watchlist_id") == watchlist_id:
                return table
        return None

    def _refresh_current(self) -> None:
        """Refresh the current watchlist."""
        if self._current_watchlist_id:
            self._refresh_watchlist(self._current_watchlist_id)

    def _on_create_watchlist(self) -> None:
        """Create a new watchlist."""
        name, ok = QInputDialog.getText(
            self, "New Watchlist", "Enter watchlist name:"
        )

        if ok and name and self.cache:
            watchlist = self.cache.create_watchlist(name.strip())
            self._watchlists[watchlist.id] = watchlist
            self._create_watchlist_tab(watchlist)
            self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)

    def _on_add_stock(self) -> None:
        """Add a stock to the current watchlist."""
        if not self._current_watchlist_id or not self.cache:
            return

        ticker, ok = QInputDialog.getText(
            self, "Add Stock", "Enter ticker symbol:"
        )

        if ok and ticker:
            ticker = ticker.strip().upper()
            self.cache.add_to_watchlist(self._current_watchlist_id, ticker)
            self._refresh_current()

    def add_stock(self, ticker: str, exchange: str = "US") -> None:
        """Add a stock to the current watchlist programmatically."""
        if not self._current_watchlist_id or not self.cache:
            return

        self.cache.add_to_watchlist(self._current_watchlist_id, ticker)
        self._refresh_current()

    def _on_close_tab(self, index: int) -> None:
        """Handle tab close request."""
        if self.tab_widget.count() <= 1:
            QMessageBox.warning(
                self, "Cannot Delete",
                "You must have at least one watchlist."
            )
            return

        tab = self.tab_widget.widget(index)
        table = tab.findChild(QTableView)
        watchlist_id = table.property("watchlist_id") if table else None

        result = QMessageBox.question(
            self, "Delete Watchlist",
            f"Are you sure you want to delete this watchlist?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if result == QMessageBox.Yes:
            if watchlist_id and self.cache:
                self.cache.delete_watchlist(watchlist_id)
                if watchlist_id in self._watchlists:
                    del self._watchlists[watchlist_id]

            self.tab_widget.removeTab(index)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab selection change."""
        if index < 0:
            self._current_watchlist_id = None
            return

        tab = self.tab_widget.widget(index)
        table = tab.findChild(QTableView)
        if table:
            self._current_watchlist_id = table.property("watchlist_id")

    def _on_tab_context_menu(self, pos) -> None:
        """Show context menu for tab."""
        index = self.tab_widget.tabBar().tabAt(pos)
        if index < 0:
            return

        menu = QMenu(self)

        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(lambda: self._rename_watchlist(index))

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._on_close_tab(index))

        menu.exec(self.tab_widget.tabBar().mapToGlobal(pos))

    def _rename_watchlist(self, index: int) -> None:
        """Rename a watchlist."""
        tab = self.tab_widget.widget(index)
        table = tab.findChild(QTableView)
        watchlist_id = table.property("watchlist_id") if table else None

        if not watchlist_id or watchlist_id not in self._watchlists:
            return

        current_name = self._watchlists[watchlist_id].name

        name, ok = QInputDialog.getText(
            self, "Rename Watchlist",
            "Enter new name:",
            text=current_name
        )

        if ok and name and self.cache:
            # Update in database (would need to add this method)
            self._watchlists[watchlist_id].name = name.strip()
            self.tab_widget.setTabText(index, name.strip())

    def _on_table_context_menu(self, table: QTableView, pos) -> None:
        """Show context menu for table row."""
        index = table.indexAt(pos)
        if not index.isValid():
            return

        model = table.property("model")
        if not model:
            return

        # Get source index if using proxy model
        proxy = table.model()
        if isinstance(proxy, QSortFilterProxyModel):
            source_index = proxy.mapToSource(index)
            row = source_index.row()
        else:
            row = index.row()

        ticker = model.get_ticker_at(row)
        if not ticker:
            return

        menu = QMenu(self)

        view_action = menu.addAction(f"View {ticker}")
        view_action.triggered.connect(
            lambda: self.stock_selected.emit(ticker, "US")
        )

        chart_action = menu.addAction("Open Chart")
        chart_action.triggered.connect(
            lambda: self.stock_double_clicked.emit(ticker, "US")
        )

        menu.addSeparator()

        remove_action = menu.addAction("Remove from Watchlist")
        remove_action.triggered.connect(
            lambda: self._remove_stock(table, row, ticker)
        )

        menu.exec(table.viewport().mapToGlobal(pos))

    def _remove_stock(self, table: QTableView, row: int, ticker: str) -> None:
        """Remove a stock from the watchlist."""
        watchlist_id = table.property("watchlist_id")
        if not watchlist_id or not self.cache:
            return

        self.cache.remove_from_watchlist(watchlist_id, ticker)

        model = table.property("model")
        if model:
            model.remove_row(row)

    def _on_row_clicked(self, table: QTableView, index: QModelIndex) -> None:
        """Handle row click."""
        model = table.property("model")
        if not model:
            return

        proxy = table.model()
        if isinstance(proxy, QSortFilterProxyModel):
            source_index = proxy.mapToSource(index)
            row = source_index.row()
        else:
            row = index.row()

        ticker = model.get_ticker_at(row)
        if ticker:
            self.stock_selected.emit(ticker, "US")

    def _on_row_double_clicked(self, table: QTableView, index: QModelIndex) -> None:
        """Handle row double-click."""
        model = table.property("model")
        if not model:
            return

        proxy = table.model()
        if isinstance(proxy, QSortFilterProxyModel):
            source_index = proxy.mapToSource(index)
            row = source_index.row()
        else:
            row = index.row()

        ticker = model.get_ticker_at(row)
        if ticker:
            self.stock_double_clicked.emit(ticker, "US")

    def update_stock_data(self, data: List[Dict[str, Any]]) -> None:
        """Update stock data for all watchlists."""
        # Create lookup by ticker
        lookup = {d["ticker"]: d for d in data}

        # Update each watchlist
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            table = tab.findChild(QTableView)
            if not table:
                continue

            model = table.property("model")
            if not model:
                continue

            # Update model data
            current_data = model._data
            for item in current_data:
                ticker = item.get("ticker")
                if ticker in lookup:
                    item.update(lookup[ticker])

            model.set_data(current_data)

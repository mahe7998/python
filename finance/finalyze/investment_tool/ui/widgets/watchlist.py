"""Watchlist widget for managing stock watchlists."""

from typing import Optional, List, Dict, Any
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QModelIndex, QSortFilterProxyModel
from PySide6.QtGui import QColor, QBrush, QAction, QFont
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

from investment_tool.ui.dialogs.add_stock_dialog import AddStockDialog

from investment_tool.data.cache import CacheManager
from investment_tool.data.models import Watchlist, WatchlistItem
from investment_tool.utils.helpers import format_percent, format_large_number, is_intraday_period, get_date_range, get_last_trading_day_hours


class WatchlistTableModel(QAbstractTableModel):
    """Table model for watchlist data."""

    COLUMNS = ["Ticker", "Open", "Price", "Change", "Change %", "P/E", "Volume"]

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
            elif col == 1:  # Open
                open_price = row_data.get("open")
                return f"${open_price:.2f}" if open_price else "--"
            elif col == 2:  # Price (current/close)
                price = row_data.get("price")
                return f"${price:.2f}" if price else "--"
            elif col == 3:  # Change
                change = row_data.get("change")
                if change is not None:
                    sign = "+" if change >= 0 else ""
                    return f"{sign}{change:.2f}"
                return "--"
            elif col == 4:  # Change %
                change_pct = row_data.get("change_percent")
                if change_pct is not None:
                    return format_percent(change_pct)
                return "--"
            elif col == 5:  # P/E
                pe = row_data.get("pe_ratio")
                return f"{pe:.2f}" if pe else "--"
            elif col == 6:  # Volume
                volume = row_data.get("volume")
                return format_large_number(volume) if volume else "--"

        elif role == Qt.ForegroundRole:
            if col in [3, 4]:  # Change columns
                change = row_data.get("change_percent")
                if change is not None:
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
        data_manager=None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.cache = cache
        self.data_manager = data_manager
        self._watchlists: Dict[int, Watchlist] = {}
        self._current_watchlist_id: Optional[int] = None
        self._current_period: str = "1D"  # Default period, synced with treemap

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

    def set_data_manager(self, data_manager) -> None:
        """Set the data manager for search functionality."""
        self.data_manager = data_manager

    def set_period(self, period: str) -> None:
        """Set the current period for data fetching."""
        self._current_period = period

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
        # Smaller font for compact display
        font = table.font()
        font.setPointSize(9)
        table.setFont(font)
        # Compact row height
        table.verticalHeader().setDefaultSectionSize(20)
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
        from loguru import logger
        from datetime import timezone

        if not self.cache:
            logger.warning("No cache available for watchlist refresh")
            return

        if table is None:
            table = self._get_table_for_watchlist(watchlist_id)
            if table is None:
                logger.warning(f"No table found for watchlist {watchlist_id}")
                return

        items = self.cache.get_watchlist_items(watchlist_id)
        logger.info(f"Watchlist {watchlist_id} has {len(items)} items, period={self._current_period}")

        # Build data - fetch real prices if data_manager available
        data = []
        for item in items:
            row = {
                "ticker": item.ticker,
                "exchange": "US",
                "open": None,
                "price": None,
                "change": None,
                "change_percent": None,
                "pe_ratio": None,
                "volume": None,
                "notes": item.notes,
            }

            # Fetch real data if data_manager is available
            if self.data_manager:
                try:
                    if is_intraday_period(self._current_period):
                        # For 1D: open=today's open, price=current, change=from prev day close
                        from datetime import date, timedelta

                        # Get intraday for current price, open, and volume
                        market_open, market_close = get_last_trading_day_hours("US")
                        now_utc = datetime.now(timezone.utc)

                        if market_open.date() == now_utc.date() and market_open <= now_utc <= market_close:
                            end_dt = now_utc
                        else:
                            end_dt = market_close

                        intraday = self.data_manager.get_intraday_prices(
                            item.ticker, "US", "5m", market_open, end_dt, use_cache=True
                        )
                        logger.info(f"Got intraday prices for {item.ticker}: {len(intraday) if intraday is not None else 'None'}")

                        # Get daily prices for previous day's close
                        start = date.today() - timedelta(days=10)
                        end = date.today()
                        daily_prices = self.data_manager.get_daily_prices(
                            item.ticker, "US", start, end
                        )

                        if intraday is not None and len(intraday) >= 1:
                            # Get today's open from first intraday bar
                            first_bar = intraday.iloc[0]
                            row["open"] = first_bar.get("open") or first_bar.get("Open")

                            # Get current price from last intraday bar
                            latest = intraday.iloc[-1]
                            row["price"] = latest.get("close") or latest.get("Close")
                            row["volume"] = intraday["volume"].sum() if "volume" in intraday.columns else None

                            # Get the trading day from intraday data
                            if hasattr(intraday.index, 'date'):
                                trading_day = intraday.index[0].date() if hasattr(intraday.index[0], 'date') else intraday.index[0]
                            else:
                                trading_day = market_open.date()

                            # Find previous day's close from daily data
                            if daily_prices is not None and len(daily_prices) >= 1:
                                # Filter to days before the trading day
                                for i in range(len(daily_prices) - 1, -1, -1):
                                    idx = daily_prices.index[i]
                                    day_date = idx.date() if hasattr(idx, 'date') else idx
                                    if day_date < trading_day:
                                        prev_close = daily_prices.iloc[i].get("close") or daily_prices.iloc[i].get("Close")
                                        row["change"] = row["price"] - prev_close
                                        row["change_percent"] = row["change"] / prev_close
                                        logger.info(f"{item.ticker}: prev_close={prev_close:.2f} ({day_date}), price={row['price']:.2f}, change={row['change_percent']*100:.2f}%")
                                        break
                        elif daily_prices is not None and len(daily_prices) >= 2:
                            # Fallback to daily data
                            latest = daily_prices.iloc[-1]
                            prev = daily_prices.iloc[-2]
                            row["open"] = latest.get("open") or latest.get("Open")
                            row["price"] = latest.get("close") or latest.get("Close")
                            row["volume"] = latest.get("volume") or latest.get("Volume")
                            prev_close = prev.get("close") or prev.get("Close")
                            if prev_close and row["price"]:
                                row["change"] = row["price"] - prev_close
                                row["change_percent"] = row["change"] / prev_close
                    else:
                        # For other periods, use daily data
                        start, end = get_date_range(self._current_period, min_trading_days=0)
                        prices = self.data_manager.get_daily_prices(
                            item.ticker, "US", start, end
                        )
                        logger.info(f"Got daily prices for {item.ticker}: {len(prices) if prices is not None else 'None'}")

                        if prices is not None and len(prices) >= 1:
                            latest = prices.iloc[-1]
                            first = prices.iloc[0]
                            row["open"] = first.get("open") or first.get("Open")  # Period start open
                            row["price"] = latest.get("close") or latest.get("Close")
                            row["volume"] = latest.get("volume") or latest.get("Volume")

                            # Change is from start of period to end
                            start_price = first.get("close") or first.get("Close")
                            if start_price and row["price"]:
                                row["change"] = row["price"] - start_price
                                row["change_percent"] = row["change"] / start_price

                    # Get P/E ratio from company info
                    company = self.data_manager.get_company_info(item.ticker, "US")
                    if company and company.pe_ratio:
                        row["pe_ratio"] = company.pe_ratio
                except Exception as e:
                    logger.error(f"Error fetching prices for {item.ticker}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            data.append(row)

        model = table.property("model")
        if model:
            model.set_data(data)

    def refresh_all(self) -> None:
        """Refresh all watchlists (called when period changes)."""
        from loguru import logger
        logger.info(f"Refreshing all watchlists: {list(self._watchlists.keys())}, data_manager={self.data_manager is not None}")
        for watchlist_id in self._watchlists.keys():
            self._refresh_watchlist(watchlist_id)

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

        dialog = AddStockDialog(data_manager=self.data_manager, parent=self)
        if dialog.exec():
            ticker, exchange, _, _ = dialog.get_result()
            if ticker:
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
        menu.setStyleSheet("QMenu { font-size: 11px; }")

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
        menu.setStyleSheet("QMenu { font-size: 11px; }")

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

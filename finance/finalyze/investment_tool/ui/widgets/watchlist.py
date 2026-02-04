"""Watchlist widget for managing stock watchlists."""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, date

from PySide6.QtCore import Qt, Signal, QModelIndex, QSortFilterProxyModel, QItemSelectionModel
from PySide6.QtGui import QColor, QBrush, QAction, QFont

# Custom role for sorting with raw numeric values
SortRole = Qt.UserRole + 1
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
from investment_tool.data.models import Watchlist, WatchlistItem
from investment_tool.utils.helpers import format_percent, format_large_number, is_intraday_period, get_date_range, get_last_trading_day_hours
from investment_tool.config.categories import get_category_manager


class WatchlistTableModel(QAbstractTableModel):
    """Table model for watchlist data."""

    COLUMNS = ["Ticker", "Prev Close", "Open", "Price", "Change", "Change %", "P/E", "Volume", "Mkt Cap"]

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
            elif col == 1:  # Prev Close
                prev_close = row_data.get("prev_close")
                return f"${prev_close:.2f}" if prev_close else "--"
            elif col == 2:  # Open
                open_price = row_data.get("open")
                return f"${open_price:.2f}" if open_price else "--"
            elif col == 3:  # Price (current/close)
                price = row_data.get("price")
                return f"${price:.2f}" if price else "--"
            elif col == 4:  # Change
                change = row_data.get("change")
                if change is not None:
                    sign = "+" if change >= 0 else ""
                    return f"{sign}{change:.2f}"
                return "--"
            elif col == 5:  # Change %
                change_pct = row_data.get("change_percent")
                if change_pct is not None:
                    return format_percent(change_pct)
                return "--"
            elif col == 6:  # P/E
                pe = row_data.get("pe_ratio")
                return f"{pe:.2f}" if pe else "--"
            elif col == 7:  # Volume
                volume = row_data.get("volume")
                return format_large_number(volume) if volume else "--"
            elif col == 8:  # Market Cap
                market_cap = row_data.get("market_cap")
                return format_large_number(market_cap, decimals=2) if market_cap else "--"

        elif role == Qt.ForegroundRole:
            if col in [4, 5]:  # Change columns
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

        elif role == SortRole:
            # Return raw numeric values for sorting
            if col == 0:  # Ticker
                return row_data.get("ticker", "")
            elif col == 1:  # Prev Close
                return row_data.get("prev_close") or 0
            elif col == 2:  # Open
                return row_data.get("open") or 0
            elif col == 3:  # Price
                return row_data.get("price") or 0
            elif col == 4:  # Change
                return row_data.get("change") or 0
            elif col == 5:  # Change %
                return row_data.get("change_percent") or 0
            elif col == 6:  # P/E
                return row_data.get("pe_ratio") or 0
            elif col == 7:  # Volume
                return row_data.get("volume") or 0
            elif col == 8:  # Market Cap
                return row_data.get("market_cap") or 0

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


class WatchlistSortProxyModel(QSortFilterProxyModel):
    """Custom sort proxy model that uses raw numeric values for sorting."""

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        """Compare two items using raw values from SortRole."""
        left_data = self.sourceModel().data(left, SortRole)
        right_data = self.sourceModel().data(right, SortRole)

        # Handle None values - sort them to the end
        if left_data is None and right_data is None:
            return False
        if left_data is None:
            return False  # None goes to end
        if right_data is None:
            return True  # Non-None comes before None

        # Compare values - use bool() to convert numpy.bool to Python bool
        try:
            # Try numeric comparison first
            if isinstance(left_data, (int, float)) or isinstance(right_data, (int, float)):
                return bool(float(left_data) < float(right_data))
            # Fall back to string comparison
            return bool(str(left_data) < str(right_data))
        except (TypeError, ValueError):
            return bool(str(left_data) < str(right_data))


class WatchlistWidget(QWidget):
    """Widget for managing stock watchlists."""

    stock_selected = Signal(str, str)  # ticker, exchange
    stock_double_clicked = Signal(str, str)
    stock_added = Signal(str, str)  # ticker, exchange - emitted when stock added to watchlist

    def __init__(
        self,
        data_manager=None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
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

    def set_data_manager(self, data_manager) -> None:
        """Set the data manager."""
        self.data_manager = data_manager
        self._load_watchlists()

    def set_period(self, period: str) -> None:
        """Set the current period for data fetching."""
        self._current_period = period

    def _load_watchlists(self) -> None:
        """Load watchlists from data manager."""
        if not self.data_manager:
            return

        watchlists = self.data_manager.get_watchlists()

        # Clear existing tabs
        self.tab_widget.clear()
        self._watchlists.clear()

        if not watchlists:
            # Create default watchlist
            default = self.data_manager.create_watchlist("My Watchlist")
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

        # Set model with custom sort proxy for numeric sorting
        model = WatchlistTableModel()
        proxy = WatchlistSortProxyModel()
        proxy.setSourceModel(model)
        table.setModel(proxy)

        # Connect selection model for keyboard navigation (must be after setModel)
        table.selectionModel().currentChanged.connect(
            lambda current, previous, t=table: self._on_selection_changed(t, current)
        )

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

        if not self.data_manager:
            logger.warning("No data manager available for watchlist refresh")
            return

        if table is None:
            table = self._get_table_for_watchlist(watchlist_id)
            if table is None:
                logger.warning(f"No table found for watchlist {watchlist_id}")
                return

        items = self.data_manager.get_watchlist_items(watchlist_id)
        logger.info(f"Watchlist {watchlist_id} has {len(items)} items, period={self._current_period}")

        # Build data - fetch real prices if data_manager available
        data = []
        for item in items:
            row = {
                "ticker": item.ticker,
                "exchange": "US",
                "prev_close": None,
                "open": None,
                "price": None,
                "change": None,
                "change_percent": None,
                "pe_ratio": None,
                "volume": None,
                "market_cap": None,
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

                        # Check if market is currently open
                        market_is_open = market_open.date() == now_utc.date() and market_open <= now_utc <= market_close
                        if market_is_open:
                            end_dt = now_utc
                        else:
                            end_dt = market_close

                        # Use cached data - data server handles caching efficiently
                        # No need for force_refresh when market is closed
                        # Use 1m interval - EODHD 5m data has gaps/NULLs for some stocks
                        intraday = self.data_manager.get_intraday_prices(
                            item.ticker, "US", "1m", market_open, end_dt,
                            use_cache=True, force_refresh=False
                        )
                        logger.info(f"Got intraday prices for {item.ticker}: {len(intraday) if intraday is not None else 'None'}")

                        # Get daily prices for previous day's close
                        start = date.today() - timedelta(days=10)
                        end = date.today()
                        daily_prices = self.data_manager.get_daily_prices(
                            item.ticker, "US", start, end
                        )

                        if intraday is not None and len(intraday) >= 1:
                            close_col = "close" if "close" in intraday.columns else "Close"

                            # Data is sorted ascending (oldest first), so iloc[-1] is the latest
                            valid_close_bars = intraday[intraday[close_col].notna()]
                            if len(valid_close_bars) > 0:
                                latest = valid_close_bars.iloc[-1]  # Last row is newest (market close)
                                row["price"] = latest[close_col]

                            # EODHD intraday volume is cumulative (running total), use last value
                            row["volume"] = intraday["volume"].iloc[-1] if "volume" in intraday.columns else None

                            # Get the trading day from intraday data (use timestamp column)
                            # Data is sorted ascending, so iloc[-1] is newest
                            if "timestamp" in intraday.columns:
                                ts_val = intraday["timestamp"].iloc[-1]
                                if hasattr(ts_val, 'date'):
                                    trading_day = ts_val.date()
                                elif isinstance(ts_val, str):
                                    # Parse ISO format string (remove timezone suffix if present)
                                    ts_clean = ts_val.replace('Z', '').split('+')[0]
                                    trading_day = datetime.fromisoformat(ts_clean).date()
                                else:
                                    trading_day = market_open.date()
                                logger.info(f"{item.ticker}: ts_val={ts_val}, trading_day={trading_day}")
                            elif hasattr(intraday.index, 'date'):
                                trading_day = intraday.index[-1].date() if hasattr(intraday.index[-1], 'date') else intraday.index[-1]
                            else:
                                trading_day = market_open.date()

                            # Get open and previous close from daily data (more reliable than intraday)
                            # Daily data may be sorted newest-first
                            if daily_prices is not None and len(daily_prices) >= 1:
                                # Find today's open and previous day's close
                                # Data is sorted ascending (oldest first), so iterate to find trading_day
                                prev_day_close = None
                                for i in range(len(daily_prices)):
                                    idx = daily_prices.index[i]
                                    # Handle both date objects and string dates
                                    if hasattr(idx, 'date') and not isinstance(idx, date):
                                        day_date = idx.date()
                                    elif isinstance(idx, str):
                                        day_date = datetime.strptime(idx, "%Y-%m-%d").date()
                                    else:
                                        day_date = idx

                                    logger.debug(f"{item.ticker}: loop i={i}, day_date={day_date}, trading_day={trading_day}, match={day_date == trading_day}")
                                    if day_date == trading_day:
                                        # Found trading day - get the open
                                        open_val = daily_prices.iloc[i].get("open") or daily_prices.iloc[i].get("Open")
                                        logger.info(f"{item.ticker}: FOUND trading_day at i={i}, open={open_val}, prev_day_close={prev_day_close}")
                                        row["open"] = open_val
                                        # Use prev_day_close from previous iteration
                                        if prev_day_close is not None:
                                            row["prev_close"] = prev_day_close
                                            if row["price"] is not None:
                                                row["change"] = row["price"] - prev_day_close
                                                row["change_percent"] = row["change"] / prev_day_close
                                        break
                                    else:
                                        # Remember this day's close as potential prev_close
                                        prev_day_close = daily_prices.iloc[i].get("close") or daily_prices.iloc[i].get("Close")

                            # Fallback to live prices if daily data is missing open/prev_close
                            if row["open"] is None or row["prev_close"] is None:
                                live = self.data_manager.get_live_price(item.ticker, "US")
                                logger.debug(f"Live price fallback for {item.ticker}: {live}")
                                if live:
                                    if row["open"] is None:
                                        row["open"] = live.get("open")
                                    if row["prev_close"] is None:
                                        # get_live_price returns "previous_close" (snake_case)
                                        row["prev_close"] = live.get("previous_close")
                                        if row["prev_close"] and row["price"]:
                                            row["change"] = row["price"] - row["prev_close"]
                                            row["change_percent"] = row["change"] / row["prev_close"]
                        elif daily_prices is not None and len(daily_prices) >= 2:
                            # Fallback to daily data
                            latest = daily_prices.iloc[-1]
                            prev = daily_prices.iloc[-2]
                            row["open"] = latest.get("open") or latest.get("Open")
                            row["price"] = latest.get("close") or latest.get("Close")
                            row["volume"] = latest.get("volume") or latest.get("Volume")
                            prev_close = prev.get("close") or prev.get("Close")
                            row["prev_close"] = prev_close
                            if prev_close and row["price"]:
                                row["change"] = row["price"] - prev_close
                                row["change_percent"] = row["change"] / prev_close

                        # Final fallback to live prices if still missing data
                        if row["price"] is None or row["open"] is None or row["prev_close"] is None:
                            live = self.data_manager.get_live_price(item.ticker, "US")
                            logger.debug(f"Final live price fallback for {item.ticker}: {live}")
                            if live:
                                if row["price"] is None:
                                    row["price"] = live.get("price")
                                if row["open"] is None:
                                    row["open"] = live.get("open")
                                if row["prev_close"] is None:
                                    row["prev_close"] = live.get("previous_close")
                                if row["volume"] is None:
                                    row["volume"] = live.get("volume")
                                # Recalculate change if we now have the data
                                if row["prev_close"] and row["price"] and row["change"] is None:
                                    row["change"] = row["price"] - row["prev_close"]
                                    row["change_percent"] = row["change"] / row["prev_close"]
                    else:
                        # For other periods (1W, 1M, etc.), use daily data
                        start, end = get_date_range(self._current_period, min_trading_days=0)
                        prices = self.data_manager.get_daily_prices(
                            item.ticker, "US", start, end
                        )
                        logger.info(f"Got daily prices for {item.ticker}: {len(prices) if prices is not None else 'None'}")

                        if prices is not None and len(prices) >= 1:
                            # Sort by date ascending to ensure correct first/last
                            prices_sorted = prices.sort_index(ascending=True)
                            first = prices_sorted.iloc[0]  # Oldest (period start)
                            latest = prices_sorted.iloc[-1]  # Newest (period end)

                            row["open"] = first.get("open") or first.get("Open")  # Period start open
                            row["volume"] = prices_sorted["volume"].sum() if "volume" in prices_sorted.columns else (prices_sorted["Volume"].sum() if "Volume" in prices_sorted.columns else None)

                            # Get today's live price for current value
                            live = self.data_manager.get_live_price(item.ticker, "US")
                            if live and live.get("price"):
                                row["price"] = live.get("price")
                            else:
                                # Fallback to latest close if live price unavailable
                                row["price"] = latest.get("close") or latest.get("Close")

                            # Change is from period's open to current price
                            period_open = row["open"]
                            if period_open and row["price"]:
                                row["change"] = row["price"] - period_open
                                row["change_percent"] = row["change"] / period_open

                    # Get P/E ratio and market cap from company info
                    company = self.data_manager.get_company_info(item.ticker, "US")
                    if company:
                        if company.pe_ratio:
                            row["pe_ratio"] = company.pe_ratio
                        if company.market_cap:
                            row["market_cap"] = company.market_cap
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

        if ok and name and self.data_manager:
            watchlist = self.data_manager.create_watchlist(name.strip())
            self._watchlists[watchlist.id] = watchlist
            self._create_watchlist_tab(watchlist)
            self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)

    def _on_add_stock(self) -> None:
        """Add a stock to the current watchlist."""
        if not self._current_watchlist_id or not self.data_manager:
            return

        dialog = AddStockDialog(data_manager=self.data_manager, parent=self, require_category=False)
        if dialog.exec():
            ticker, exchange, _, _ = dialog.get_result()
            if ticker:
                self.data_manager.add_to_watchlist(self._current_watchlist_id, ticker)
                # Also add to Uncategorized category so it appears in All Stocks
                self._add_to_uncategorized(ticker, exchange or "US")
                self._refresh_current()
                self.stock_added.emit(ticker, exchange or "US")

    def add_stock(self, ticker: str, exchange: str = "US") -> None:
        """Add a stock to the current watchlist programmatically."""
        if not self._current_watchlist_id or not self.data_manager:
            return

        self.data_manager.add_to_watchlist(self._current_watchlist_id, ticker)
        # Also add to Uncategorized category so it appears in All Stocks
        self._add_to_uncategorized(ticker, exchange)
        self._refresh_current()
        self.stock_added.emit(ticker, exchange)

    def select_stock(self, ticker: str, exchange: str = "US") -> bool:
        """Select a stock in the current watchlist by ticker.

        Returns True if the stock was found and selected, False otherwise.
        """
        table = self._get_table_for_watchlist(self._current_watchlist_id)
        if not table:
            return False

        model = table.property("model")
        if not model:
            return False

        # Find the row with this ticker
        for row in range(len(model._data)):
            if model._data[row].get("ticker") == ticker:
                # Get the proxy model to handle sorting
                proxy = table.model()
                if isinstance(proxy, QSortFilterProxyModel):
                    # Map source row to proxy row
                    source_index = model.index(row, 0)
                    proxy_index = proxy.mapFromSource(source_index)
                    if proxy_index.isValid():
                        # Select the row without emitting signal (to avoid loop)
                        table.selectionModel().blockSignals(True)
                        table.selectRow(proxy_index.row())
                        table.scrollTo(proxy_index)
                        table.selectionModel().blockSignals(False)
                        return True
                else:
                    table.selectionModel().blockSignals(True)
                    table.selectRow(row)
                    table.scrollTo(model.index(row, 0))
                    table.selectionModel().blockSignals(False)
                    return True

        return False

    def _add_to_uncategorized(self, ticker: str, exchange: str) -> None:
        """Add stock to Uncategorized category if not already in any category."""
        category_manager = get_category_manager()

        # Check if stock is already in any category
        existing_categories = category_manager.get_categories_for_stock(ticker, exchange)
        if existing_categories:
            return  # Already categorized

        # Find or create Uncategorized category
        uncategorized = category_manager.get_category_by_name("Uncategorized")
        if uncategorized is None:
            # Create Uncategorized category with gray color
            uncategorized = category_manager.add_category(
                name="Uncategorized",
                color="#808080",
                description="Stocks not assigned to any category"
            )

        # Add stock to Uncategorized
        category_manager.add_stock_to_category(uncategorized.id, ticker, exchange)

        # Save categories
        from investment_tool.config.categories import USER_CATEGORIES_FILE
        category_manager.save_to_file(USER_CATEGORIES_FILE)

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
            if watchlist_id and self.data_manager:
                self.data_manager.delete_watchlist(watchlist_id)
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

        if ok and name and self.data_manager:
            # Update in local state (would need to add this method to data manager)
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
        if not watchlist_id or not self.data_manager:
            return

        self.data_manager.remove_from_watchlist(watchlist_id, ticker)

        model = table.property("model")
        if model:
            model.remove_row(row)

    def _on_row_clicked(self, table: QTableView, index: QModelIndex) -> None:
        """Handle row click."""
        self._emit_selection(table, index)

    def _on_selection_changed(self, table: QTableView, current: QModelIndex) -> None:
        """Handle selection change (keyboard navigation)."""
        if current.isValid():
            self._emit_selection(table, current)

    def _emit_selection(self, table: QTableView, index: QModelIndex) -> None:
        """Emit stock_selected signal for the given index."""
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

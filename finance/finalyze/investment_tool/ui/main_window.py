"""Main application window."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict

from PySide6.QtCore import Qt, QTimer, QEventLoop, Signal, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTabWidget,
    QToolBar,
    QStatusBar,
    QLabel,
    QPushButton,
    QToolButton,
    QComboBox,
    QMenu,
    QProgressDialog,
    QMessageBox,
    QGroupBox,
    QFormLayout,
    QApplication,
)
from loguru import logger
import pandas as pd

from investment_tool.config.settings import get_config, AppConfig
from investment_tool.config.categories import get_category_manager
from investment_tool.data.manager import get_data_manager, DataManager
from investment_tool.ui.styles.theme import get_stylesheet
from investment_tool.ui.dialogs.settings_dialog import SettingsDialog
from investment_tool.ui.dialogs.category_dialog import CategoryDialog
from investment_tool.ui.dialogs.add_stock_dialog import AddStockDialog
from investment_tool.ui.widgets.etf_overview import ETFOverviewWidget
from investment_tool.ui.widgets.fundamentals_overview import FundamentalsOverviewWidget
from investment_tool.ui.widgets.market_treemap import MarketTreemap, TreemapItem
from investment_tool.ui.widgets.fx_converter import FXConverterWidget
from investment_tool.ui.widgets.news_feed import NewsFeedWidget
from investment_tool.ui.widgets.quarterly_financials import QuarterlyFinancialsWidget
from investment_tool.ui.widgets.sentiment_gauge import SentimentGaugeWidget
from investment_tool.ui.widgets.stock_chart import StockChart
from investment_tool.ui.widgets.advanced_chart import AdvancedChartWidget
from investment_tool.ui.control_server import ControlServer
from investment_tool.ui.widgets.watchlist import WatchlistWidget
from investment_tool.utils.helpers import (
    get_date_range,
    format_percent,
    format_large_number,
    is_intraday_period,
    get_last_trading_day_hours,
)
from investment_tool.utils.exchange_hours import (
    get_market_hours as _get_market_hours,
    get_utc_offset as _get_utc_offset,
    is_market_open,
    clear_lunch_break as _clear_lunch_break,
)


def _strip_phantom_today(prices):
    """Remove today's EOD entry if its OHLC duplicates a recent day (stale data).

    Data providers sometimes include today's entry using a stale live-price
    snapshot (e.g. pre-market) which duplicates a previous day's OHLC.
    Detect this by checking if today's close matches any of the last 5 real
    entries within float tolerance — real closes virtually never repeat exactly.
    """
    if prices is None or len(prices) < 2:
        return prices
    import pandas as pd
    today = date.today()
    last_idx = prices.index[-1]
    last_date = last_idx.date() if isinstance(last_idx, (datetime, pd.Timestamp)) else None
    if last_date is None:
        try:
            last_date = date.fromisoformat(str(last_idx)[:10])
        except (ValueError, TypeError):
            return prices
    if last_date != today:
        return prices
    # Today's entry exists — check if its close duplicates a recent entry
    last_close = prices["close"].iloc[-1]
    lookback = min(5, len(prices) - 1)
    for i in range(2, lookback + 2):
        prev_close = prices["close"].iloc[-i]
        if abs(last_close - prev_close) < 0.01:
            # Duplicate found — drop today's phantom entry
            return prices.iloc[:-1]
    return prices


class MainWindow(QMainWindow):
    """Main application window."""

    status_updated = Signal(str)
    db_update_progress = Signal(int, str)  # (index, symbol_name)

    def __init__(self, config: Optional[AppConfig] = None):
        super().__init__()

        self.config = config or get_config()
        self.data_manager: Optional[DataManager] = None
        self.category_manager = get_category_manager()

        # Current selection state
        self._selected_ticker: Optional[str] = None
        self._selected_exchange: Optional[str] = None
        self._chart_loading: bool = False  # Prevent concurrent chart loads
        self._selecting: bool = False  # Prevent circular selection
        self._db_update_progress: Optional[QProgressDialog] = None
        self._news_update_progress: Optional[QProgressDialog] = None
        self._financials_update_progress: Optional[QProgressDialog] = None

        self._setup_window()
        self._create_menu_bar()
        self._create_tool_bar()
        self._create_central_widget()
        self._create_status_bar()
        self._setup_timers()

        self._initialize_data()

        # Start embedded HTTP control server for external tool integration
        self._control_server = ControlServer(port=18765, parent=self)
        self._control_server.state_requested.connect(self._on_control_get_state)
        self._control_server.select_stock_requested.connect(self._on_control_select_stock)
        self._control_server.set_period_requested.connect(self._on_control_set_period)
        self._control_server.start()

    def _setup_window(self) -> None:
        """Configure main window properties."""
        self.setWindowTitle("Investment Tracking & Analysis Tool")
        self.setMinimumSize(1200, 800)
        self.resize(1600, 1000)

        self.setStyleSheet(get_stylesheet("dark"))

    def _create_menu_bar(self) -> None:
        """Create the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        refresh_action = QAction("&Refresh Data", self)
        refresh_action.setShortcut(QKeySequence.Refresh)
        refresh_action.triggered.connect(self._on_refresh)
        file_menu.addAction(refresh_action)

        update_db_action = QAction("&Update Database", self)
        update_db_action.triggered.connect(self._on_update_database)
        file_menu.addAction(update_db_action)

        update_news_action = QAction("Update &News", self)
        update_news_action.triggered.connect(self._on_update_news)
        file_menu.addAction(update_news_action)

        update_financials_action = QAction("Update &Financials", self)
        update_financials_action.triggered.connect(self._on_update_financials)
        file_menu.addAction(update_financials_action)

        file_menu.addSeparator()

        export_action = QAction("&Export Data...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._on_export)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Data menu
        data_menu = menubar.addMenu("&Data")

        add_stock = QAction("&Add Stock...", self)
        add_stock.setShortcut(QKeySequence("Ctrl+N"))
        add_stock.triggered.connect(self._on_add_stock)
        data_menu.addAction(add_stock)

        manage_categories = QAction("&Manage Categories...", self)
        manage_categories.triggered.connect(self._on_manage_categories)
        data_menu.addAction(manage_categories)

        data_menu.addSeparator()

        clear_cache = QAction("&Clear Cache...", self)
        clear_cache.triggered.connect(self._on_clear_cache)
        data_menu.addAction(clear_cache)

        # Analysis menu
        analysis_menu = menubar.addMenu("&Analysis")

        screener = QAction("&Stock Screener", self)
        screener.setShortcut(QKeySequence("Ctrl+F"))
        screener.triggered.connect(self._on_open_screener)
        analysis_menu.addAction(screener)

        compare = QAction("&Compare Stocks...", self)
        compare.triggered.connect(self._on_compare_stocks)
        analysis_menu.addAction(compare)

        # Backtest menu
        backtest_menu = menubar.addMenu("&Backtest")

        new_backtest = QAction("&New Backtest...", self)
        new_backtest.triggered.connect(self._on_new_backtest)
        backtest_menu.addAction(new_backtest)

        view_results = QAction("&View Results...", self)
        view_results.triggered.connect(self._on_view_backtest_results)
        backtest_menu.addAction(view_results)

        # Settings menu
        settings_menu = menubar.addMenu("&Settings")

        preferences = QAction("&Preferences...", self)
        preferences.setShortcut(QKeySequence.Preferences)
        preferences.triggered.connect(self._on_open_settings)
        settings_menu.addAction(preferences)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about = QAction("&About", self)
        about.triggered.connect(self._on_about)
        help_menu.addAction(about)

    def _create_tool_bar(self) -> None:
        """Create the tool bar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Advanced mode toggle
        self.advanced_btn = QPushButton("Advanced")
        self.advanced_btn.setCheckable(True)
        self.advanced_btn.setStyleSheet("""
            QPushButton {
                padding: 4px 12px;
            }
            QPushButton:checked {
                background-color: #3B82F6;
                color: white;
            }
        """)
        self.advanced_btn.toggled.connect(self._toggle_advanced_mode)
        toolbar.addWidget(self.advanced_btn)

        # Period selector (moved from treemap toolbar)
        self.period_combo = QComboBox()
        self.period_combo.addItems(["1D", "1W", "1M", "3M", "6M", "YTD", "1Y", "2Y", "5Y"])
        self.period_combo.setCurrentText("1D")
        self.period_combo.currentTextChanged.connect(self._on_period_changed)
        toolbar.addWidget(self.period_combo)

        toolbar.addSeparator()

        refresh_btn = QToolButton()
        refresh_btn.setText("Refresh")
        refresh_menu = QMenu(refresh_btn)
        refresh_menu.addAction("Refresh Screen", self._on_refresh)
        refresh_menu.addAction("Update Database", self._on_update_database)
        refresh_menu.addAction("Update News", self._on_update_news)
        refresh_menu.addAction("Update Financials", self._on_update_financials)
        refresh_btn.setMenu(refresh_menu)
        refresh_btn.setPopupMode(QToolButton.InstantPopup)
        toolbar.addWidget(refresh_btn)

        toolbar.addSeparator()

        add_stock_btn = QPushButton("Add Stock")
        add_stock_btn.clicked.connect(self._on_add_stock)
        toolbar.addWidget(add_stock_btn)

        categories_btn = QPushButton("Categories")
        categories_btn.clicked.connect(self._on_manage_categories)
        toolbar.addWidget(categories_btn)

        screener_btn = QPushButton("Screener")
        screener_btn.clicked.connect(self._on_open_screener)
        toolbar.addWidget(screener_btn)

        toolbar.addSeparator()

        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self._on_open_settings)
        toolbar.addWidget(settings_btn)

    def _create_central_widget(self) -> None:
        """Create the central widget layout."""
        central = QWidget()
        self.setCentralWidget(central)

        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(8)

        # Advanced chart widget (hidden by default, shown full-width in advanced mode)
        self.advanced_chart = AdvancedChartWidget()
        self.advanced_chart.hide()

        # Main content splitter
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_layout.addWidget(self.main_splitter, stretch=1)

        # Left panel - Market Treemap
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.treemap = MarketTreemap()
        self.treemap.stock_selected.connect(self._on_stock_selected)
        self.treemap.stock_double_clicked.connect(self._on_stock_double_clicked)
        self.treemap.filter_changed.connect(self._on_treemap_filter_changed)
        self.treemap.stock_remove_requested.connect(self._on_stock_remove_requested)
        self.treemap.stock_add_to_watchlist.connect(self._on_stock_add_to_watchlist)
        left_layout.addWidget(self.treemap)

        self.main_splitter.addWidget(left_panel)

        # Right panel - Chart and details
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget for Chart / Financials toggle
        self.chart_tabs = QTabWidget()
        self.chart_tabs.setDocumentMode(True)  # Cleaner tab appearance

        # Stock Chart tab
        self.stock_chart = StockChart()
        # Period is now controlled by treemap, not chart
        self.chart_tabs.addTab(self.stock_chart, "Chart")

        # Quarterly Financials tab
        self.quarterly_financials = QuarterlyFinancialsWidget()
        self.chart_tabs.addTab(self.quarterly_financials, "Financials")

        # Fundamentals Overview tab
        self.fundamentals_overview = FundamentalsOverviewWidget()
        self.chart_tabs.addTab(self.fundamentals_overview, "Fundamentals")

        # ETF Overview tab (created but not added to tabs until needed)
        self.etf_overview = ETFOverviewWidget()
        self._current_asset_mode = "stock"  # "stock" or "etf"

        right_layout.addWidget(self.chart_tabs, stretch=2)

        # Key Metrics panel - 3 columns
        self.metrics_group = QGroupBox("Key Metrics")
        metrics_main_layout = QHBoxLayout(self.metrics_group)
        metrics_main_layout.setContentsMargins(8, 8, 8, 8)
        metrics_main_layout.setSpacing(16)

        # Column 1: Price & Change
        col1_layout = QFormLayout()
        col1_layout.setSpacing(4)
        self.price_label = QLabel("--")
        col1_layout.addRow("Price:", self.price_label)
        self.change_label = QLabel("--")
        col1_layout.addRow("Change:", self.change_label)
        metrics_main_layout.addLayout(col1_layout)

        # Column 2: 52W High, Low, Day Vol, Avg Volume
        col2_layout = QFormLayout()
        col2_layout.setSpacing(4)
        self.week52_high_label = QLabel("--")
        col2_layout.addRow("52W High:", self.week52_high_label)
        self.week52_low_label = QLabel("--")
        col2_layout.addRow("52W Low:", self.week52_low_label)
        self.day_vol_label = QLabel("--")
        col2_layout.addRow("Day Vol:", self.day_vol_label)
        self.avg_volume_label = QLabel("--")
        self.avg_volume_row_label = QLabel("1D Avg Vol:")
        col2_layout.addRow(self.avg_volume_row_label, self.avg_volume_label)
        metrics_main_layout.addLayout(col2_layout)

        # Column 3: Market Cap & P/E
        col3_layout = QFormLayout()
        col3_layout.setSpacing(4)
        self.market_cap_label = QLabel("--")
        col3_layout.addRow("Market Cap:", self.market_cap_label)
        self.pe_label = QLabel("--")
        col3_layout.addRow("P/E Ratio:", self.pe_label)
        self.forward_pe_label = QLabel("--")
        col3_layout.addRow("Forward P/E:", self.forward_pe_label)
        metrics_main_layout.addLayout(col3_layout)

        # Column 4: Day's Data (Prev Close, Open, High, Low)
        col4_layout = QFormLayout()
        col4_layout.setSpacing(4)
        self.prev_close_label = QLabel("--")
        col4_layout.addRow("Prev Close:", self.prev_close_label)
        self.day_open_label = QLabel("--")
        col4_layout.addRow("Day Open:", self.day_open_label)
        self.day_high_label = QLabel("--")
        col4_layout.addRow("Day High:", self.day_high_label)
        self.day_low_label = QLabel("--")
        col4_layout.addRow("Day Low:", self.day_low_label)
        metrics_main_layout.addLayout(col4_layout)

        metrics_main_layout.addStretch()
        right_layout.addWidget(self.metrics_group)

        # Sentiment gauge widget
        self.sentiment_gauge = SentimentGaugeWidget()
        right_layout.addWidget(self.sentiment_gauge)

        self.main_splitter.addWidget(right_panel)

        # Set splitter sizes
        self.main_splitter.setSizes([700, 400])

        # Bottom tabs
        self.bottom_tabs = QTabWidget()
        self.main_layout.addWidget(self.bottom_tabs)

        # Watchlist tab (first tab)
        self.watchlist_widget = WatchlistWidget()
        self.watchlist_widget.stock_selected.connect(self._on_stock_selected)
        self.watchlist_widget.stock_double_clicked.connect(self._on_stock_double_clicked)
        self.watchlist_widget.stock_added.connect(self._on_stock_added)
        self.bottom_tabs.addTab(self.watchlist_widget, "Watchlist")

        # News feed tab
        self.news_feed = NewsFeedWidget()
        self.news_feed.stock_clicked.connect(self._on_stock_selected)
        self.news_feed.articles_changed.connect(self._on_news_articles_changed)
        self.bottom_tabs.addTab(self.news_feed, "News Feed")

        # FX Converter tab
        self.fx_converter = FXConverterWidget()
        self.bottom_tabs.addTab(self.fx_converter, "FX Converter")

        # Screener tab (placeholder)
        screener_tab = QWidget()
        screener_layout = QVBoxLayout(screener_tab)
        screener_label = QLabel("Stock Screener\n(Coming in Phase 4)")
        screener_label.setAlignment(Qt.AlignCenter)
        screener_label.setStyleSheet("color: #9CA3AF;")
        screener_layout.addWidget(screener_label)
        self.bottom_tabs.addTab(screener_tab, "Screener")

        # Backtest tab (placeholder)
        backtest_tab = QWidget()
        backtest_layout = QVBoxLayout(backtest_tab)
        backtest_label = QLabel("Backtesting\n(Coming in Phase 5)")
        backtest_label.setAlignment(Qt.AlignCenter)
        backtest_label.setStyleSheet("color: #9CA3AF;")
        backtest_layout.addWidget(backtest_label)
        self.bottom_tabs.addTab(backtest_tab, "Backtest")

        self.bottom_tabs.setMaximumHeight(250)

    def _create_status_bar(self) -> None:
        """Create the status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.last_update_label = QLabel("Last Update: --")
        self.status_bar.addWidget(self.last_update_label)

        self.connection_label = QLabel("EODHD: Checking...")
        self.status_bar.addWidget(self.connection_label)

        self.cache_label = QLabel("Cache: --")
        self.status_bar.addPermanentWidget(self.cache_label)

    def _setup_timers(self) -> None:
        """Setup automatic refresh timers."""
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(30000)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._auto_refresh)
        refresh_interval = self.config.data.auto_refresh_interval_minutes * 60 * 1000
        self.refresh_timer.start(refresh_interval)

        # Live price refresh timer (15 seconds for real-time updates)
        self.live_price_timer = QTimer(self)
        self.live_price_timer.timeout.connect(self._refresh_live_prices)
        self.live_price_timer.start(15000)  # 15 seconds

        # EODHD data availability check timer (every 30 minutes)
        self.eodhd_check_timer = QTimer(self)
        self.eodhd_check_timer.timeout.connect(self._check_eodhd_data_availability)
        self.eodhd_check_timer.start(30 * 60 * 1000)  # 30 minutes

        # Track last known EODHD intraday date
        self._last_eodhd_date: Optional[date] = None

        # Check EODHD availability on startup (delayed to allow app to load)
        QTimer.singleShot(5000, self._check_eodhd_data_availability)

    def _check_eodhd_data_availability(self) -> None:
        """Check if EODHD has new intraday data available."""
        if not self.data_manager:
            return

        # Get expected trading date (today if after market open, else previous trading day)
        now_utc = datetime.utcnow()
        now_et = now_utc + _get_utc_offset("US")
        current_date_et = now_et.date()

        from datetime import time as dt_time
        market_open_et = dt_time(9, 30)

        if now_et.time() < market_open_et:
            expected_date = current_date_et - timedelta(days=1)
        else:
            expected_date = current_date_et

        # Skip weekends
        while expected_date.weekday() >= 5:
            expected_date = expected_date - timedelta(days=1)

        # Check if EODHD has data for this date
        day_open = datetime(expected_date.year, expected_date.month, expected_date.day, 14, 30)
        day_close = datetime(expected_date.year, expected_date.month, expected_date.day, 21, 0)

        try:
            # Use a common symbol to check availability
            test_data = self.data_manager.get_intraday_prices(
                "AAPL", "US", "1m",
                day_open.replace(tzinfo=timezone.utc),
                day_close.replace(tzinfo=timezone.utc),
                use_cache=True,
                force_refresh=True,
            )

            if test_data is not None and not test_data.empty:
                if self._last_eodhd_date != expected_date:
                    logger.info(f"EODHD now has data for {expected_date}")
                    self._last_eodhd_date = expected_date
                    self.status_bar.showMessage(
                        f"New EODHD data available for {expected_date.strftime('%b %d')}", 5000
                    )
                    # Refresh current chart if 1D is selected
                    if self._selected_ticker and self.stock_chart.get_period() == "1D":
                        self._load_stock_chart(self._selected_ticker, self._selected_exchange)
            else:
                logger.info(f"EODHD does not have data for {expected_date} yet")
        except Exception as e:
            logger.warning(f"Error checking EODHD availability: {e}")

    def _refresh_live_prices(self) -> None:
        """Refresh live prices from data server.

        During market hours: full refresh every 15s (treemap + chart + metrics).
        Outside market hours: reduced rate refresh (~60s).
        Treemap data is always refreshed regardless of period selection.
        All data comes from the local data server — no direct API calls.
        """
        from investment_tool.utils.exchange_hours import is_market_open

        if not self.data_manager:
            return

        period = self.period_combo.currentText()
        market_open = is_market_open("US")

        if not hasattr(self, '_offhours_tick'):
            self._offhours_tick = 0

        if market_open and period == "1D":
            # Full refresh during market hours for 1D view
            self._load_treemap_data()
            now = datetime.now().strftime("%H:%M:%S")
            self.status_bar.showMessage(f"Live prices updated at {now}", 10000)

            if self._selected_ticker and self._selected_exchange:
                if self.advanced_btn.isChecked():
                    self._load_advanced_chart()
                else:
                    self._load_stock_chart(self._selected_ticker, self._selected_exchange)
                self._update_metrics(self._selected_ticker, self._selected_exchange)
        else:
            # Non-1D period or outside market hours: refresh treemap at reduced rate
            # (every 4th tick = ~60s instead of 15s)
            self._offhours_tick += 1
            if self._offhours_tick % 4 == 0:
                self._load_treemap_data()

    def _initialize_data(self) -> None:
        """Initialize data manager and load initial data."""
        try:
            self.data_manager = get_data_manager()
            self._update_status()

            # Set data_manager on widgets
            self.watchlist_widget.set_data_manager(self.data_manager)
            self.sentiment_gauge.set_data_manager(self.data_manager)
            self.news_feed.set_data_manager(self.data_manager)
            self.quarterly_financials.set_data_manager(self.data_manager)
            self.fundamentals_overview.set_data_manager(self.data_manager)
            self.etf_overview.set_data_manager(self.data_manager)
            self.fx_converter.set_data_manager(self.data_manager)
            self.advanced_chart.set_data_manager(self.data_manager)

            if self.data_manager.is_connected():
                # Get server status for EODHD API call count
                server_status = self.data_manager.get_server_status()
                if server_status:
                    api_calls = server_status.get("eodhd_api_calls", 0)
                    self.connection_label.setText(f"Data Server: Connected | EODHD Calls: {api_calls}")
                else:
                    self.connection_label.setText("Data Server: Connected")
                self.connection_label.setStyleSheet("color: #22C55E;")

                # Sync all stocks to data server for live price tracking
                self._sync_stocks_to_server()

                # Show loading state while data server may still be warming up
                self.treemap.set_loading(True)

                # Load treemap with default category
                self._load_treemap_data()

                # Set period and refresh watchlist with current data
                period = self.period_combo.currentText()
                self.watchlist_widget.set_period(period)
                self.watchlist_widget.refresh_all()

                # News feed only loads when a stock is selected
            else:
                self.connection_label.setText("EODHD: Not Configured")
                self.connection_label.setStyleSheet("color: #F59E0B;")

            # Update category filter in treemap
            categories = [c.name for c in self.category_manager.get_all_categories()]
            self.treemap.set_categories(categories)

        except Exception as e:
            logger.error(f"Failed to initialize data: {e}")
            self.connection_label.setText("EODHD: Error")
            self.connection_label.setStyleSheet("color: #EF4444;")

    def _sync_stocks_to_server(self) -> None:
        """Sync all stocks from categories to data server for live price tracking."""
        import os
        import requests

        data_server_url = os.getenv("DATA_SERVER_URL", "").rstrip("/")
        if not data_server_url:
            logger.debug("DATA_SERVER_URL not set, skipping stock sync")
            return

        try:
            # Collect all unique stocks from all categories
            stocks = []
            seen = set()
            for category in self.category_manager.get_all_categories():
                for stock_ref in category.stocks:
                    key = f"{stock_ref.ticker}.{stock_ref.exchange}"
                    if key not in seen:
                        seen.add(key)
                        stocks.append({
                            "ticker": stock_ref.ticker,
                            "exchange": stock_ref.exchange,
                        })

            if not stocks:
                return

            # Sync to data server
            response = requests.post(
                f"{data_server_url}/tracking/stocks/sync",
                json={"stocks": stocks},
                timeout=10,
            )
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Synced {result.get('added', 0)} stocks to data server (total: {result.get('total_tracked', 0)})")
            else:
                logger.warning(f"Failed to sync stocks to data server: {response.status_code}")

        except Exception as e:
            logger.warning(f"Could not sync stocks to data server: {e}")

    def _load_treemap_data(self) -> None:
        """Load data for the market treemap."""
        if not self.data_manager or not self.data_manager.is_connected():
            return

        # Get selected filter and period
        selected_filter = self.treemap.get_selected_filter()
        selected_period = self.period_combo.currentText()

        # Set current category ID for removal operations
        market_cap_filters = ("All Stocks", "Large Cap (>$200B)", "Mid Cap ($20B-$200B)", "Small Cap ($2B-$20B)", "Tiny Stocks (<$2B)")
        if selected_filter not in market_cap_filters:
            category = self.category_manager.get_category_by_name(selected_filter)
            self.treemap.set_current_category_id(str(category.id) if category else None)
        else:
            self.treemap.set_current_category_id(None)

        # Get date range for the selected period
        start, end = get_date_range(selected_period, min_trading_days=0)

        # Get stocks from categories, avoiding duplicates
        items: List[TreemapItem] = []
        seen_tickers: set = set()

        # Market cap filters that should include all categories
        market_cap_filters = ("All Stocks", "Large Cap (>$200B)", "Mid Cap ($20B-$200B)", "Small Cap ($2B-$20B)", "Tiny Stocks (<$2B)")

        all_categories = self.category_manager.get_all_categories()
        logger.info(f"Found {len(all_categories)} categories")

        # First pass: collect all symbols and their metadata
        stock_refs_by_symbol: Dict[str, tuple] = {}  # symbol -> (stock_ref, category)
        # Track tickers seen across exchanges to deduplicate (prefer US listing)
        ticker_to_symbol: Dict[str, str] = {}  # bare ticker -> best ticker_key
        for category in all_categories:
            if selected_filter not in market_cap_filters and category.name != selected_filter:
                continue
            for stock_ref in category.stocks[:30]:
                ticker_key = f"{stock_ref.ticker}.{stock_ref.exchange}"
                if selected_filter in market_cap_filters:
                    if ticker_key in seen_tickers:
                        continue
                    seen_tickers.add(ticker_key)
                # Deduplicate same ticker across exchanges (prefer US listing)
                bare_ticker = stock_ref.ticker
                if bare_ticker in ticker_to_symbol:
                    existing_key = ticker_to_symbol[bare_ticker]
                    existing_exchange = existing_key.split(".")[-1]
                    if stock_ref.exchange == "US" and existing_exchange != "US":
                        # Replace non-US with US listing
                        del stock_refs_by_symbol[existing_key]
                        ticker_to_symbol[bare_ticker] = ticker_key
                    elif existing_exchange == "US":
                        # Already have US listing, skip this one
                        continue
                    else:
                        # Both non-US, keep whichever came first
                        continue
                else:
                    ticker_to_symbol[bare_ticker] = ticker_key
                stock_refs_by_symbol[ticker_key] = (stock_ref, category)

        # Use live prices for 1D when market is open, batch API otherwise
        batch_changes = {}
        if stock_refs_by_symbol:
            symbols = list(stock_refs_by_symbol.keys())

            # For 1D, use live prices which have today's price vs previous close
            # Filter to today's timestamps for treemap (stale data = wrong daily change)
            if selected_period == "1D":
                all_live = self.data_manager.get_all_live_prices()
                today_str = date.today().isoformat()
                live_prices = {
                    k: v for k, v in all_live.items()
                    if str(v.get("market_timestamp", "")).startswith(today_str)
                }
                if live_prices:
                    for symbol in symbols:
                        if symbol in live_prices:
                            lp = live_prices[symbol]
                            price = lp.get("price")
                            prev_close = lp.get("previous_close")
                            if price and prev_close and prev_close != 0:
                                change = (price - prev_close) / prev_close
                                batch_changes[symbol] = {
                                    "end_price": price,
                                    "change": change,
                                }
                    logger.info(f"Live prices returned {len(batch_changes)}/{len(symbols)} for period=1D")

            # Fallback to batch API for symbols missing from live prices
            missing_symbols = [s for s in symbols if s not in batch_changes]
            if missing_symbols:
                # For 1D, compare last 2 trading days (EODHD daily prices)
                use_daily_change = (selected_period == "1D")
                fallback = self.data_manager.get_batch_daily_changes(
                    missing_symbols,
                    start.date() if hasattr(start, 'date') else start,
                    end.date() if hasattr(end, 'date') else end,
                    daily_change=use_daily_change,
                )
                batch_changes.update(fallback)
                logger.info(f"Batch API returned {len(fallback)}/{len(missing_symbols)} price changes for period={selected_period}")

        # Batch fetch company highlights for all symbols (1 call instead of N)
        all_highlights = self.data_manager.get_batch_highlights(list(stock_refs_by_symbol.keys()))

        # Second pass: build treemap items using batch results
        for ticker_key, (stock_ref, category) in stock_refs_by_symbol.items():
            try:
                if ticker_key in batch_changes:
                    price_data = batch_changes[ticker_key]
                    current = price_data.get("end_price")
                    change = price_data.get("change", 0)
                    if current is None:
                        # No price — show placeholder in category views
                        if selected_filter not in market_cap_filters:
                            items.append(TreemapItem(
                                ticker=stock_ref.ticker,
                                name=stock_ref.ticker,
                                exchange=stock_ref.exchange,
                                value=1e9,
                                change_percent=0,
                                sector=category.name,
                            ))
                        continue
                else:
                    # No price data — show placeholder in category views
                    if selected_filter not in market_cap_filters:
                        items.append(TreemapItem(
                            ticker=stock_ref.ticker,
                            name=stock_ref.ticker,
                            exchange=stock_ref.exchange,
                            value=1e9,
                            change_percent=0,
                            sector=category.name,
                        ))
                    continue

                hl = all_highlights.get(ticker_key, {})

                # Convert price to USD for non-USD stocks
                price_usd = current
                fx = hl.get("fx_rate_to_usd")
                ccy = hl.get("currency")
                if fx and ccy and ccy != "USD":
                    price_usd = current * fx

                # Market cap from batch highlights (already computed server-side)
                market_cap = hl.get("market_cap") or 1e9

                # P/E from batch highlights
                pe_ratio = hl.get("pe_ratio")

                # Apply market cap filter
                if selected_filter == "Large Cap (>$200B)" and (market_cap or 0) < 200e9:
                    continue
                elif selected_filter == "Mid Cap ($20B-$200B)" and not (20e9 <= (market_cap or 0) < 200e9):
                    continue
                elif selected_filter == "Small Cap ($2B-$20B)" and not (2e9 <= (market_cap or 0) < 20e9):
                    continue
                elif selected_filter == "Tiny Stocks (<$2B)" and (market_cap or 0) >= 2e9:
                    continue

                items.append(TreemapItem(
                    ticker=stock_ref.ticker,
                    name=hl.get("name") or stock_ref.ticker,
                    exchange=stock_ref.exchange,
                    value=market_cap or 1e9,
                    change_percent=change,
                    sector=category.name,
                    price=price_usd,
                    pe_ratio=pe_ratio,
                    market_cap=market_cap,
                ))

            except Exception as e:
                logger.debug(f"Failed to load {stock_ref.ticker}: {e}")
                # Skip placeholders for market cap filtered views
                if selected_filter in ("Large Cap (>$200B)", "Mid Cap ($20B-$200B)", "Small Cap ($2B-$20B)", "Tiny Stocks (<$2B)"):
                    continue
                # Add placeholder for All Stocks or category views
                items.append(TreemapItem(
                    ticker=stock_ref.ticker,
                    name=stock_ref.ticker,
                    exchange=stock_ref.exchange,
                    value=1e9,
                    change_percent=0,
                    sector=category.name,
                ))

        logger.info(f"Treemap loaded {len(items)} items for period={selected_period}, filter={selected_filter}")
        if items:
            self.treemap.set_items(items)
        else:
            # Keep loading state if no items yet (data server may still be warming up)
            self.treemap.set_loading(True)

    def _configure_tabs_for_asset_type(self, asset_type: str) -> None:
        """Reconfigure chart_tabs based on whether this is an ETF or stock.

        Stock mode (default): Chart | Financials | Fundamentals
        ETF mode: Chart | ETF Overview
        """
        mode = "etf" if asset_type == "ETF" else "stock"
        if mode == self._current_asset_mode:
            return

        # Remember current tab index to restore Chart tab if possible
        current_idx = self.chart_tabs.currentIndex()

        # Remove all tabs except Chart (index 0)
        while self.chart_tabs.count() > 1:
            self.chart_tabs.removeTab(1)

        if mode == "etf":
            self.chart_tabs.addTab(self.etf_overview, "ETF Overview")
        else:
            self.chart_tabs.addTab(self.quarterly_financials, "Financials")
            self.chart_tabs.addTab(self.fundamentals_overview, "Fundamentals")

        self._current_asset_mode = mode

        # Restore tab position if valid
        if current_idx < self.chart_tabs.count():
            self.chart_tabs.setCurrentIndex(current_idx)

    def _on_stock_selected(self, ticker: str, exchange: str) -> None:
        """Handle stock selection."""
        # Prevent circular selection
        if self._selecting:
            return

        # Skip if already selected
        if self._selected_ticker == ticker and self._selected_exchange == exchange:
            return

        self._selecting = True
        try:
            import time
            total_start = time.perf_counter()

            self._selected_ticker = ticker
            self._selected_exchange = exchange

            logger.info(f"Stock selected: {ticker}.{exchange}")

            # Select the stock in the treemap (if visible in current view)
            self.treemap.select_stock(ticker, exchange)

            # Select the stock in the watchlist (if present)
            self.watchlist_widget.select_stock(ticker, exchange)

            # Fetch all data in parallel using threads
            articles = None
            if self.data_manager:
                end_date = date.today()
                start_date = end_date - timedelta(days=30)

                # Define fetch functions
                def fetch_news():
                    t0 = time.perf_counter()
                    # Fetch only 100 initially for fast loading - more loaded on demand
                    result = self.data_manager.get_news(
                        ticker, limit=100, from_date=start_date, to_date=end_date,
                        refresh=True,
                    )
                    logger.info(f"[TIMING] News fetch: {(time.perf_counter() - t0)*1000:.0f}ms ({len(result) if result else 0} articles)")
                    return result

                # Run news fetch in parallel with chart/metrics (which share some data)
                with ThreadPoolExecutor(max_workers=2) as executor:
                    news_future = executor.submit(fetch_news)

                    # Load chart and metrics on main thread (they update UI)
                    t1 = time.perf_counter()
                    if self.advanced_btn.isChecked():
                        self._load_advanced_chart()
                    else:
                        self._load_stock_chart(ticker, exchange)
                    logger.info(f"[TIMING] Chart load: {(time.perf_counter() - t1)*1000:.0f}ms")

                    t2 = time.perf_counter()
                    self._update_metrics(ticker, exchange)
                    logger.info(f"[TIMING] Metrics update: {(time.perf_counter() - t2)*1000:.0f}ms")

                    # Get news result
                    t3 = time.perf_counter()
                    articles = news_future.result()
                    logger.info(f"[TIMING] News future.result(): {(time.perf_counter() - t3)*1000:.0f}ms")

            # Update sentiment gauge with pre-fetched articles
            t4 = time.perf_counter()
            self.sentiment_gauge.set_ticker(ticker, exchange, articles=articles)
            logger.info(f"[TIMING] Sentiment gauge: {(time.perf_counter() - t4)*1000:.0f}ms")

            # Update news feed with pre-fetched articles
            t5 = time.perf_counter()
            self.news_feed.set_filter_ticker(ticker)
            self.news_feed.refresh(articles=articles)
            logger.info(f"[TIMING] News feed refresh: {(time.perf_counter() - t5)*1000:.0f}ms")

            # Determine asset type from fundamentals and configure tabs
            asset_type = None
            etf_data = None
            if self.data_manager:
                try:
                    fundamentals = self.data_manager.get_fundamentals(ticker, exchange)
                    asset_type = fundamentals.get("asset_type") if fundamentals else None
                    etf_data = fundamentals.get("etf_data") if fundamentals else None
                except Exception:
                    pass

            self._configure_tabs_for_asset_type(asset_type or "")

            if asset_type == "ETF" and etf_data:
                # ETF mode: show ETF overview
                company = self.data_manager.get_company_info(ticker, exchange) if self.data_manager else None
                name = company.name if company else ""
                self.etf_overview.set_ticker_label(ticker, name)
                self.etf_overview.update_data(etf_data)
            else:
                # Stock mode: load financials and fundamentals
                t6 = time.perf_counter()
                self.quarterly_financials.set_ticker(ticker, exchange)
                logger.info(f"[TIMING] Quarterly financials: {(time.perf_counter() - t6)*1000:.0f}ms")

                t7 = time.perf_counter()
                self.fundamentals_overview.set_ticker(ticker, exchange)
                logger.info(f"[TIMING] Fundamentals overview: {(time.perf_counter() - t7)*1000:.0f}ms")

            logger.info(f"[TIMING] TOTAL _on_stock_selected: {(time.perf_counter() - total_start)*1000:.0f}ms")
        finally:
            self._selecting = False

    def _on_stock_double_clicked(self, ticker: str, exchange: str) -> None:
        """Handle stock double-click (open in new window)."""
        logger.info(f"Stock double-clicked: {ticker}.{exchange}")
        # For now, just select and show in main view
        self._on_stock_selected(ticker, exchange)

    def _toggle_advanced_mode(self, enabled: bool) -> None:
        """Toggle between normal and advanced chart mode."""
        if enabled:
            # Default to 5Y if current period is too short for advanced analysis
            short_periods = {"1D", "1W", "1M", "3M"}
            if self.period_combo.currentText() in short_periods:
                self.period_combo.setCurrentText("5Y")
            self.main_splitter.hide()
            self.main_layout.insertWidget(0, self.advanced_chart, stretch=1)
            self.advanced_chart.show()
            # Load advanced chart for current stock
            if self._selected_ticker and self._selected_exchange:
                self._load_advanced_chart()
        else:
            self.main_layout.removeWidget(self.advanced_chart)
            self.advanced_chart.hide()
            self.main_splitter.show()
            # Refresh treemap with latest data (may have been stale while hidden)
            self._load_treemap_data()
            # Reload normal chart
            if self._selected_ticker and self._selected_exchange:
                self._load_stock_chart(self._selected_ticker, self._selected_exchange)

    def _load_advanced_chart(self) -> None:
        """Load data into the advanced chart for the current stock."""
        if not self.data_manager or not self._selected_ticker:
            return

        ticker = self._selected_ticker
        exchange = self._selected_exchange
        period = self.period_combo.currentText()

        try:
            start, end = get_date_range(period, min_trading_days=0)

            # Fetch 120 extra days so MA lines start from day 1 of the visible range
            if period != "5Y":
                extended_start = start - timedelta(days=170)  # ~120 trading days
            else:
                extended_start = start

            prices = self.data_manager.get_daily_prices(ticker, exchange, extended_start, end)
            if prices is not None and not prices.empty:
                prices = _strip_phantom_today(prices)
                self.advanced_chart.set_period(period)
                self.advanced_chart.set_data(prices, ticker, exchange, visible_start=start)
            else:
                self.advanced_chart.clear()
                self.status_bar.showMessage(f"No data for {ticker}", 3000)
        except Exception as e:
            logger.error(f"Failed to load advanced chart for {ticker}: {e}")
            self.advanced_chart.clear()

    def _on_treemap_filter_changed(self, filter_text: str) -> None:
        """Handle treemap category filter change."""
        logger.info(f"Treemap filter changed: {filter_text}")
        self._load_treemap_data()

    def _on_period_changed(self, period: str) -> None:
        """Handle period change - updates all views.

        Sets loading state and returns immediately so the event loop can
        repaint the combo box and loading indicators. Heavy data fetching
        is deferred to the next event loop cycle via QTimer.
        """
        logger.info(f"Period changed: {period}")

        # Lightweight state updates only
        self.stock_chart.set_period(period)
        self.advanced_chart.set_period(period)
        self.setCursor(Qt.WaitCursor)
        self.status_bar.showMessage(f"Loading {period} data...")
        if self._selected_ticker:
            self._set_metrics_loading()
        self.stock_chart.clear()

        # Return immediately — let event loop repaint combo, loading dots, cursor.
        # Heavy work runs on the NEXT event loop iteration.
        QTimer.singleShot(200, lambda p=period: self._do_period_update(p))

    def _do_period_update(self, period: str) -> None:
        """Execute the heavy data reload (called after UI has repainted)."""
        try:
            # Reload treemap data (even in advanced mode, keeps data fresh)
            self._load_treemap_data()

            # Reload chart and metrics if a stock is selected
            if self._selected_ticker and self._selected_exchange:
                if self.advanced_btn.isChecked():
                    self._load_advanced_chart()
                else:
                    self._load_stock_chart(self._selected_ticker, self._selected_exchange)
                self._update_metrics(self._selected_ticker, self._selected_exchange)

            # Update quarterly financials period
            self.quarterly_financials.set_period(period)

            # Update fundamentals overview period (no-op but keeps interface consistent)
            self.fundamentals_overview.set_period(period)

            # Set period and refresh watchlist data
            self.watchlist_widget.set_period(period)
            self.watchlist_widget.refresh_all()

            self.status_bar.showMessage(f"{period} data loaded", 3000)
        finally:
            self.setCursor(Qt.ArrowCursor)

    def _on_stock_remove_requested(self, ticker: str, exchange: str, category_id: str) -> None:
        """Handle stock removal from category."""
        from pathlib import Path

        if category_id == "":
            # Remove from all categories
            logger.info(f"Removing {ticker}.{exchange} from all categories")
            for category in self.category_manager.get_all_categories():
                self.category_manager.remove_stock_from_category(category.id, ticker, exchange)
        else:
            # Remove from specific category
            cat_id = int(category_id)
            category = self.category_manager.get_category(cat_id)
            logger.info(f"Removing {ticker}.{exchange} from category: {category.name if category else cat_id}")
            self.category_manager.remove_stock_from_category(cat_id, ticker, exchange)

        # Save changes
        save_path = Path.home() / ".investment_tool" / "categories.json"
        self.category_manager.save_to_file(save_path)

        # Refresh the treemap
        self._load_treemap_data()

    def _on_stock_add_to_watchlist(self, ticker: str, exchange: str) -> None:
        """Handle adding stock to watchlist from treemap."""
        self.watchlist_widget.add_stock(ticker, exchange)
        logger.info(f"Added {ticker}.{exchange} to watchlist")

    def _on_news_articles_changed(self, articles: list) -> None:
        """Handle news articles changed (e.g., Load More clicked)."""
        if self._selected_ticker and self._selected_exchange:
            self.sentiment_gauge.set_ticker(
                self._selected_ticker, self._selected_exchange, articles=articles
            )

    def _load_stock_chart(self, ticker: str, exchange: str) -> None:
        """Load chart data for a stock."""
        if not self.data_manager:
            return

        # Prevent concurrent chart loads
        if self._chart_loading:
            logger.debug(f"Chart loading in progress, skipping request for {ticker}")
            return

        self._chart_loading = True
        period = self.stock_chart.get_period()

        try:
            if is_intraday_period(period):
                # For 1D: show full trading day using exchange-specific market hours
                now_utc = datetime.utcnow()
                from datetime import time as dt_time

                # Get market hours for this exchange (DST-aware offset)
                _, open_h, open_m, close_h, close_m = _get_market_hours(exchange)
                utc_offset_td = _get_utc_offset(exchange)  # timedelta, DST-aware
                utc_offset = utc_offset_td.total_seconds() / 3600  # float hours

                # Convert UTC to exchange local time
                now_local = now_utc + utc_offset_td
                current_time_local = now_local.time()
                current_date_local = now_local.date()

                market_open_local = dt_time(open_h, open_m)
                market_close_local = dt_time(close_h, close_m)

                # Determine trading date in local time
                if current_time_local < market_open_local:
                    trading_date = current_date_local - timedelta(days=1)
                else:
                    trading_date = current_date_local

                # Skip weekends (Saturday=5, Sunday=6)
                while trading_date.weekday() >= 5:
                    trading_date = trading_date - timedelta(days=1)

                logger.info(f"Exchange {exchange}: local time {now_local.strftime('%Y-%m-%d %H:%M')} (UTC{utc_offset:+g}), trading_date: {trading_date}")

                prices = None

                # Market hours in UTC for the trading date
                market_open_utc = datetime(trading_date.year, trading_date.month, trading_date.day, open_h, open_m) - timedelta(hours=utc_offset)
                market_close_utc = datetime(trading_date.year, trading_date.month, trading_date.day, close_h, close_m) - timedelta(hours=utc_offset)

                # Check if market is currently open
                is_weekday = current_date_local.weekday() < 5
                market_is_open = is_weekday and market_open_local <= current_time_local <= market_close_local and trading_date == current_date_local

                # Create full trading day index (1-minute intervals)
                full_day_index = pd.date_range(
                    start=market_open_utc,
                    end=market_close_utc,
                    freq="1min"
                )

                if not market_is_open:
                    # Market closed - use EODHD historical only
                    # Try current trading date first, then go back to find available data
                    raw_prices = None
                    display_date = trading_date

                    # Try recent trading days (handles holidays + weekends)
                    check_date = trading_date
                    for _ in range(10):
                        # Skip weekends
                        while check_date.weekday() >= 5:
                            check_date = check_date - timedelta(days=1)

                        day_open = datetime(check_date.year, check_date.month, check_date.day, open_h, open_m) - timedelta(hours=utc_offset)
                        day_close = datetime(check_date.year, check_date.month, check_date.day, close_h, close_m) - timedelta(hours=utc_offset)

                        logger.info(f"Checking intraday for {ticker} on {check_date}")
                        try:
                            raw_prices = self.data_manager.get_intraday_prices(
                                ticker, exchange, "1m",
                                day_open.replace(tzinfo=timezone.utc),
                                day_close.replace(tzinfo=timezone.utc),
                                use_cache=True,
                                force_refresh=True,
                            )
                        except Exception as e:
                            logger.warning(f"Failed to get intraday for {check_date}: {e}")
                            raw_prices = None

                        if raw_prices is not None and not raw_prices.empty:
                            display_date = check_date
                            market_open_utc = day_open
                            market_close_utc = day_close
                            full_day_index = pd.date_range(
                                start=market_open_utc,
                                end=market_close_utc,
                                freq="1min"
                            )
                            logger.info(f"Found intraday data for {check_date} ({len(raw_prices)} records)")
                            break

                        check_date = check_date - timedelta(days=1)

                    if raw_prices is not None and not raw_prices.empty:
                        if "timestamp" in raw_prices.columns:
                            raw_prices = raw_prices.set_index("timestamp")

                        # EODHD often dumps total daily volume into the last bar -
                        # cap outlier volume at the 95th percentile of other bars
                        if "volume" in raw_prices.columns and len(raw_prices) > 10:
                            vol = raw_prices["volume"].dropna()
                            p95 = vol.quantile(0.95)
                            if p95 > 0:
                                raw_prices["volume"] = raw_prices["volume"].clip(upper=p95)

                        # For sparse data (OTC stocks with few trades), don't reindex
                        # Just use raw data directly - chart will show actual trades only
                        is_sparse = len(raw_prices) < 50  # Less than 50 actual data points

                        if is_sparse:
                            # Use raw data directly without reindexing
                            prices = raw_prices
                            logger.info(f"Sparse data for {ticker}: {len(raw_prices)} bars, skipping reindex")
                        else:
                            # Reindex to full trading day and forward-fill gaps
                            prices = raw_prices.reindex(full_day_index)
                            # Forward-fill close price first
                            # This ensures bars connect (open of bar N = close of bar N-1)
                            prices["close"] = prices["close"].ffill()
                            # For filled bars, set open=high=low=close (no movement)
                            prices["open"] = prices["open"].fillna(prices["close"])
                            prices["high"] = prices["high"].fillna(prices["close"])
                            prices["low"] = prices["low"].fillna(prices["close"])

                        if "volume" in prices.columns:
                            prices["volume"] = prices["volume"].fillna(0)
                        # Clear lunch break so chart shows a gap instead of flat line
                        _clear_lunch_break(prices, exchange, utc_offset, display_date)
                        if display_date != current_date_local:
                            self.status_bar.showMessage(
                                f"Showing {display_date.strftime('%b %d')} - latest EODHD data available", 5000
                            )
                    else:
                        # No EODHD intraday data found - should not happen normally
                        logger.warning(f"No EODHD intraday data found for {ticker} in last 5 trading days")
                        prices = None
                else:
                    # Market open - use live data from price worker (has proper OHLC from 15s aggregation)
                    try:
                        raw_prices = self.data_manager.get_intraday_prices(
                            ticker, exchange, "1m",
                            market_open_utc.replace(tzinfo=timezone.utc),
                            market_close_utc.replace(tzinfo=timezone.utc),
                            use_cache=True,
                            force_refresh=False,  # Use live data with proper OHLC
                        )
                    except Exception as e:
                        logger.warning(f"Failed to get intraday prices: {e}")
                        raw_prices = None

                    # Get current live price
                    symbol = f"{ticker}.{exchange}"
                    live_prices = self.data_manager.get_all_live_prices()
                    live_price_data = live_prices.get(symbol) if live_prices else None

                    if raw_prices is not None and not raw_prices.empty:
                        if "timestamp" in raw_prices.columns:
                            raw_prices = raw_prices.set_index("timestamp")

                        # Price worker provides proper OHLC data
                        num_points = len(raw_prices)
                        logger.info(f"Got {num_points} intraday records for {ticker} today")

                        # Reindex to full trading day
                        # Keep NaN for missing times - no forward-fill
                        prices = raw_prices.reindex(full_day_index)

                        if num_points < 10:
                            self.status_bar.showMessage(f"Building intraday data for {ticker} ({num_points} points)", 5000)
                    elif live_price_data and live_price_data.get("price"):
                        # No historical data yet - create full day with just live price at current time
                        logger.info(f"No intraday data yet for {ticker}, showing live price")
                        prices = pd.DataFrame(index=full_day_index, columns=["open", "high", "low", "close", "volume"])

                        # Set the live price at current minute
                        current_minute = pd.Timestamp(now_utc).floor("min")
                        if current_minute in prices.index:
                            prices.loc[current_minute, "open"] = live_price_data.get("price")
                            prices.loc[current_minute, "high"] = live_price_data.get("price")
                            prices.loc[current_minute, "low"] = live_price_data.get("price")
                            prices.loc[current_minute, "close"] = live_price_data.get("price")
                            prices.loc[current_minute, "volume"] = live_price_data.get("volume") or 0

                            # Forward-fill from market open to current time
                            mask_past = prices.index <= current_minute
                            prices.loc[mask_past] = prices.loc[mask_past].bfill().ffill()

                        self.status_bar.showMessage(f"Live: ${live_price_data.get('price'):.2f} (building intraday)", 5000)
                    else:
                        # No live data - likely a holiday. Try previous days' intraday.
                        logger.info(f"No live data for {ticker}, trying previous days' intraday")
                        check_date = trading_date - timedelta(days=1)
                        for _ in range(10):
                            while check_date.weekday() >= 5:
                                check_date = check_date - timedelta(days=1)
                            day_open = datetime(check_date.year, check_date.month, check_date.day, open_h, open_m) - timedelta(hours=utc_offset)
                            day_close = datetime(check_date.year, check_date.month, check_date.day, close_h, close_m) - timedelta(hours=utc_offset)
                            logger.info(f"Checking intraday for {ticker} on {check_date}")
                            try:
                                raw_prev = self.data_manager.get_intraday_prices(
                                    ticker, exchange, "1m",
                                    day_open.replace(tzinfo=timezone.utc),
                                    day_close.replace(tzinfo=timezone.utc),
                                    use_cache=True, force_refresh=True,
                                )
                            except Exception:
                                raw_prev = None
                            if raw_prev is not None and not raw_prev.empty:
                                if "timestamp" in raw_prev.columns:
                                    raw_prev = raw_prev.set_index("timestamp")
                                if "volume" in raw_prev.columns and len(raw_prev) > 10:
                                    p95 = raw_prev["volume"].dropna().quantile(0.95)
                                    if p95 > 0:
                                        raw_prev["volume"] = raw_prev["volume"].clip(upper=p95)
                                prev_index = pd.date_range(start=day_open, end=day_close, freq="1min")
                                prices = raw_prev.reindex(prev_index)
                                prices["close"] = prices["close"].ffill()
                                prices["open"] = prices["open"].fillna(prices["close"])
                                prices["high"] = prices["high"].fillna(prices["close"])
                                prices["low"] = prices["low"].fillna(prices["close"])
                                if "volume" in prices.columns:
                                    prices["volume"] = prices["volume"].fillna(0)
                                # Clear lunch break so chart shows a gap instead of flat line
                                _clear_lunch_break(prices, exchange, utc_offset, check_date)
                                logger.info(f"Found intraday data for {check_date} ({len(raw_prev)} records)")
                                self.status_bar.showMessage(
                                    f"Showing {check_date.strftime('%b %d')} - market closed today", 5000
                                )
                                break
                            check_date = check_date - timedelta(days=1)
            elif period == "1W":
                # Fetch intraday data for each trading day separately (EODHD limitation)
                # This gives ~130 data points (5 days * 26 fifteen-min periods)
                all_prices = []

                # Use exchange-aware local date (DST-aware)
                now_utc = datetime.utcnow()
                _, oh, om, ch, cm = _get_market_hours(exchange)
                utc_off_td = _get_utc_offset(exchange)
                utc_off = utc_off_td.total_seconds() / 3600
                now_local_1w = now_utc + utc_off_td
                today_local = now_local_1w.date()

                # Get last 7 calendar days, fetch each trading day
                for days_ago in range(7, -1, -1):
                    check_date = today_local - timedelta(days=days_ago)
                    # Skip weekends
                    if check_date.weekday() >= 5:
                        continue

                    # Market hours in UTC for this exchange
                    day_start = datetime(check_date.year, check_date.month, check_date.day, oh, om, tzinfo=timezone.utc) - timedelta(hours=utc_off)
                    day_end = datetime(check_date.year, check_date.month, check_date.day, ch, cm, tzinfo=timezone.utc) - timedelta(hours=utc_off)

                    # Use 1m interval - EODHD 5m data has gaps/NULLs for some stocks
                    day_prices = self.data_manager.get_intraday_prices(
                        ticker, exchange, "1m", day_start, day_end, use_cache=True,
                        force_refresh=True  # Only use EODHD data, not price worker cache
                    )
                    if day_prices is not None and not day_prices.empty:
                        all_prices.append(day_prices)

                if all_prices:
                    prices = pd.concat(all_prices, ignore_index=True)
                    if "timestamp" in prices.columns:
                        prices = prices.set_index("timestamp")
                    prices = prices.sort_index()
                    # Cap outlier volume (EODHD dumps daily total into last bar)
                    if "volume" in prices.columns and len(prices) > 10:
                        vol = prices["volume"].dropna()
                        p95 = vol.quantile(0.95)
                        if p95 > 0:
                            prices["volume"] = prices["volume"].clip(upper=p95)
                    # Resample to 15-minute OHLC for smooth graph
                    prices = prices.resample("15min").agg({
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum"
                    }).dropna()
                    if "volume" in prices.columns:
                        prices["volume"] = prices["volume"].fillna(0)
                    logger.info(f"Got {len(prices)} 15-min records for {ticker} (1W)")
                else:
                    # Fallback to daily data if no intraday available
                    logger.info(f"No intraday data for {ticker}, falling back to daily data")
                    start, end = get_date_range(period, min_trading_days=0)
                    prices = self.data_manager.get_daily_prices(ticker, exchange, start, end)
                    if prices is not None and "volume" in prices.columns:
                        prices["volume"] = prices["volume"].fillna(0)
            else:
                # Use daily data for 1M and longer periods
                start, end = get_date_range(period, min_trading_days=0)
                logger.info(f"Fetching {period} daily data for {ticker} from {start} to {end}")
                prices = self.data_manager.get_daily_prices(ticker, exchange, start, end)
                if prices is not None and not prices.empty:
                    logger.info(f"Got {len(prices)} daily records for {ticker} ({prices.index.min()} to {prices.index.max()})")
                if prices is not None and "volume" in prices.columns:
                    prices["volume"] = prices["volume"].fillna(0)

            # Check if selection changed while loading (user clicked another stock)
            if self._selected_ticker != ticker or self._selected_exchange != exchange:
                logger.debug(f"Selection changed during load, discarding data for {ticker}")
                return

            # Convert chart prices to USD for non-USD stocks using date-specific FX rates
            if prices is not None and not prices.empty and exchange != "US":
                try:
                    company = self.data_manager.get_company_info(ticker, exchange)
                    if company and company.currency and company.currency != "USD":
                        # Try to get historical daily FX rates for date-accurate conversion
                        dates = prices.index
                        min_date = (dates.min().date() if hasattr(dates.min(), 'date') else dates.min()).isoformat()
                        max_date = (dates.max().date() if hasattr(dates.max(), 'date') else dates.max()).isoformat()
                        fx_rates = self.data_manager.get_forex_rates(
                            company.currency, from_date=min_date, to_date=max_date,
                        )

                        if fx_rates:
                            # Build a Series of FX rates indexed by date string
                            price_dates = pd.Series(
                                [d.date().isoformat() if hasattr(d, 'date') else str(d)[:10] for d in dates],
                                index=dates,
                            )
                            fx_series = price_dates.map(fx_rates)
                            # Forward-fill missing dates (weekends/holidays use previous rate)
                            fx_series = fx_series.ffill().bfill()

                            if fx_series.notna().any():
                                for col in ("open", "high", "low", "close"):
                                    if col in prices.columns:
                                        prices[col] = prices[col] * fx_series
                                logger.info(
                                    f"Converted {ticker} chart prices to USD using "
                                    f"{fx_series.nunique()} historical FX rates"
                                )
                            else:
                                # No historical rates available, use today's rate
                                fx = company.fx_rate_to_usd
                                if fx:
                                    for col in ("open", "high", "low", "close"):
                                        if col in prices.columns:
                                            prices[col] = prices[col] * fx
                                    logger.info(f"Converted {ticker} chart prices to USD (single fx={fx:.6f})")
                        elif company.fx_rate_to_usd:
                            # No historical rates in DB, fall back to today's rate
                            fx = company.fx_rate_to_usd
                            for col in ("open", "high", "low", "close"):
                                if col in prices.columns:
                                    prices[col] = prices[col] * fx
                            logger.info(f"Converted {ticker} chart prices to USD (fallback fx={fx:.6f})")
                except Exception as e:
                    logger.warning(f"Failed to convert chart prices to USD: {e}")

            if prices is not None and not prices.empty:
                logger.info(f"Chart data for {ticker}: {len(prices)} rows, index={prices.index[0]} to {prices.index[-1]}, dates={set(d.date() if hasattr(d, 'date') else d for d in prices.index)}")
                self.stock_chart.set_data(prices, ticker, exchange)
            else:
                self.stock_chart.clear()
                self.status_bar.showMessage(f"No data available for {ticker}", 3000)

        except Exception as e:
            logger.error(f"Failed to load chart for {ticker}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Only clear if this is still the selected stock
            if self._selected_ticker == ticker:
                self.stock_chart.clear()
        finally:
            self._chart_loading = False

    def _set_metrics_loading(self) -> None:
        """Set metrics panel to loading state for immediate visual feedback."""
        loading = "\u2022\u2022\u2022"
        self.price_label.setText(loading)
        self.change_label.setText(loading)
        self.prev_close_label.setText(loading)
        self.day_open_label.setText(loading)
        self.day_high_label.setText(loading)
        self.day_low_label.setText(loading)
        self.week52_high_label.setText(loading)
        self.week52_low_label.setText(loading)
        self.day_vol_label.setText(loading)
        self.avg_volume_label.setText(loading)
        self.market_cap_label.setText(loading)
        self.pe_label.setText(loading)
        self.forward_pe_label.setText(loading)

    def _update_metrics(self, ticker: str, exchange: str) -> None:
        """Update the metrics panel for a stock."""
        if not self.data_manager:
            return

        try:
            # Get company info
            company = self.data_manager.get_company_info(ticker, exchange)

            # Get period from chart
            period = self.stock_chart.get_period()

            # Get period date range and fetch daily prices (used by both branches)
            start, end = get_date_range(period, min_trading_days=0)
            period_prices = self.data_manager.get_daily_prices(ticker, exchange, start, end)

            if is_intraday_period(period):
                # Detect phantom today entry: if today's OHLC duplicates a recent
                # day's OHLC, it's stale pre-market data, not a real close
                period_prices = _strip_phantom_today(period_prices)

                symbol = f"{ticker}.{exchange}"

                # Get live prices (provider already filters stale data)
                live_data = None
                live_prices = self.data_manager.get_all_live_prices()
                if live_prices:
                    live_data = live_prices.get(symbol)

                # Get previous day's close from EODHD daily prices
                prev_close = None
                if period_prices is not None and len(period_prices) >= 2:
                    prev_close = period_prices["close"].iloc[-2]

                if live_data and live_data.get("price"):
                    # Use live data for current price and day stats
                    current = live_data.get("price")
                    total_volume = live_data.get("volume", 0)
                    day_open = live_data.get("open")
                    day_high = live_data.get("high")
                    day_low = live_data.get("low")
                    # Prefer LivePrice previousClose — yfinance daily data may be
                    # auto-adjusted (dividends/splits) causing prev close != actual close
                    live_prev = live_data.get("previous_close")
                    if live_prev is not None:
                        prev_close = live_prev
                    if prev_close is not None:
                        change = current - prev_close
                        change_pct = change / prev_close if prev_close != 0 else 0
                    else:
                        change = 0
                        change_pct = 0
                    logger.debug(f"Using live price for {ticker}: {current} (change={change})")
                else:
                    # No live data - use EODHD daily prices entirely
                    if period_prices is not None and len(period_prices) >= 1:
                        last_day = period_prices.iloc[-1]
                        current = last_day["close"]
                        total_volume = last_day["volume"] if "volume" in period_prices.columns else 0
                        day_open = last_day["open"] if "open" in period_prices.columns else None
                        day_high = last_day["high"] if "high" in period_prices.columns else None
                        day_low = last_day["low"] if "low" in period_prices.columns else None
                    else:
                        current = None
                        total_volume = 0
                        day_open = None
                        day_high = None
                        day_low = None

                    if current is not None and prev_close is not None:
                        change = current - prev_close
                        change_pct = change / prev_close if prev_close != 0 else 0
                    else:
                        change = 0
                        change_pct = 0
            else:
                # For other periods: compare start to end
                if period_prices is not None and len(period_prices) >= 1:
                    current = period_prices["close"].iloc[-1]
                    first = period_prices["close"].iloc[0]
                    change = current - first
                    change_pct = change / first if first != 0 else 0
                    total_volume = period_prices["volume"].sum()
                else:
                    current = None
                    change = 0
                    change_pct = 0
                    total_volume = 0

            # Convert prices to USD for non-USD stocks
            fx = company.fx_rate_to_usd if company and company.fx_rate_to_usd else None
            if fx and company.currency and company.currency != "USD":
                if current is not None:
                    current = current * fx
                if change is not None:
                    change = change * fx
                if is_intraday_period(period):
                    if prev_close is not None:
                        prev_close = prev_close * fx
                    if day_open is not None:
                        day_open = day_open * fx
                    if day_high is not None:
                        day_high = day_high * fx
                    if day_low is not None:
                        day_low = day_low * fx

            if current is not None:
                self.price_label.setText(f"${current:.2f}")

                change_color = "#22C55E" if change >= 0 else "#EF4444"
                sign = "+" if change >= 0 else ""
                self.change_label.setText(
                    f"<span style='color: {change_color};'>"
                    f"{sign}${change:.2f} ({format_percent(change_pct)})</span>"
                )
                self.change_label.setTextFormat(Qt.RichText)

            # Update day's data (Prev Close, Open, High, Low) - only for intraday periods
            if is_intraday_period(period):
                self.prev_close_label.setText(f"${prev_close:.2f}" if prev_close is not None else "--")
                self.day_open_label.setText(f"${day_open:.2f}" if day_open is not None else "--")
                self.day_high_label.setText(f"${day_high:.2f}" if day_high is not None else "--")
                self.day_low_label.setText(f"${day_low:.2f}" if day_low is not None else "--")
            else:
                # Clear day data for non-intraday periods (52W High/Low is more relevant)
                self.prev_close_label.setText("--")
                self.day_open_label.setText("--")
                self.day_high_label.setText("--")
                self.day_low_label.setText("--")

            # Get 52-week data for high/low (fetch once, used for multiple metrics)
            week52_start = date.today() - timedelta(days=365)
            week52_end = date.today()
            week52_prices = self.data_manager.get_daily_prices(ticker, exchange, week52_start, week52_end)

            if week52_prices is not None and len(week52_prices) >= 1:
                week52_high = week52_prices["high"].max()
                week52_low = week52_prices["low"].min()
                if fx and company and company.currency and company.currency != "USD":
                    week52_high = week52_high * fx
                    week52_low = week52_low * fx
                self.week52_high_label.setText(f"${week52_high:.2f}")
                self.week52_low_label.setText(f"${week52_low:.2f}")
            else:
                self.week52_high_label.setText("--")
                self.week52_low_label.setText("--")

            # Day Vol = last day's volume; {period} Avg Vol = period average
            self.avg_volume_row_label.setText(f"{period} Avg Vol:")
            if period_prices is not None and len(period_prices) >= 1:
                day_volume = period_prices["volume"].iloc[-1]
                self.day_vol_label.setText(format_large_number(day_volume))
                if is_intraday_period(period):
                    # 1D Avg Vol = Day Vol (1-day average is just that day)
                    avg_volume = day_volume
                else:
                    avg_volume = period_prices["volume"].mean()
                self.avg_volume_label.setText(format_large_number(avg_volume))
            else:
                self.day_vol_label.setText("--")
                self.avg_volume_label.setText("--")

            if company:
                # Update metrics group title with company name
                company_name = company.name if company.name else ticker
                self.metrics_group.setTitle(f"Key Metrics - {company_name}")

                # Compute market cap dynamically = shares × current price (USD)
                mcap_text = "--"
                fundamentals = self.data_manager.get_fundamentals(ticker, exchange)
                if fundamentals and current is not None:
                    shares = fundamentals.get("highlights", {}).get("shares_outstanding")
                    if shares:
                        mcap_text = format_large_number(shares * current, decimals=2)
                self.market_cap_label.setText(mcap_text)
                highlights = fundamentals.get("highlights", {}) if fundamentals else {}

                # Helper: get FX factor to convert EPS from earnings_ccy to USD
                # (current price is already in USD after the conversion above)
                earnings_ccy = highlights.get("earnings_currency")
                eps_to_usd = 1.0
                if earnings_ccy and earnings_ccy != "USD":
                    rates = self.data_manager.get_forex_rates(earnings_ccy)
                    if rates:
                        latest = max(rates.keys())
                        eps_to_usd = rates[latest]
                        logger.debug(f"EPS FX for {ticker}: {earnings_ccy}→USD = {eps_to_usd:.6f}")

                # Display trailing P/E: recompute with FX conversion
                trailing_eps = highlights.get("eps")
                if trailing_eps and current is not None and trailing_eps != 0:
                    eps_usd = trailing_eps * eps_to_usd
                    pe = current / eps_usd
                    if pe > 0:
                        self.pe_label.setText(f"{pe:.2f}")
                    else:
                        self.pe_label.setText("--")
                elif company.pe_ratio is not None and company.pe_ratio > 0:
                    # Only trust EODHD's pe_ratio for USD stocks (currency mismatch risk)
                    if not earnings_ccy or earnings_ccy == "USD":
                        self.pe_label.setText(f"{company.pe_ratio:.2f}")
                    else:
                        self.pe_label.setText("--")
                else:
                    self.pe_label.setText("--")

                # Compute Forward P/E dynamically = current price / forward EPS estimate
                # Use next year's EPS if today is past the fiscal year end month
                forward_pe_text = "--"
                eps_next = highlights.get("eps_estimate_next_year")
                eps_curr = highlights.get("eps_estimate_current_year")
                fy_end = highlights.get("fiscal_year_end")  # e.g. "January"
                eps_est = eps_curr
                if fy_end and eps_next:
                    try:
                        fy_month = datetime.strptime(fy_end, "%B").month
                        if date.today().month > fy_month:
                            eps_est = eps_next
                    except ValueError:
                        pass
                if eps_est and current is not None and eps_est != 0:
                    fwd_pe = current / (eps_est * eps_to_usd)
                    if fwd_pe > 0:
                        forward_pe_text = f"{fwd_pe:.2f}"
                elif highlights.get("forward_pe") is not None and highlights["forward_pe"] > 0:
                    # Only trust EODHD's forward_pe for USD-denominated stocks;
                    # non-USD stocks have known currency mismatch issues in EODHD data
                    earnings_ccy = highlights.get("earnings_currency")
                    if not earnings_ccy or earnings_ccy == "USD":
                        forward_pe_text = f"{highlights['forward_pe']:.2f}"
                self.forward_pe_label.setText(forward_pe_text)
            else:
                self.metrics_group.setTitle(f"Key Metrics - {ticker}")
                self.market_cap_label.setText("--")
                self.pe_label.setText("--")
                self.forward_pe_label.setText("--")

        except Exception as e:
            logger.error(f"Failed to update metrics for {ticker}: {e}")


    def _update_status(self) -> None:
        """Update status bar information."""
        self.last_update_label.setText(
            f"Last Update: {datetime.now().strftime('%H:%M:%S')}"
        )

        if self.data_manager:
            # Cache stats handled by data server
            self.cache_label.setText("Data Server")

            if self.data_manager.is_connected():
                server_status = self.data_manager.get_server_status()
                if server_status:
                    api_calls = server_status.get("eodhd_api_calls", 0)
                    self.connection_label.setText(f"Data Server: Connected | EODHD Calls: {api_calls}")
                else:
                    self.connection_label.setText("Data Server: Connected")

    def _auto_refresh(self) -> None:
        """Perform automatic data refresh."""
        logger.debug("Auto-refresh triggered")
        self._load_treemap_data()

    def _on_refresh(self) -> None:
        """Handle refresh action."""
        logger.info("Manual refresh triggered")
        self._load_treemap_data()

        if self._selected_ticker and self._selected_exchange:
            if self.advanced_btn.isChecked():
                self._load_advanced_chart()
            else:
                self._load_stock_chart(self._selected_ticker, self._selected_exchange)
            self._update_metrics(self._selected_ticker, self._selected_exchange)

        self._update_status()
        self.status_bar.showMessage("Data refreshed", 3000)

    # ------------------------------------------------------------------
    # Update Database
    # ------------------------------------------------------------------

    def _on_update_database(self) -> None:
        """Bulk-update the database cache for all stocks across categories."""
        if not self.data_manager or not self.data_manager.is_connected():
            QMessageBox.warning(
                self, "Update Database",
                "Data server is not connected. Cannot update database.",
            )
            return

        if self._db_update_progress is not None:
            QMessageBox.information(
                self, "Update Database",
                "A database update is already running.",
            )
            return

        # Collect all unique stocks
        stocks: list[tuple[str, str]] = []
        seen: set[str] = set()
        for category in self.category_manager.get_all_categories():
            for ref in category.stocks:
                key = f"{ref.ticker}.{ref.exchange}"
                if key not in seen:
                    seen.add(key)
                    stocks.append((ref.ticker, ref.exchange))

        if not stocks:
            QMessageBox.information(
                self, "Update Database",
                "No stocks found in any category.",
            )
            return

        # Create progress dialog
        progress = QProgressDialog(
            "Preparing database update...", "Cancel", 0, len(stocks), self,
        )
        progress.setWindowTitle("Update Database")
        progress.setMinimumDuration(0)
        progress.setModal(True)
        progress.setValue(0)
        self._db_update_progress = progress

        # Connect our cross-thread signal to update progress on the main thread
        self.db_update_progress.connect(self._on_db_update_progress)

        # Run in background thread via ThreadManager
        from investment_tool.utils.threading import get_thread_manager
        tm = get_thread_manager()
        tm.submit(
            self._update_database_worker,
            stocks,
            on_finished=self._on_update_database_finished,
            worker_id="update_database",
        )

    def _update_database_worker(
        self, stocks: list[tuple[str, str]],
    ) -> dict:
        """Background worker: fetch daily (5Y) and intraday (1 month) data for every stock.

        First queries the data server for existing cache coverage, then only
        requests the missing date ranges for each symbol.
        """
        import os
        import requests as http_requests

        today = date.today()
        daily_target_start = today - timedelta(days=5 * 365)
        intraday_target_start = datetime.combine(today - timedelta(days=30), datetime.min.time())
        intraday_target_end = datetime.combine(today, datetime.max.time())

        # --- Invalidate fundamentals cache so new fields get re-fetched ---
        symbols = [f"{t}.{e}" for t, e in stocks]
        data_server_url = os.getenv("DATA_SERVER_URL", "").rstrip("/")
        if data_server_url:
            try:
                http_requests.post(
                    f"{data_server_url}/api/cache/invalidate",
                    json={"prefix": "fundamentals:"},
                    timeout=10,
                )
                logger.info("Invalidated fundamentals cache for re-fetch")
            except Exception as e:
                logger.warning(f"Could not invalidate fundamentals cache: {e}")
            try:
                http_requests.post(
                    f"{data_server_url}/api/cache/invalidate",
                    json={"prefix": "eod:"},
                    timeout=10,
                )
                logger.info("Invalidated EOD cache for re-fetch")
            except Exception as e:
                logger.warning(f"Could not invalidate EOD cache: {e}")

        # --- Fetch existing coverage from data server in one batch call ---
        daily_coverage: dict = {}
        intraday_coverage: dict = {}
        if data_server_url:
            try:
                resp = http_requests.post(
                    f"{data_server_url}/api/cache/coverage",
                    json={"symbols": symbols},
                    timeout=15,
                )
                if resp.status_code == 200:
                    body = resp.json()
                    daily_coverage = body.get("daily", {})
                    intraday_coverage = body.get("intraday", {})
                    logger.info(
                        f"Cache coverage: {len(daily_coverage)} daily, "
                        f"{len(intraday_coverage)} intraday symbols cached"
                    )
            except Exception as e:
                logger.warning(f"Could not fetch cache coverage: {e}")

        success = 0
        failed = 0
        skipped = 0

        from investment_tool.utils.threading import get_thread_manager
        tm = get_thread_manager()
        worker = tm._active_workers.get("update_database")

        for i, (ticker, exchange) in enumerate(stocks):
            # Check cancellation
            if worker and worker.is_cancelled:
                skipped = len(stocks) - i
                break

            symbol = f"{ticker}.{exchange}"
            self.db_update_progress.emit(i, symbol)

            try:
                # --- Daily prices (5 years) ---
                need_daily = True
                daily_start = daily_target_start
                cov = daily_coverage.get(symbol)
                if cov and cov.get("max_date") and cov.get("min_date"):
                    cov_min = date.fromisoformat(cov["min_date"])
                    cov_max = date.fromisoformat(cov["max_date"])
                    start_ok = cov_min <= daily_target_start + timedelta(days=5)
                    end_ok = (today - cov_max).days <= 1
                    if start_ok and end_ok:
                        need_daily = False
                    elif start_ok:
                        # Only fetch the gap at the end
                        daily_start = cov_max
                    # else: fetch full range

                if need_daily:
                    self.data_manager.get_daily_prices(
                        ticker, exchange, daily_start, today,
                    )

                # --- Intraday prices (last month, 5-min bars) ---
                need_intraday = True
                intraday_start = intraday_target_start
                icov = intraday_coverage.get(symbol)
                if icov and icov.get("max_timestamp") and icov.get("min_timestamp"):
                    icov_max = datetime.fromisoformat(icov["max_timestamp"])
                    month_ago = datetime.combine(today - timedelta(days=30), datetime.min.time())
                    start_ok = icov_max >= month_ago  # has data within the window
                    # Compare by date to handle weekends/non-trading hours
                    # (last trading day data may be >24h ago)
                    end_ok = (today - icov_max.date()).days <= 1
                    if start_ok and end_ok:
                        need_intraday = False
                    elif start_ok:
                        intraday_start = icov_max

                if need_intraday:
                    self.data_manager.get_intraday_prices(
                        ticker, exchange, "5m",
                        intraday_start, intraday_target_end,
                    )

                # --- Fundamentals (re-fetch after cache invalidation) ---
                self.data_manager.get_fundamentals(ticker, exchange)

                if not need_daily and not need_intraday:
                    skipped += 1
                else:
                    success += 1
            except Exception as e:
                logger.warning(f"Failed to update {symbol}: {e}")
                failed += 1

        # --- Update FX rates for ALL supported non-USD currencies ---
        if not (worker and worker.is_cancelled):
            self.db_update_progress.emit(len(stocks) - 1, "FX rates...")
            try:
                # All non-USD currencies from the exchange mapping
                all_currencies = sorted({
                    "EUR", "GBp", "HKD", "CAD", "KRW", "INR",
                    "CNY", "JPY", "CHF", "AUD", "BRL", "CLP",
                    "TWD", "SGD", "IDR", "ILS", "PLN", "SEK",
                    "DKK", "NOK",
                })

                if data_server_url:
                    resp = http_requests.post(
                        f"{data_server_url}/api/forex/update",
                        json={"currencies": all_currencies},
                        timeout=300,
                    )
                    if resp.status_code == 200:
                        fx_results = resp.json().get("results", {})
                        for cur, info in fx_results.items():
                            if info.get("stored"):
                                logger.info(f"FX {cur}: {info['stored']} new daily rates")
                            elif info.get("status") == "up_to_date":
                                logger.debug(f"FX {cur}: up to date")
                            elif "error" in info:
                                logger.warning(f"FX {cur}: {info['error']}")
            except Exception as e:
                logger.warning(f"FX rate update failed: {e}")

        return {"success": success, "failed": failed, "skipped": skipped, "total": len(stocks)}

    @Slot(int, str)
    def _on_db_update_progress(self, index: int, symbol: str) -> None:
        """Update progress dialog from main thread."""
        progress = self._db_update_progress
        if progress is None:
            return
        if progress.wasCanceled():
            # Request cancellation on the worker
            from investment_tool.utils.threading import get_thread_manager
            get_thread_manager().cancel("update_database")
            return
        total = progress.maximum()
        progress.setValue(index)
        progress.setLabelText(f"Updating {symbol}... ({index + 1}/{total})")

    def _on_update_database_finished(self, result) -> None:
        """Handle completion of the database update worker."""
        # Disconnect signal and close dialog
        try:
            self.db_update_progress.disconnect(self._on_db_update_progress)
        except RuntimeError:
            pass

        if self._db_update_progress is not None:
            self._db_update_progress.close()
            self._db_update_progress = None

        if result.success:
            data = result.data
            QMessageBox.information(
                self, "Update Database",
                f"Database update complete.\n\n"
                f"  Updated: {data['success']}\n"
                f"  Failed:  {data['failed']}\n"
                f"  Skipped: {data['skipped']}\n"
                f"  Total:   {data['total']}",
            )
        else:
            QMessageBox.warning(
                self, "Update Database",
                f"Database update failed:\n{result.error}",
            )

        # Refresh the display
        self._on_refresh()

    # ------------------------------------------------------------------
    # Update News
    # ------------------------------------------------------------------

    def _on_update_news(self) -> None:
        """Bulk-update news articles for all tracked stocks."""
        if not self.data_manager or not self.data_manager.is_connected():
            QMessageBox.warning(
                self, "Update News",
                "Data server is not connected. Cannot update news.",
            )
            return

        if self._news_update_progress is not None:
            QMessageBox.information(
                self, "Update News",
                "A news update is already running.",
            )
            return

        progress = QProgressDialog(
            "Updating news for all tracked stocks...", None, 0, 0, self,
        )
        progress.setWindowTitle("Update News")
        progress.setMinimumDuration(0)
        progress.setModal(True)
        self._news_update_progress = progress

        from investment_tool.utils.threading import get_thread_manager
        tm = get_thread_manager()
        tm.submit(
            self._update_news_worker,
            on_finished=self._on_update_news_finished,
            worker_id="update_news",
        )

    def _update_news_worker(self) -> dict:
        """Background worker: POST to data server to trigger bulk news update."""
        import os
        import requests as http_requests

        data_server_url = os.getenv("DATA_SERVER_URL", "").rstrip("/")
        if not data_server_url:
            raise RuntimeError("DATA_SERVER_URL is not set")

        resp = http_requests.post(
            f"{data_server_url}/api/news/update",
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json()

    def _on_update_news_finished(self, result) -> None:
        """Handle completion of the news update worker."""
        if self._news_update_progress is not None:
            self._news_update_progress.close()
            self._news_update_progress = None

        if result.success:
            data = result.data
            if data.get("timeout"):
                QMessageBox.warning(
                    self, "Update News",
                    "News update timed out after 5 minutes.\n"
                    f"Stocks checked: {data.get('tickers', 0)}",
                )
            else:
                QMessageBox.information(
                    self, "Update News",
                    f"News update complete.\n\n"
                    f"  Articles: {data.get('total_articles', 0)}\n"
                    f"  Stocks:   {data.get('tickers', 0)}\n"
                    f"  Errors:   {data.get('errors', 0)}",
                )
        else:
            QMessageBox.warning(
                self, "Update News",
                f"News update failed:\n{result.error}",
            )

        # Refresh the display (reloads news feed for currently selected stock)
        self._on_refresh()

    # ------------------------------------------------------------------
    # Update Financials
    # ------------------------------------------------------------------

    def _on_update_financials(self) -> None:
        """Bulk-update quarterly financials for all tracked stocks."""
        if not self.data_manager or not self.data_manager.is_connected():
            QMessageBox.warning(
                self, "Update Financials",
                "Data server is not connected. Cannot update financials.",
            )
            return

        if self._financials_update_progress is not None:
            QMessageBox.information(
                self, "Update Financials",
                "A financials update is already running.",
            )
            return

        progress = QProgressDialog(
            "Updating financials for all tracked stocks...", None, 0, 0, self,
        )
        progress.setWindowTitle("Update Financials")
        progress.setMinimumDuration(0)
        progress.setModal(True)
        self._financials_update_progress = progress

        from investment_tool.utils.threading import get_thread_manager
        tm = get_thread_manager()
        tm.submit(
            self._update_financials_worker,
            on_finished=self._on_update_financials_finished,
            worker_id="update_financials",
        )

    def _update_financials_worker(self) -> dict:
        """Background worker: POST to data server to trigger bulk financials update."""
        import os
        import requests as http_requests

        data_server_url = os.getenv("DATA_SERVER_URL", "").rstrip("/")
        if not data_server_url:
            raise RuntimeError("DATA_SERVER_URL is not set")

        resp = http_requests.post(
            f"{data_server_url}/api/fundamentals/update",
            timeout=600,
        )
        resp.raise_for_status()
        return resp.json()

    def _on_update_financials_finished(self, result) -> None:
        """Handle completion of the financials update worker."""
        if self._financials_update_progress is not None:
            self._financials_update_progress.close()
            self._financials_update_progress = None

        if result.success:
            data = result.data
            yf_filled = data.get('yf_missing_filled', 0)
            yf_overrides = data.get('yf_overrides', 0)
            msg = (
                f"Financials update complete.\n\n"
                f"  Updated:  {data.get('updated', 0)}\n"
                f"  Quarters: {data.get('quarters', 0)}\n"
                f"  Stocks:   {data.get('tickers', 0)}\n"
                f"  Errors:   {data.get('errors', 0)}"
            )
            if yf_filled or yf_overrides:
                msg += (
                    f"\n\n  Yahoo Finance corrections:\n"
                    f"    Missing quarters filled: {yf_filled}\n"
                    f"    Discrepancies overridden: {yf_overrides}"
                )
            QMessageBox.information(self, "Update Financials", msg)
        else:
            QMessageBox.warning(
                self, "Update Financials",
                f"Financials update failed:\n{result.error}",
            )

        # Refresh the display
        self._on_refresh()

    def _on_export(self) -> None:
        """Handle export action."""
        QMessageBox.information(
            self, "Export", "Export functionality coming in a future phase."
        )

    def _on_add_stock(self) -> None:
        """Handle add stock action."""
        # Default category to current treemap filter if it's an industry category
        default_category = None
        market_cap_filters = (
            "All Stocks", "Large Cap (>$200B)", "Mid Cap ($20B-$200B)",
            "Small Cap ($2B-$20B)", "Tiny Stocks (<$2B)",
        )
        selected_filter = self.treemap.get_selected_filter()
        if selected_filter and selected_filter not in market_cap_filters:
            default_category = selected_filter

        dialog = AddStockDialog(self.data_manager, self, default_category=default_category)
        dialog.stock_added.connect(self._on_stock_added)
        dialog.exec()

    def _on_stock_added(self, ticker: str, exchange: str) -> None:
        """Handle stock added event."""
        # Sync to data server so it starts tracking the new stock
        self._sync_stocks_to_server()

        # Reload treemap to show the new stock
        self._load_treemap_data()

        self.status_bar.showMessage(f"Added {ticker}.{exchange}", 3000)

    def _on_manage_categories(self) -> None:
        """Handle manage categories action."""
        dialog = CategoryDialog(self, data_manager=self.data_manager)
        dialog.categories_changed.connect(self._on_categories_changed)
        dialog.exec()

    def _on_categories_changed(self) -> None:
        """Handle categories changed event."""
        # Update category and exchange filters
        all_cats = self.category_manager.get_all_categories()
        categories = [c.name for c in all_cats]
        self.treemap.set_categories(categories)

        # Sync newly added stocks to data server so it can fetch their prices
        self._sync_stocks_to_server()

        # Reload treemap
        self._load_treemap_data()

    def _on_clear_cache(self) -> None:
        """Handle clear cache action."""
        QMessageBox.information(
            self,
            "Clear Cache",
            "Cache is managed by the data server.\n"
            "Local user data (watchlists, settings) is not affected.",
        )

    def _on_open_screener(self) -> None:
        """Handle open screener action."""
        QMessageBox.information(
            self, "Screener", "Stock screener coming in Phase 4."
        )

    def _on_compare_stocks(self) -> None:
        """Handle compare stocks action."""
        QMessageBox.information(
            self, "Compare", "Stock comparison coming in Phase 4."
        )

    def _on_new_backtest(self) -> None:
        """Handle new backtest action."""
        QMessageBox.information(
            self, "Backtest", "Backtesting coming in Phase 5."
        )

    def _on_view_backtest_results(self) -> None:
        """Handle view backtest results action."""
        QMessageBox.information(
            self, "Backtest Results", "Backtest results viewer coming in Phase 5."
        )

    def _on_open_settings(self) -> None:
        """Handle open settings action."""
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self._initialize_data()
            self._update_status()

    def _on_about(self) -> None:
        """Handle about action."""
        QMessageBox.about(
            self,
            "About Investment Tool",
            "<h3>Investment Tracking & Analysis Tool</h3>"
            "<p>Version 0.2.0 (Phase 2)</p>"
            "<p>A local-only desktop application for comprehensive "
            "investment tracking and analysis.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Interactive market treemap</li>"
            "<li>Candlestick charts with indicators</li>"
            "<li>Watchlist management</li>"
            "<li>Category organization</li>"
            "</ul>"
            "<p><b>Coming Soon:</b></p>"
            "<ul>"
            "<li>News & sentiment analysis</li>"
            "<li>Stock screener</li>"
            "<li>RL backtesting</li>"
            "</ul>",
        )

    # --- Control server handlers (called on main thread via signals) ---

    def _on_control_get_state(self):
        """Provide current UI state to the control server."""
        state = {
            "ticker": self._selected_ticker,
            "exchange": self._selected_exchange,
            "period": self.period_combo.currentText(),
            "filter": self.treemap.get_selected_filter(),
        }
        self._control_server.provide_result(state)

    def _on_control_select_stock(self, ticker: str, exchange: str):
        """Handle stock selection from control server."""
        logger.info(f"Control API: selecting {ticker}.{exchange}")
        self._on_stock_selected(ticker, exchange)
        self._control_server.provide_result({
            "status": "ok",
            "ticker": ticker,
            "exchange": exchange,
        })

    def _on_control_set_period(self, period: str):
        """Handle period change from control server."""
        logger.info(f"Control API: setting period to {period}")
        # Setting currentText triggers currentTextChanged → _on_period_changed
        self.period_combo.setCurrentText(period)
        self._control_server.provide_result({
            "status": "ok",
            "period": period,
        })

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        # Stop control server
        if hasattr(self, '_control_server'):
            self._control_server.stop()
            self._control_server.wait(2000)
        event.accept()

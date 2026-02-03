"""Main application window."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict

from PySide6.QtCore import Qt, QTimer, Signal
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
    QMessageBox,
    QGroupBox,
    QFormLayout,
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
from investment_tool.ui.widgets.market_treemap import MarketTreemap, TreemapItem
from investment_tool.ui.widgets.news_feed import NewsFeedWidget
from investment_tool.ui.widgets.sentiment_gauge import SentimentGaugeWidget
from investment_tool.ui.widgets.stock_chart import StockChart
from investment_tool.ui.widgets.watchlist import WatchlistWidget
from investment_tool.utils.helpers import (
    get_date_range,
    format_percent,
    format_large_number,
    is_intraday_period,
    get_last_trading_day_hours,
    is_market_open,
)


class MainWindow(QMainWindow):
    """Main application window."""

    status_updated = Signal(str)

    def __init__(self, config: Optional[AppConfig] = None):
        super().__init__()

        self.config = config or get_config()
        self.data_manager: Optional[DataManager] = None
        self.category_manager = get_category_manager()

        # Current selection state
        self._selected_ticker: Optional[str] = None
        self._selected_exchange: Optional[str] = None
        self._chart_loading: bool = False  # Prevent concurrent chart loads

        self._setup_window()
        self._create_menu_bar()
        self._create_tool_bar()
        self._create_central_widget()
        self._create_status_bar()
        self._setup_timers()

        self._initialize_data()

    def _setup_window(self) -> None:
        """Configure main window properties."""
        self.setWindowTitle("Investment Tracking & Analysis Tool")
        self.setMinimumSize(1200, 800)
        self.resize(1600, 1000)

        self.setStyleSheet(get_stylesheet(self.config.ui.theme))

    def _create_menu_bar(self) -> None:
        """Create the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        refresh_action = QAction("&Refresh Data", self)
        refresh_action.setShortcut(QKeySequence.Refresh)
        refresh_action.triggered.connect(self._on_refresh)
        file_menu.addAction(refresh_action)

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

        # View menu
        view_menu = menubar.addMenu("&View")

        theme_menu = view_menu.addMenu("&Theme")
        dark_theme = QAction("&Dark", self)
        dark_theme.setCheckable(True)
        dark_theme.setChecked(self.config.ui.theme == "dark")
        dark_theme.triggered.connect(lambda: self._set_theme("dark"))
        theme_menu.addAction(dark_theme)

        light_theme = QAction("&Light", self)
        light_theme.setCheckable(True)
        light_theme.setChecked(self.config.ui.theme == "light")
        light_theme.triggered.connect(lambda: self._set_theme("light"))
        theme_menu.addAction(light_theme)

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

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._on_refresh)
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

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Main content splitter
        main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(main_splitter, stretch=1)

        # Left panel - Market Treemap
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.treemap = MarketTreemap()
        self.treemap.stock_selected.connect(self._on_stock_selected)
        self.treemap.stock_double_clicked.connect(self._on_stock_double_clicked)
        self.treemap.filter_changed.connect(self._on_treemap_filter_changed)
        self.treemap.period_changed.connect(self._on_treemap_period_changed)
        self.treemap.stock_remove_requested.connect(self._on_stock_remove_requested)
        self.treemap.stock_add_to_watchlist.connect(self._on_stock_add_to_watchlist)
        left_layout.addWidget(self.treemap)

        main_splitter.addWidget(left_panel)

        # Right panel - Chart and details
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Stock Chart
        self.stock_chart = StockChart()
        # Period is now controlled by treemap, not chart
        right_layout.addWidget(self.stock_chart, stretch=2)

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

        # Column 2: 52W High, Low, Avg Volume
        col2_layout = QFormLayout()
        col2_layout.setSpacing(4)
        self.week52_high_label = QLabel("--")
        col2_layout.addRow("52W High:", self.week52_high_label)
        self.week52_low_label = QLabel("--")
        col2_layout.addRow("52W Low:", self.week52_low_label)
        self.avg_volume_label = QLabel("--")
        col2_layout.addRow("Avg Volume:", self.avg_volume_label)
        metrics_main_layout.addLayout(col2_layout)

        # Column 3: Market Cap & P/E
        col3_layout = QFormLayout()
        col3_layout.setSpacing(4)
        self.market_cap_label = QLabel("--")
        col3_layout.addRow("Market Cap:", self.market_cap_label)
        self.pe_label = QLabel("--")
        col3_layout.addRow("P/E Ratio:", self.pe_label)
        metrics_main_layout.addLayout(col3_layout)

        # Column 4: Day's Data (Open, High, Low)
        col4_layout = QFormLayout()
        col4_layout.setSpacing(4)
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

        main_splitter.addWidget(right_panel)

        # Set splitter sizes
        main_splitter.setSizes([700, 400])

        # Bottom tabs
        self.bottom_tabs = QTabWidget()
        main_layout.addWidget(self.bottom_tabs)

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
        now_et = now_utc - timedelta(hours=5)
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
        """Refresh live prices if 1D period is selected and market is open."""
        from investment_tool.utils.helpers import is_market_open

        if not self.data_manager:
            return

        # Check if 1D period is selected
        period = self.treemap.get_selected_period()
        if period != "1D":
            return

        # Skip refresh when market is closed to avoid unnecessary API calls
        if not is_market_open("US"):
            logger.info("Market closed, skipping live price refresh")
            return

        logger.info("Auto-refreshing live prices (every 15s)")
        # Reload treemap with live prices
        self._load_treemap_data()
        # Show last update time in status bar
        now = datetime.now().strftime("%H:%M:%S")
        self.status_bar.showMessage(f"Live prices updated at {now}", 10000)

        # Also refresh the selected stock's chart and metrics if one is selected
        if self._selected_ticker and self._selected_exchange:
            self._load_stock_chart(self._selected_ticker, self._selected_exchange)
            self._update_metrics(self._selected_ticker, self._selected_exchange)

    def _initialize_data(self) -> None:
        """Initialize data manager and load initial data."""
        try:
            self.data_manager = get_data_manager()
            self._update_status()

            # Set data_manager on widgets
            self.watchlist_widget.set_data_manager(self.data_manager)
            self.sentiment_gauge.set_data_manager(self.data_manager)
            self.news_feed.set_data_manager(self.data_manager)

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

                # Load treemap with default category
                self._load_treemap_data()

                # Set period and refresh watchlist with current data
                period = self.treemap.get_selected_period()
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
        selected_period = self.treemap.get_selected_period()

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
        for category in all_categories:
            if selected_filter not in market_cap_filters and category.name != selected_filter:
                continue
            for stock_ref in category.stocks[:30]:
                ticker_key = f"{stock_ref.ticker}.{stock_ref.exchange}"
                if selected_filter in market_cap_filters:
                    if ticker_key in seen_tickers:
                        continue
                    seen_tickers.add(ticker_key)
                stock_refs_by_symbol[ticker_key] = (stock_ref, category)

        # Use live prices for 1D, batch API for other periods
        batch_changes = {}
        if stock_refs_by_symbol:
            symbols = list(stock_refs_by_symbol.keys())

            if selected_period == "1D":
                # Use live prices from data server for 1D
                live_prices = self.data_manager.get_all_live_prices()
                if live_prices:
                    for symbol in symbols:
                        if symbol in live_prices:
                            lp = live_prices[symbol]
                            # change_percent from EODHD is in % format (e.g., 0.1977 = 0.1977%)
                            # Treemap expects decimal (e.g., 0.001977 for 0.1977%)
                            change_pct = lp.get("change_percent")
                            if change_pct is not None:
                                batch_changes[symbol] = {
                                    "end_price": lp.get("price"),
                                    "change": change_pct / 100,  # Convert from % to decimal
                                }
                    logger.info(f"Live prices returned {len(batch_changes)}/{len(symbols)} for period=1D")
                    # Show today's date in status bar
                    today_str = date.today().strftime("%b %d, %Y")
                    self.status_bar.showMessage(f"Showing live prices for {today_str}", 5000)

            # Fallback to batch API if no live prices or not 1D
            if not batch_changes:
                batch_changes = self.data_manager.get_batch_daily_changes(
                    symbols,
                    start.date() if hasattr(start, 'date') else start,
                    end.date() if hasattr(end, 'date') else end,
                )
                logger.info(f"Batch API returned {len(batch_changes)}/{len(symbols)} price changes for period={selected_period}")

        # Second pass: build treemap items using batch results
        for ticker_key, (stock_ref, category) in stock_refs_by_symbol.items():
            try:
                if ticker_key in batch_changes:
                    price_data = batch_changes[ticker_key]
                    current = price_data.get("end_price")
                    change = price_data.get("change", 0)
                    if current is None:
                        continue
                else:
                    # Fallback: fetch individually (shouldn't happen often)
                    prices = self.data_manager.get_daily_prices(
                        stock_ref.ticker, stock_ref.exchange, start, end
                    )
                    if prices is None or len(prices) < 1:
                        continue
                    current = prices["close"].iloc[-1]
                    if len(prices) >= 2:
                        prev = prices["close"].iloc[0]
                        change = (current - prev) / prev if prev != 0 else 0
                    else:
                        change = 0

                # Get company info for market cap and P/E
                company = self.data_manager.get_company_info(
                    stock_ref.ticker, stock_ref.exchange
                )

                market_cap = company.market_cap if company else 1e9
                pe_ratio = company.pe_ratio if company else None

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
                    name=company.name if company else stock_ref.ticker,
                    exchange=stock_ref.exchange,
                    value=market_cap or 1e9,
                    change_percent=change,
                    sector=category.name,
                    price=current,
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

    def _on_stock_selected(self, ticker: str, exchange: str) -> None:
        """Handle stock selection."""
        import time
        total_start = time.perf_counter()

        self._selected_ticker = ticker
        self._selected_exchange = exchange

        logger.info(f"Stock selected: {ticker}.{exchange}")

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
                    ticker, limit=100, from_date=start_date, to_date=end_date
                )
                logger.info(f"[TIMING] News fetch: {(time.perf_counter() - t0)*1000:.0f}ms ({len(result) if result else 0} articles)")
                return result

            # Run news fetch in parallel with chart/metrics (which share some data)
            with ThreadPoolExecutor(max_workers=2) as executor:
                news_future = executor.submit(fetch_news)

                # Load chart and metrics on main thread (they update UI)
                t1 = time.perf_counter()
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

        logger.info(f"[TIMING] TOTAL _on_stock_selected: {(time.perf_counter() - total_start)*1000:.0f}ms")

    def _on_stock_double_clicked(self, ticker: str, exchange: str) -> None:
        """Handle stock double-click (open in new window)."""
        logger.info(f"Stock double-clicked: {ticker}.{exchange}")
        # For now, just select and show in main view
        self._on_stock_selected(ticker, exchange)

    def _on_treemap_filter_changed(self, filter_text: str) -> None:
        """Handle treemap category filter change."""
        logger.info(f"Treemap filter changed: {filter_text}")
        self._load_treemap_data()

    def _on_treemap_period_changed(self, period: str) -> None:
        """Handle treemap period change - updates all views."""
        logger.info(f"Period changed: {period}")

        # Update stock chart period
        self.stock_chart.set_period(period)

        # Reload treemap data
        self._load_treemap_data()

        # Reload stock chart if a stock is selected
        if self._selected_ticker and self._selected_exchange:
            self._load_stock_chart(self._selected_ticker, self._selected_exchange)
            self._update_metrics(self._selected_ticker, self._selected_exchange)

        # Set period and refresh watchlist data
        self.watchlist_widget.set_period(period)
        self.watchlist_widget.refresh_all()

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
                # For 1D: show full trading day (9:30 AM - 4:00 PM ET)
                now_utc = datetime.utcnow()

                # Convert UTC to Eastern Time (EST = UTC-5, simplified - no DST handling)
                # TODO: Use zoneinfo for proper DST handling
                now_et = now_utc - timedelta(hours=5)
                current_time_et = now_et.time()
                current_date_et = now_et.date()

                # Market hours in ET
                from datetime import time as dt_time
                market_open_et = dt_time(9, 30)
                market_close_et = dt_time(16, 0)

                # Determine trading date based on ET time
                if current_time_et < market_open_et:
                    # Before market open in ET - show previous trading day
                    trading_date = current_date_et - timedelta(days=1)
                else:
                    # During or after market hours - show today's trading data
                    trading_date = current_date_et

                # Skip weekends (Saturday=5, Sunday=6)
                while trading_date.weekday() >= 5:
                    trading_date = trading_date - timedelta(days=1)

                logger.info(f"ET time: {now_et.strftime('%Y-%m-%d %H:%M')} ET, trading_date: {trading_date}")

                prices = None

                # Trading day in UTC: 9:30 AM - 4:00 PM ET = 14:30 - 21:00 UTC
                market_open_utc = datetime(trading_date.year, trading_date.month, trading_date.day, 14, 30)
                market_close_utc = datetime(trading_date.year, trading_date.month, trading_date.day, 21, 0)

                # Check if market is currently open (using ET time)
                is_weekday = current_date_et.weekday() < 5
                market_is_open = is_weekday and market_open_et <= current_time_et <= market_close_et and trading_date == current_date_et

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

                    for days_back in range(5):  # Try up to 5 trading days back
                        check_date = trading_date - timedelta(days=days_back)
                        # Skip weekends
                        while check_date.weekday() >= 5:
                            check_date = check_date - timedelta(days=1)

                        day_open = datetime(check_date.year, check_date.month, check_date.day, 14, 30)
                        day_close = datetime(check_date.year, check_date.month, check_date.day, 21, 0)

                        logger.info(f"Checking EODHD intraday for {ticker} on {check_date}")
                        try:
                            raw_prices = self.data_manager.get_intraday_prices(
                                ticker, exchange, "1m",
                                day_open.replace(tzinfo=timezone.utc),
                                day_close.replace(tzinfo=timezone.utc),
                                use_cache=True,
                                force_refresh=True,  # Only use EODHD data
                            )
                        except Exception as e:
                            logger.warning(f"Failed to get EODHD intraday for {check_date}: {e}")
                            raw_prices = None

                        if raw_prices is not None and not raw_prices.empty:
                            display_date = check_date
                            market_open_utc = day_open
                            market_close_utc = day_close
                            # Update full day index for this date
                            full_day_index = pd.date_range(
                                start=market_open_utc,
                                end=market_close_utc,
                                freq="1min"
                            )
                            logger.info(f"Found EODHD data for {check_date} ({len(raw_prices)} records)")
                            break

                        # Move to previous trading day
                        trading_date = check_date - timedelta(days=1)

                    if raw_prices is not None and not raw_prices.empty:
                        if "timestamp" in raw_prices.columns:
                            raw_prices = raw_prices.set_index("timestamp")
                        prices = raw_prices
                        if "volume" in prices.columns:
                            prices["volume"] = prices["volume"].fillna(0)
                        if display_date != current_date_et:
                            self.status_bar.showMessage(
                                f"Showing {display_date.strftime('%b %d')} - latest EODHD data available", 5000
                            )
                    else:
                        # No EODHD intraday data found - should not happen normally
                        logger.warning(f"No EODHD intraday data found for {ticker} in last 5 trading days")
                        prices = None
                else:
                    # Market open - use real-time snapshots from data server
                    try:
                        raw_prices = self.data_manager.get_intraday_prices(
                            ticker, exchange, "1m",
                            market_open_utc.replace(tzinfo=timezone.utc),
                            market_close_utc.replace(tzinfo=timezone.utc),
                            use_cache=True
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

                        # Add live price as current data point
                        if live_price_data and live_price_data.get("price"):
                            live_row = pd.DataFrame({
                                "open": [live_price_data.get("price")],
                                "high": [live_price_data.get("price")],
                                "low": [live_price_data.get("price")],
                                "close": [live_price_data.get("price")],
                                "volume": [live_price_data.get("volume") or 0],
                            }, index=[pd.Timestamp(now_utc)])
                            raw_prices = pd.concat([raw_prices, live_row])

                        num_points = len(raw_prices)
                        logger.info(f"Got {num_points} intraday records for {ticker} today")

                        # Reindex to full trading day
                        prices = raw_prices.reindex(full_day_index)

                        # Forward-fill values only up to current time
                        current_minute = pd.Timestamp(now_utc).floor("min")
                        mask_past = prices.index <= current_minute
                        prices.loc[mask_past] = prices.loc[mask_past].ffill()

                        # Fill volume NaN with 0 for filled periods
                        if "volume" in prices.columns:
                            prices["volume"] = prices["volume"].fillna(0)

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
                        # No live data - fallback to daily data
                        logger.info(f"No live data for {ticker}, falling back to daily")
                        start = trading_date - timedelta(days=7)
                        end = trading_date
                        prices = self.data_manager.get_daily_prices(ticker, exchange, start, end)
                        if prices is not None and "volume" in prices.columns:
                            prices["volume"] = prices["volume"].fillna(0)
                        self.status_bar.showMessage(f"Showing daily data for {ticker}", 5000)
            elif period == "1W":
                # Fetch intraday data for each trading day separately (EODHD limitation)
                # This gives ~130 data points (5 days * 26 fifteen-min periods)
                all_prices = []

                # Use ET date for consistency with US market
                now_utc = datetime.utcnow()
                now_et = now_utc - timedelta(hours=5)  # EST = UTC-5
                today_et = now_et.date()

                # Get last 7 calendar days, fetch each trading day
                for days_ago in range(7, -1, -1):
                    check_date = today_et - timedelta(days=days_ago)
                    # Skip weekends
                    if check_date.weekday() >= 5:
                        continue

                    # Market hours: 9:30 AM - 4:00 PM ET = 14:30 - 21:00 UTC
                    day_start = datetime(check_date.year, check_date.month, check_date.day, 14, 30, tzinfo=timezone.utc)
                    day_end = datetime(check_date.year, check_date.month, check_date.day, 21, 0, tzinfo=timezone.utc)

                    day_prices = self.data_manager.get_intraday_prices(
                        ticker, exchange, "5m", day_start, day_end, use_cache=True,
                        force_refresh=True  # Only use EODHD data, not price worker cache
                    )
                    if day_prices is not None and not day_prices.empty:
                        all_prices.append(day_prices)

                if all_prices:
                    prices = pd.concat(all_prices, ignore_index=True)
                    if "timestamp" in prices.columns:
                        prices = prices.set_index("timestamp")
                    prices = prices.sort_index()
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

            if prices is not None and not prices.empty:
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
                # For 1D: use live prices from data server
                symbol = f"{ticker}.{exchange}"
                live_prices = self.data_manager.get_all_live_prices()
                live_data = live_prices.get(symbol) if live_prices else None

                if live_data and live_data.get("price"):
                    # Use live data
                    current = live_data.get("price")
                    prev_close = live_data.get("previous_close")
                    change = live_data.get("change", 0)
                    change_pct = (live_data.get("change_percent") or 0) / 100  # Convert from % to decimal
                    total_volume = live_data.get("volume", 0)
                    day_open = live_data.get("open")
                    day_high = live_data.get("high")
                    day_low = live_data.get("low")
                    logger.debug(f"Using live data for {ticker}: ${current:.2f} ({change_pct*100:.2f}%)")
                else:
                    # Fallback to daily prices - use previous trading day's data
                    prev_close = None
                    if period_prices is not None and len(period_prices) >= 2:
                        prev_close = period_prices["close"].iloc[-2]

                    if period_prices is not None and len(period_prices) >= 1:
                        # Use last available day's data
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

            if current is not None:
                self.price_label.setText(f"${current:.2f}")

                change_color = "#22C55E" if change >= 0 else "#EF4444"
                sign = "+" if change >= 0 else ""
                self.change_label.setText(
                    f"<span style='color: {change_color};'>"
                    f"{sign}${change:.2f} ({format_percent(change_pct)})</span>"
                )
                self.change_label.setTextFormat(Qt.RichText)

            # Update day's data (Open, High, Low) - only for intraday periods
            if is_intraday_period(period):
                self.day_open_label.setText(f"${day_open:.2f}" if day_open is not None else "--")
                self.day_high_label.setText(f"${day_high:.2f}" if day_high is not None else "--")
                self.day_low_label.setText(f"${day_low:.2f}" if day_low is not None else "--")
            else:
                # Clear day data for non-intraday periods (52W High/Low is more relevant)
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
                self.week52_high_label.setText(f"${week52_high:.2f}")
                self.week52_low_label.setText(f"${week52_low:.2f}")
            else:
                self.week52_high_label.setText("--")
                self.week52_low_label.setText("--")

            # Calculate average volume - reuse period_prices from above
            if period_prices is not None and len(period_prices) >= 1:
                avg_volume = period_prices["volume"].mean()
                self.avg_volume_label.setText(format_large_number(avg_volume))
            else:
                self.avg_volume_label.setText("--")

            if company:
                # Update metrics group title with company name
                company_name = company.name if company.name else ticker
                self.metrics_group.setTitle(f"Key Metrics - {company_name}")

                self.market_cap_label.setText(
                    format_large_number(company.market_cap) if company.market_cap else "--"
                )
                # Display P/E ratio
                if company.pe_ratio is not None:
                    self.pe_label.setText(f"{company.pe_ratio:.2f}")
                else:
                    self.pe_label.setText("--")
            else:
                self.metrics_group.setTitle(f"Key Metrics - {ticker}")
                self.market_cap_label.setText("--")
                self.pe_label.setText("--")

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

    def _set_theme(self, theme: str) -> None:
        """Change application theme."""
        self.config.ui.theme = theme
        self.setStyleSheet(get_stylesheet(theme))

    def _on_refresh(self) -> None:
        """Handle refresh action."""
        logger.info("Manual refresh triggered")
        self._load_treemap_data()

        if self._selected_ticker and self._selected_exchange:
            self._load_stock_chart(self._selected_ticker, self._selected_exchange)
            self._update_metrics(self._selected_ticker, self._selected_exchange)

        self._update_status()
        self.status_bar.showMessage("Data refreshed", 3000)

    def _on_export(self) -> None:
        """Handle export action."""
        QMessageBox.information(
            self, "Export", "Export functionality coming in a future phase."
        )

    def _on_add_stock(self) -> None:
        """Handle add stock action."""
        dialog = AddStockDialog(self.data_manager, self)
        dialog.stock_added.connect(self._on_stock_added)
        dialog.exec()

    def _on_stock_added(self, ticker: str, exchange: str) -> None:
        """Handle stock added event."""
        # Reload treemap to show the new stock
        self._load_treemap_data()

        self.status_bar.showMessage(f"Added {ticker}.{exchange}", 3000)

    def _on_manage_categories(self) -> None:
        """Handle manage categories action."""
        dialog = CategoryDialog(self)
        dialog.categories_changed.connect(self._on_categories_changed)
        dialog.exec()

    def _on_categories_changed(self) -> None:
        """Handle categories changed event."""
        # Update category filter
        categories = [c.name for c in self.category_manager.get_all_categories()]
        self.treemap.set_categories(categories)

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

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        event.accept()

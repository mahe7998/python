"""Main application window."""

from datetime import datetime, date, timedelta, timezone
from typing import Optional, List

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
from investment_tool.ui.widgets.stock_chart import StockChart
from investment_tool.ui.widgets.watchlist import WatchlistWidget
from investment_tool.utils.helpers import (
    get_date_range,
    format_percent,
    format_large_number,
    is_intraday_period,
    get_last_trading_day_hours,
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

        metrics_main_layout.addStretch()
        right_layout.addWidget(self.metrics_group)

        # Sentiment placeholder
        sentiment_group = QGroupBox("Sentiment")
        sentiment_layout = QVBoxLayout(sentiment_group)
        self.sentiment_label = QLabel("Sentiment analysis coming in Phase 3")
        self.sentiment_label.setAlignment(Qt.AlignCenter)
        self.sentiment_label.setStyleSheet("color: #9CA3AF;")
        sentiment_layout.addWidget(self.sentiment_label)
        right_layout.addWidget(sentiment_group)

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
        self.bottom_tabs.addTab(self.watchlist_widget, "Watchlist")

        # News tab (placeholder)
        news_tab = QWidget()
        news_layout = QVBoxLayout(news_tab)
        news_label = QLabel("News Feed\n(Coming in Phase 3)")
        news_label.setAlignment(Qt.AlignCenter)
        news_label.setStyleSheet("color: #9CA3AF;")
        news_layout.addWidget(news_label)
        self.bottom_tabs.addTab(news_tab, "News Feed")

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

        # Intraday refresh timer (30 seconds for real-time updates)
        self.intraday_timer = QTimer(self)
        self.intraday_timer.timeout.connect(self._refresh_intraday)
        self.intraday_timer.start(30000)  # 30 seconds

    def _refresh_intraday(self) -> None:
        """Refresh intraday data if 1D period is selected."""
        if not self._selected_ticker or not self.data_manager:
            return

        period = self.stock_chart.get_period()
        if is_intraday_period(period):
            logger.info(f"Auto-refreshing intraday data for {self._selected_ticker}")
            self._load_stock_chart(self._selected_ticker, self._selected_exchange)

    def _initialize_data(self) -> None:
        """Initialize data manager and load initial data."""
        try:
            self.data_manager = get_data_manager()
            self._update_status()

            # Set data_manager first, then cache (cache triggers refresh which needs data_manager)
            self.watchlist_widget.set_data_manager(self.data_manager)
            self.watchlist_widget.set_cache(self.data_manager.cache)

            if self.data_manager.is_connected():
                self.connection_label.setText(f"EODHD: Connected | API Calls: {self.data_manager.api_call_count}")
                self.connection_label.setStyleSheet("color: #22C55E;")

                # Load treemap with default category
                self._load_treemap_data()

                # Set period and refresh watchlist with current data
                period = self.treemap.get_selected_period()
                self.watchlist_widget.set_period(period)
                self.watchlist_widget.refresh_all()
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

    def _load_treemap_data(self) -> None:
        """Load data for the market treemap."""
        if not self.data_manager or not self.data_manager.is_connected():
            return

        # Ensure trading_days table is populated for all exchanges
        cache = self.data_manager.cache
        if cache.get_trading_day_count("US") == 0:
            logger.info("Populating trading_days table from existing price data...")
            cache.update_trading_days_from_prices()  # Populate all exchanges
            logger.info(f"Trading days populated")

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

        # For longer periods (1M+), only fetch start and end dates to save API calls
        is_long_period = selected_period in ("1M", "3M", "6M", "1Y", "2Y", "YTD", "5Y")

        # Get stocks from categories, avoiding duplicates
        items: List[TreemapItem] = []
        seen_tickers: set = set()

        # Market cap filters that should include all categories
        market_cap_filters = ("All Stocks", "Large Cap (>$200B)", "Mid Cap ($20B-$200B)", "Small Cap ($2B-$20B)", "Tiny Stocks (<$2B)")

        all_categories = self.category_manager.get_all_categories()
        logger.info(f"Found {len(all_categories)} categories")
        for category in all_categories:
            # Skip if category doesn't match filter (unless it's All Stocks or a market cap filter)
            if selected_filter not in market_cap_filters and category.name != selected_filter:
                continue
            for stock_ref in category.stocks[:30]:  # Limit for performance
                ticker_key = f"{stock_ref.ticker}.{stock_ref.exchange}"
                # Only skip duplicates for "All Stocks" and market cap filters
                if selected_filter in market_cap_filters:
                    if ticker_key in seen_tickers:
                        continue
                    seen_tickers.add(ticker_key)

                try:
                    if is_long_period:
                        # Get exact trading days for this stock's exchange
                        exch = stock_ref.exchange
                        start_trading_day = cache.get_nearest_trading_day(exch, start, "after")
                        end_trading_day = cache.get_nearest_trading_day(exch, end, "before")

                        # For long periods, use exact trading days if known
                        if end_trading_day:
                            end_prices = self.data_manager.get_daily_prices(
                                stock_ref.ticker, exch, end_trading_day, end_trading_day
                            )
                        else:
                            end_prices = self.data_manager.get_daily_prices(
                                stock_ref.ticker, exch, end - timedelta(days=3), end
                            )

                        if end_prices is None or len(end_prices) < 1:
                            continue  # No current price, skip this stock

                        current = end_prices["close"].iloc[-1]

                        # Try to get start price using exact trading day if known
                        if start_trading_day:
                            start_prices = self.data_manager.get_daily_prices(
                                stock_ref.ticker, exch, start_trading_day, start_trading_day
                            )
                        else:
                            start_prices = self.data_manager.get_daily_prices(
                                stock_ref.ticker, exch, start, start + timedelta(days=5)
                            )

                        if start_prices is not None and len(start_prices) >= 1:
                            prev = start_prices["close"].iloc[0]
                            change = (current - prev) / prev if prev != 0 else 0
                        else:
                            change = 0  # No historical data, show with 0 change
                    else:
                        # For short periods, fetch all data
                        prices = self.data_manager.get_daily_prices(
                            stock_ref.ticker, stock_ref.exchange, start, end
                        )

                        if prices is not None and len(prices) >= 2:
                            current = prices["close"].iloc[-1]
                            # For 1D, compare to previous day; for other periods, compare to first day
                            if selected_period == "1D":
                                prev = prices["close"].iloc[-2]
                            else:
                                prev = prices["close"].iloc[0]
                            change = (current - prev) / prev if prev != 0 else 0
                        elif prices is not None and len(prices) == 1:
                            current = prices["close"].iloc[-1]
                            change = 0  # No comparison available
                        else:
                            continue  # No price data, skip this stock

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
        self._selected_ticker = ticker
        self._selected_exchange = exchange

        logger.info(f"Stock selected: {ticker}.{exchange}")

        # Load chart data
        self._load_stock_chart(ticker, exchange)

        # Update metrics
        self._update_metrics(ticker, exchange)

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

    def _load_stock_chart(self, ticker: str, exchange: str) -> None:
        """Load chart data for a stock."""
        if not self.data_manager:
            return

        period = self.stock_chart.get_period()

        try:
            if is_intraday_period(period):
                # Use intraday data for 1D - get market hours for the trading day
                market_open, market_close = get_last_trading_day_hours(exchange)
                now_utc = datetime.now(timezone.utc)

                # If market is currently open, extend to now for real-time data
                # Otherwise show full trading session (open to close)
                if market_open.date() == now_utc.date() and market_open <= now_utc <= market_close:
                    # Market is open today - show up to current time
                    end_dt = now_utc
                else:
                    # Market closed - show full session
                    end_dt = market_close

                start_dt = market_open
                logger.info(f"Fetching intraday data for {ticker} ({market_open.date()}) from {start_dt} to {end_dt}")
                prices = self.data_manager.get_intraday_prices(
                    ticker, exchange, "1m", start_dt, end_dt, use_cache=True  # Use 1-minute intervals and cache
                )
                # Normalize column names for the chart
                if prices is not None and not prices.empty:
                    if "timestamp" in prices.columns:
                        prices = prices.set_index("timestamp")
                    # Fill NA values in volume with 0
                    if "volume" in prices.columns:
                        prices["volume"] = prices["volume"].fillna(0)
                    logger.info(f"Got {len(prices)} 1-minute records for {ticker}")
                else:
                    # Fallback to daily data for last 5 days if no intraday available
                    logger.info(f"No intraday data for {ticker}, falling back to daily data")
                    start = date.today() - timedelta(days=5)
                    end = date.today()
                    prices = self.data_manager.get_daily_prices(ticker, exchange, start, end)
                    if prices is not None and "volume" in prices.columns:
                        prices["volume"] = prices["volume"].fillna(0)
            elif period == "1W":
                # Use intraday data aggregated to hourly for 1 week view
                end_dt = datetime.now(timezone.utc)
                start_dt = end_dt - timedelta(days=7)

                logger.info(f"Fetching 1W intraday data for {ticker} from {start_dt} to {end_dt}")
                # Force refresh to get all days but still cache for next time
                prices = self.data_manager.get_intraday_prices(
                    ticker, exchange, "5m", start_dt, end_dt, use_cache=True, force_refresh=True
                )

                if prices is not None and not prices.empty:
                    if "timestamp" in prices.columns:
                        prices = prices.set_index("timestamp")
                    # Resample to hourly OHLC
                    prices = prices.resample("1h").agg({
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum"
                    }).dropna()
                    if "volume" in prices.columns:
                        prices["volume"] = prices["volume"].fillna(0)
                    logger.info(f"Got {len(prices)} hourly records for {ticker}")
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

            if prices is not None and not prices.empty:
                self.stock_chart.set_data(prices, ticker, exchange)
            else:
                self.stock_chart.clear()
                self.status_bar.showMessage(f"No data available for {ticker}", 3000)

        except Exception as e:
            logger.error(f"Failed to load chart for {ticker}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stock_chart.clear()

    def _update_metrics(self, ticker: str, exchange: str) -> None:
        """Update the metrics panel for a stock."""
        if not self.data_manager:
            return

        try:
            # Get company info
            company = self.data_manager.get_company_info(ticker, exchange)

            # Get period from chart
            period = self.stock_chart.get_period()

            if is_intraday_period(period):
                # For 1D: use intraday for current price, daily for prev close
                start, end = get_date_range(period, min_trading_days=0)
                daily_prices = self.data_manager.get_daily_prices(ticker, exchange, start, end)

                prev_close = None
                if daily_prices is not None and len(daily_prices) >= 2:
                    prev_close = daily_prices["close"].iloc[-2]

                # Get intraday for current price
                market_open, market_close = get_last_trading_day_hours(exchange)
                now_utc = datetime.now(timezone.utc)
                end_dt = now_utc if (market_open.date() == now_utc.date() and market_open <= now_utc <= market_close) else market_close

                intraday = self.data_manager.get_intraday_prices(ticker, exchange, "5m", market_open, end_dt, use_cache=True)

                if intraday is not None and len(intraday) >= 1:
                    current = intraday["close"].iloc[-1]
                    total_volume = intraday["volume"].sum() if "volume" in intraday.columns else 0
                elif daily_prices is not None and len(daily_prices) >= 1:
                    current = daily_prices["close"].iloc[-1]
                    total_volume = daily_prices["volume"].iloc[-1]
                else:
                    current = None
                    total_volume = 0

                if current is not None and prev_close is not None:
                    change = current - prev_close
                    change_pct = change / prev_close if prev_close != 0 else 0
                else:
                    change = 0
                    change_pct = 0
            else:
                # For other periods: compare start to end
                start, end = get_date_range(period, min_trading_days=0)
                prices = self.data_manager.get_daily_prices(ticker, exchange, start, end)

                if prices is not None and len(prices) >= 1:
                    current = prices["close"].iloc[-1]
                    first = prices["close"].iloc[0]
                    change = current - first
                    change_pct = change / first if first != 0 else 0
                    total_volume = prices["volume"].sum()
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

            # Get 52-week data for high/low and average volume
            week52_start = date.today() - timedelta(days=365)
            week52_end = date.today()
            week52_prices = self.data_manager.get_daily_prices(ticker, exchange, week52_start, week52_end)

            if week52_prices is not None and len(week52_prices) >= 1:
                week52_high = week52_prices["high"].max()
                week52_low = week52_prices["low"].min()
                avg_volume = week52_prices["volume"].mean()

                self.week52_high_label.setText(f"${week52_high:.2f}")
                self.week52_low_label.setText(f"${week52_low:.2f}")
                self.avg_volume_label.setText(format_large_number(avg_volume))
            else:
                self.week52_high_label.setText("--")
                self.week52_low_label.setText("--")
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
            stats = self.data_manager.get_cache_stats()
            self.cache_label.setText(f"Cache: {stats['size_mb']} MB")

            if self.data_manager.is_connected():
                self.connection_label.setText(f"EODHD: Connected | API Calls: {self.data_manager.api_call_count}")

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
        # Add to watchlist if option was checked
        self.watchlist_widget.add_stock(ticker, exchange)

        # Reload treemap
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
        result = QMessageBox.question(
            self,
            "Clear Cache",
            "Are you sure you want to clear the cache?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if result == QMessageBox.Yes and self.data_manager:
            deleted = self.data_manager.cache.clear_old_cache(days=0)
            self.status_bar.showMessage(f"Cleared {deleted} cache entries", 3000)
            self._update_status()

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
        if self.data_manager:
            self.data_manager.cache.close()
        event.accept()

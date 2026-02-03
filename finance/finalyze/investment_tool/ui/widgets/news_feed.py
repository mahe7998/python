"""News feed widget for displaying and filtering news articles."""

import webbrowser
from datetime import date, datetime, timedelta
from typing import Optional, List

from PySide6.QtCore import Qt, Signal, QTimer, QPoint
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QScrollArea,
    QFrame,
    QSizePolicy,
    QApplication,
)

from investment_tool.data.manager import DataManager
from investment_tool.data.models import NewsArticle


class SummaryPopup(QFrame):
    """Floating popup window to display article summary."""

    _instance: Optional["SummaryPopup"] = None

    # Maximum dimensions for the popup
    MAX_WIDTH = 500
    MAX_HEIGHT = 400

    @classmethod
    def instance(cls) -> "SummaryPopup":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = SummaryPopup()
        return cls._instance

    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet("""
            SummaryPopup {
                background-color: #1F2937;
                border: 1px solid #4B5563;
                border-radius: 6px;
            }
        """)
        self.setMaximumWidth(self.MAX_WIDTH)
        self.setMaximumHeight(self.MAX_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Title (outside scroll area for visibility)
        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("color: #F9FAFB; font-weight: bold; font-size: 11px;")
        self.title_label.setMaximumWidth(self.MAX_WIDTH - 20)
        layout.addWidget(self.title_label)

        # Scroll area for summary content
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1F2937;
            }
            QScrollArea > QWidget > QWidget {
                background-color: #1F2937;
            }
            QScrollBar:vertical {
                background-color: #374151;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #6B7280;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Summary label inside scroll area
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color: #D1D5DB; font-size: 10px; background-color: #1F2937;")
        self.summary_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.summary_label.setTextFormat(Qt.PlainText)
        self.scroll_area.setWidget(self.summary_label)
        layout.addWidget(self.scroll_area, stretch=1)

        # Source and time
        self.meta_label = QLabel()
        self.meta_label.setStyleSheet("color: #9CA3AF; font-size: 9px;")
        layout.addWidget(self.meta_label)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

        # Track if mouse is over the popup
        self.setMouseTracking(True)

    def enterEvent(self, event) -> None:
        """Cancel hide when mouse enters popup."""
        self.hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Schedule hide when mouse leaves popup."""
        self.schedule_hide(300)
        super().leaveEvent(event)

    def show_for_article(self, article: NewsArticle, pos: QPoint) -> None:
        """Show popup with article info at position."""
        self.hide_timer.stop()

        self.title_label.setText(article.title)
        summary = article.summary if article.summary else "No summary available."
        self.summary_label.setText(summary)
        self.meta_label.setText(f"{article.source} - {article.published_at.strftime('%Y-%m-%d %H:%M')}")

        # Calculate ideal size based on content
        # Title and meta have fixed heights, summary is scrollable
        title_height = self.title_label.sizeHint().height()
        meta_height = self.meta_label.sizeHint().height()
        margins = 16 + 12  # layout margins + spacing

        # Calculate summary height needed (capped at max scroll height)
        summary_ideal_height = self.summary_label.sizeHint().height()
        max_scroll_height = self.MAX_HEIGHT - title_height - meta_height - margins - 20
        scroll_height = min(summary_ideal_height + 10, max_scroll_height)

        # Set scroll area to appropriate size
        self.scroll_area.setMinimumHeight(min(scroll_height, 50))  # At least 50px
        self.scroll_area.setMaximumHeight(max_scroll_height)

        self.adjustSize()

        # Position popup near the cursor but ensure it stays on screen
        screen = QApplication.screenAt(pos)
        if screen:
            screen_rect = screen.availableGeometry()
            x = pos.x() + 10
            y = pos.y() + 10

            # Adjust if popup would go off screen
            if x + self.width() > screen_rect.right():
                x = pos.x() - self.width() - 10
            if y + self.height() > screen_rect.bottom():
                y = pos.y() - self.height() - 10

            self.move(x, y)

        self.show()

    def schedule_hide(self, delay: int = 200) -> None:
        """Schedule popup to hide after delay."""
        self.hide_timer.start(delay)

    def cancel_hide(self) -> None:
        """Cancel scheduled hide."""
        self.hide_timer.stop()


class NewsItemWidget(QFrame):
    """Widget for displaying a single news article."""

    clicked = Signal(str)  # url
    ticker_clicked = Signal(str, str)  # ticker, exchange

    # Sentiment color thresholds
    POSITIVE_THRESHOLD = 0.3
    NEGATIVE_THRESHOLD = -0.3

    def __init__(
        self,
        article: NewsArticle,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.article = article
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            NewsItemWidget {
                background-color: #1F2937;
                border-radius: 4px;
                margin: 2px;
            }
            NewsItemWidget:hover {
                background-color: #374151;
            }
        """)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # Sentiment indicator
        polarity = self._get_polarity()
        sentiment_color = self._get_sentiment_color(polarity)

        self.sentiment_label = QLabel()
        self.sentiment_label.setFixedWidth(50)
        self.sentiment_label.setAlignment(Qt.AlignCenter)

        if polarity is not None:
            indicator = self._get_indicator(polarity)
            self.sentiment_label.setText(f"{indicator} {polarity:+.2f}")
        else:
            self.sentiment_label.setText("--")

        self.sentiment_label.setStyleSheet(f"color: {sentiment_color}; font-size: 10px;")
        layout.addWidget(self.sentiment_label)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("background-color: #374151;")
        layout.addWidget(sep)

        # Content area
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)

        # Title
        self.title_label = QLabel(self.article.title)
        self.title_label.setWordWrap(True)
        font = QFont()
        font.setPointSize(10)
        self.title_label.setFont(font)
        self.title_label.setStyleSheet("color: #F9FAFB;")
        content_layout.addWidget(self.title_label)

        # Meta row: ticker, source, time
        meta_layout = QHBoxLayout()
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(8)

        # Ticker badge
        self.ticker_label = QLabel(self.article.ticker)
        self.ticker_label.setStyleSheet("""
            background-color: #374151;
            color: #60A5FA;
            padding: 1px 4px;
            border-radius: 2px;
            font-size: 9px;
        """)
        self.ticker_label.setCursor(Qt.PointingHandCursor)
        meta_layout.addWidget(self.ticker_label)

        # Source
        self.source_label = QLabel(self.article.source)
        self.source_label.setStyleSheet("color: #9CA3AF; font-size: 9px;")
        meta_layout.addWidget(self.source_label)

        # Time ago
        time_ago = self._format_time_ago(self.article.published_at)
        self.time_label = QLabel(time_ago)
        self.time_label.setStyleSheet("color: #6B7280; font-size: 9px;")
        meta_layout.addWidget(self.time_label)

        meta_layout.addStretch()
        content_layout.addLayout(meta_layout)

        layout.addLayout(content_layout, stretch=1)

    def _get_polarity(self) -> Optional[float]:
        """Get the best available polarity for the article."""
        if self.article.ensemble_polarity is not None:
            return self.article.ensemble_polarity
        if self.article.eodhd_sentiment is not None:
            return self.article.eodhd_sentiment.polarity
        return None

    def _get_sentiment_color(self, polarity: Optional[float]) -> str:
        """Get color based on polarity value."""
        if polarity is None:
            return "#6B7280"  # Gray
        if polarity > self.POSITIVE_THRESHOLD:
            return "#22C55E"  # Green
        elif polarity < self.NEGATIVE_THRESHOLD:
            return "#EF4444"  # Red
        else:
            return "#FBBF24"  # Yellow

    def _get_indicator(self, polarity: float) -> str:
        """Get emoji indicator based on polarity."""
        if polarity > self.POSITIVE_THRESHOLD:
            return "+"
        elif polarity < self.NEGATIVE_THRESHOLD:
            return "-"
        else:
            return "~"

    def _format_time_ago(self, dt: datetime) -> str:
        """Format datetime as relative time string.

        Note: EODHD timestamps are in UTC, so we compare with UTC now.
        """
        from datetime import timezone
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        if dt.tzinfo is not None:
            # Convert to naive datetime for comparison
            dt = dt.replace(tzinfo=None)

        diff = now_utc - dt

        if diff.days > 7:
            return dt.strftime("%b %d")
        elif diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours}h ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes}m ago"
        else:
            return "just now"

    def mousePressEvent(self, event) -> None:
        """Handle mouse press to open article."""
        if event.button() == Qt.LeftButton:
            # Check if click was on ticker label
            ticker_pos = self.ticker_label.mapFromParent(event.pos())
            if self.ticker_label.rect().contains(ticker_pos):
                self.ticker_clicked.emit(self.article.ticker, "US")
            else:
                self.clicked.emit(self.article.url)
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:
        """Show summary popup on hover."""
        popup = SummaryPopup.instance()
        popup.cancel_hide()
        # Use cursor position
        from PySide6.QtGui import QCursor
        global_pos = QCursor.pos()
        popup.show_for_article(self.article, global_pos)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Hide summary popup when leaving."""
        popup = SummaryPopup.instance()
        popup.schedule_hide(300)
        super().leaveEvent(event)


class NewsFeedWidget(QWidget):
    """Widget for displaying a scrollable news feed with filters."""

    article_clicked = Signal(str)  # url
    stock_clicked = Signal(str, str)  # ticker, exchange
    articles_changed = Signal(list)  # emitted when displayed articles change (load more, filter)

    # Display limit for performance - render at most this many items
    DISPLAY_LIMIT = 100
    LOAD_MORE_INCREMENT = 100
    FETCH_BATCH_SIZE = 100  # How many to fetch from server at a time

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._data_manager: Optional[DataManager] = None
        self._filter_ticker: Optional[str] = None
        self._filter_sentiment: str = "all"
        self._search_text: str = ""
        self._articles: List[NewsArticle] = []
        self._filtered_articles: List[NewsArticle] = []  # Cached filtered results
        self._displayed_count: int = 0  # How many are currently rendered
        self._server_offset: int = 0  # How many articles fetched from server
        self._server_has_more: bool = True  # Whether server has more articles

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Filter bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        # Ticker filter
        self.ticker_combo = QComboBox()
        self.ticker_combo.addItem("All Stocks", None)
        self.ticker_combo.setMinimumWidth(120)
        self.ticker_combo.currentIndexChanged.connect(self._on_ticker_filter_changed)
        filter_bar.addWidget(self.ticker_combo)

        # Sentiment filter
        self.sentiment_combo = QComboBox()
        self.sentiment_combo.addItem("All Sentiment", "all")
        self.sentiment_combo.addItem("Positive", "positive")
        self.sentiment_combo.addItem("Neutral", "neutral")
        self.sentiment_combo.addItem("Negative", "negative")
        self.sentiment_combo.setMinimumWidth(100)
        self.sentiment_combo.currentIndexChanged.connect(self._on_sentiment_filter_changed)
        filter_bar.addWidget(self.sentiment_combo)

        # Refresh button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        filter_bar.addWidget(self.refresh_btn)

        filter_bar.addStretch()

        # Search box
        search_label = QLabel("Search:")
        search_label.setStyleSheet("color: #9CA3AF;")
        filter_bar.addWidget(search_label)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter articles...")
        self.search_box.setMinimumWidth(150)
        self.search_box.setMaximumWidth(200)
        self.search_box.textChanged.connect(self._on_search_changed)
        filter_bar.addWidget(self.search_box)

        layout.addLayout(filter_bar)

        # Scroll area for news items
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

        # Container for news items
        self.news_container = QWidget()
        self.news_layout = QVBoxLayout(self.news_container)
        self.news_layout.setContentsMargins(0, 0, 0, 0)
        self.news_layout.setSpacing(4)
        self.news_layout.addStretch()

        self.scroll_area.setWidget(self.news_container)
        layout.addWidget(self.scroll_area)

        # Status bar with count and load more button
        status_bar = QHBoxLayout()
        status_bar.setSpacing(8)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #9CA3AF; font-size: 10px;")
        status_bar.addWidget(self.count_label)

        status_bar.addStretch()

        self.load_more_btn = QPushButton("Load More")
        self.load_more_btn.setStyleSheet("font-size: 10px; padding: 2px 8px;")
        self.load_more_btn.clicked.connect(self._on_load_more)
        self.load_more_btn.hide()
        status_bar.addWidget(self.load_more_btn)

        layout.addLayout(status_bar)

        # No data label
        self.no_data_label = QLabel("No news articles available")
        self.no_data_label.setAlignment(Qt.AlignCenter)
        self.no_data_label.setStyleSheet("color: #6B7280;")
        self.no_data_label.hide()
        layout.addWidget(self.no_data_label)

    def set_data_manager(self, data_manager: DataManager) -> None:
        """Set the data manager."""
        self._data_manager = data_manager

    def set_filter_ticker(self, ticker: Optional[str]) -> None:
        """Set the ticker filter."""
        self._filter_ticker = ticker

        # Update combo box selection
        for i in range(self.ticker_combo.count()):
            if self.ticker_combo.itemData(i) == ticker:
                self.ticker_combo.setCurrentIndex(i)
                break
        else:
            # Add ticker if not in list
            if ticker:
                self.ticker_combo.addItem(ticker, ticker)
                self.ticker_combo.setCurrentIndex(self.ticker_combo.count() - 1)

        self._apply_filters()

    def set_filter_sentiment(self, sentiment: str) -> None:
        """Set the sentiment filter ('positive', 'negative', 'neutral', 'all')."""
        self._filter_sentiment = sentiment

        for i in range(self.sentiment_combo.count()):
            if self.sentiment_combo.itemData(i) == sentiment:
                self.sentiment_combo.setCurrentIndex(i)
                break

        self._apply_filters()

    def refresh(self, articles=None) -> None:
        """Refresh news articles from data source.

        Args:
            articles: Pre-fetched news articles (optional, avoids duplicate API call)
        """
        from loguru import logger

        if not self._data_manager:
            self._show_no_data()
            return

        try:
            # Reset server tracking
            self._server_offset = 0
            self._server_has_more = True

            # Date range for last 30 days
            end_date = date.today()
            start_date = end_date - timedelta(days=30)

            # Use pre-fetched articles if provided
            if articles is not None and self._filter_ticker:
                self._articles = articles
                self._server_offset = len(articles)
                self._server_has_more = len(articles) >= self.FETCH_BATCH_SIZE
                logger.info(f"News feed: using {len(self._articles)} pre-fetched articles for {self._filter_ticker}")
            elif self._filter_ticker:
                # Fetch only initial batch for fast loading
                self._articles = self._data_manager.get_news(
                    self._filter_ticker,
                    limit=self.FETCH_BATCH_SIZE,
                    use_cache=True,
                    from_date=start_date,
                    to_date=end_date,
                )
                self._server_offset = len(self._articles)
                self._server_has_more = len(self._articles) >= self.FETCH_BATCH_SIZE
                logger.info(f"News feed: fetched {len(self._articles)} articles for {self._filter_ticker} (initial batch)")
            else:
                # Get news for all tracked stocks
                self._articles = []
                companies = self._data_manager.get_all_companies()

                for company in companies[:10]:  # Limit for performance
                    articles = self._data_manager.get_news(
                        company.ticker,
                        limit=100,
                        use_cache=True,
                        from_date=start_date,
                        to_date=end_date,
                    )
                    self._articles.extend(articles)

                # Sort by date
                self._articles.sort(
                    key=lambda a: a.published_at,
                    reverse=True
                )
                logger.info(f"News feed: fetched {len(self._articles)} articles for all stocks")

            # Update ticker combo with available tickers
            self._update_ticker_combo()

            # Apply filters and display
            self._apply_filters()

        except Exception as e:
            logger.error(f"Failed to refresh news: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._show_no_data()

    def _update_ticker_combo(self) -> None:
        """Update ticker combo box with available tickers."""
        current_ticker = self.ticker_combo.currentData()

        # Get unique tickers
        tickers = set()
        for article in self._articles:
            tickers.add(article.ticker)

        # Rebuild combo box
        self.ticker_combo.blockSignals(True)
        self.ticker_combo.clear()
        self.ticker_combo.addItem("All Stocks", None)

        for ticker in sorted(tickers):
            self.ticker_combo.addItem(ticker, ticker)

        # Restore selection
        for i in range(self.ticker_combo.count()):
            if self.ticker_combo.itemData(i) == current_ticker:
                self.ticker_combo.setCurrentIndex(i)
                break

        self.ticker_combo.blockSignals(False)

    def _apply_filters(self) -> None:
        """Apply current filters and update display."""
        filtered = self._articles

        # Note: Ticker filter is not needed here because refresh() already
        # fetches news for the specific ticker. The articles are pre-filtered.

        # Apply sentiment filter
        if self._filter_sentiment != "all":
            filtered = [a for a in filtered if self._matches_sentiment(a)]

        # Apply search filter
        if self._search_text:
            search_lower = self._search_text.lower()
            filtered = [
                a for a in filtered
                if search_lower in a.title.lower() or
                   search_lower in a.ticker.lower() or
                   (a.source and search_lower in a.source.lower())
            ]

        # Store filtered results and reset display count
        self._filtered_articles = filtered
        self._displayed_count = 0

        # Display initial batch
        self._display_articles()

    def _matches_sentiment(self, article: NewsArticle) -> bool:
        """Check if article matches current sentiment filter."""
        polarity = None
        if article.ensemble_polarity is not None:
            polarity = article.ensemble_polarity
        elif article.eodhd_sentiment is not None:
            polarity = article.eodhd_sentiment.polarity

        if polarity is None:
            return self._filter_sentiment == "neutral"

        if self._filter_sentiment == "positive":
            return polarity > 0.3
        elif self._filter_sentiment == "negative":
            return polarity < -0.3
        elif self._filter_sentiment == "neutral":
            return -0.3 <= polarity <= 0.3

        return True

    def _display_articles(self, append: bool = False) -> None:
        """Display articles in the scroll area.

        Args:
            append: If True, append to existing items. If False, clear and redisplay.
        """
        articles = self._filtered_articles

        if not append:
            # Clear existing items
            while self.news_layout.count() > 1:  # Keep the stretch
                item = self.news_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._displayed_count = 0

        if not articles:
            self._show_no_data()
            self.count_label.setText("")
            self.load_more_btn.hide()
            return

        self.no_data_label.hide()
        self.scroll_area.show()

        # Calculate how many to display
        start_idx = self._displayed_count
        end_idx = min(start_idx + self.DISPLAY_LIMIT, len(articles))

        # Add items for this batch
        for i in range(start_idx, end_idx):
            article = articles[i]
            item = NewsItemWidget(article)
            item.clicked.connect(self._on_article_clicked)
            item.ticker_clicked.connect(self._on_ticker_clicked)
            self.news_layout.insertWidget(self.news_layout.count() - 1, item)

        self._displayed_count = end_idx

        # Update status
        total = len(articles)
        has_more_to_display = self._displayed_count < total
        has_more_on_server = self._server_has_more

        if has_more_to_display or has_more_on_server:
            if has_more_on_server:
                self.count_label.setText(f"Showing {self._displayed_count} of {total}+ articles")
            else:
                self.count_label.setText(f"Showing {self._displayed_count} of {total} articles")
            self.load_more_btn.setText(f"Load {self.LOAD_MORE_INCREMENT} More")
            self.load_more_btn.show()
        else:
            self.count_label.setText(f"Showing all {total} articles")
            self.load_more_btn.hide()

    def _on_load_more(self) -> None:
        """Load more articles - fetch from server if needed."""
        from loguru import logger

        # Check if we need to fetch more from server
        if self._displayed_count >= len(self._filtered_articles) and self._server_has_more:
            self._fetch_more_from_server()

        self._display_articles(append=True)
        # Emit signal with all displayed articles so sentiment can be updated
        displayed_articles = self._filtered_articles[:self._displayed_count]
        self.articles_changed.emit(displayed_articles)

    def _fetch_more_from_server(self) -> None:
        """Fetch more articles from server."""
        from loguru import logger

        if not self._data_manager or not self._filter_ticker or not self._server_has_more:
            return

        try:
            end_date = date.today()
            start_date = end_date - timedelta(days=30)

            logger.info(f"Fetching more news from server: offset={self._server_offset}")
            new_articles = self._data_manager.get_news(
                self._filter_ticker,
                limit=self.FETCH_BATCH_SIZE,
                offset=self._server_offset,
                use_cache=True,
                from_date=start_date,
                to_date=end_date,
            )

            if new_articles:
                self._articles.extend(new_articles)
                self._server_offset += len(new_articles)
                self._server_has_more = len(new_articles) >= self.FETCH_BATCH_SIZE
                logger.info(f"Fetched {len(new_articles)} more articles, total now {len(self._articles)}")

                # Re-apply filters to include new articles
                self._reapply_filters()
            else:
                self._server_has_more = False
                logger.info("No more articles available from server")

        except Exception as e:
            logger.error(f"Failed to fetch more articles: {e}")
            self._server_has_more = False

    def _reapply_filters(self) -> None:
        """Re-apply filters without resetting display count."""
        filtered = self._articles

        if self._filter_sentiment != "all":
            filtered = [a for a in filtered if self._matches_sentiment(a)]

        if self._search_text:
            search_lower = self._search_text.lower()
            filtered = [
                a for a in filtered
                if search_lower in a.title.lower() or
                   search_lower in a.ticker.lower() or
                   (a.source and search_lower in a.source.lower())
            ]

        self._filtered_articles = filtered

    def _show_no_data(self) -> None:
        """Show no data message."""
        while self.news_layout.count() > 1:
            item = self.news_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.no_data_label.show()
        self.count_label.setText("")
        self.load_more_btn.hide()

    def _on_ticker_filter_changed(self, index: int) -> None:
        """Handle ticker filter change."""
        self._filter_ticker = self.ticker_combo.itemData(index)
        self._apply_filters()

    def _on_sentiment_filter_changed(self, index: int) -> None:
        """Handle sentiment filter change."""
        self._filter_sentiment = self.sentiment_combo.itemData(index)
        self._apply_filters()

    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self._search_text = text
        self._apply_filters()

    def _on_article_clicked(self, url: str) -> None:
        """Handle article click - open in browser."""
        try:
            webbrowser.open(url)
        except Exception as e:
            from loguru import logger
            logger.error(f"Failed to open URL: {e}")

        self.article_clicked.emit(url)

    def _on_ticker_clicked(self, ticker: str, exchange: str) -> None:
        """Handle ticker click - emit signal for stock selection."""
        self.stock_clicked.emit(ticker, exchange)

    def clear(self) -> None:
        """Clear the news feed."""
        self._articles = []
        self._filtered_articles = []
        self._displayed_count = 0
        self._server_offset = 0
        self._server_has_more = True
        self._filter_ticker = None
        self.ticker_combo.setCurrentIndex(0)
        self._show_no_data()

"""Interactive market treemap widget."""

from dataclasses import dataclass
from typing import Optional, List, Dict, Callable, Any
import math

from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QTimer
from PySide6.QtGui import (
    QPainter,
    QColor,
    QBrush,
    QPen,
    QFont,
    QFontMetrics,
    QPainterPath,
    QMouseEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QLabel,
    QToolTip,
    QMenu,
    QSizePolicy,
)
import squarify

from investment_tool.utils.helpers import (
    format_percent,
    format_large_number,
    interpolate_color,
)
from investment_tool.config.settings import get_config


@dataclass
class TreemapItem:
    """Single item in the treemap."""
    ticker: str
    name: str
    exchange: str
    value: float  # Size value (e.g., market cap)
    change_percent: float  # Performance for color
    sector: Optional[str] = None
    industry: Optional[str] = None
    price: Optional[float] = None
    volume: Optional[int] = None
    pe_ratio: Optional[float] = None
    market_cap: Optional[float] = None

    # Computed layout properties
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0


class MarketTreemap(QWidget):
    """
    Interactive market treemap visualization.

    Displays stocks as rectangles sized by market cap and colored by performance.
    """

    stock_selected = Signal(str, str)  # ticker, exchange
    stock_double_clicked = Signal(str, str)  # ticker, exchange
    stocks_compare_requested = Signal(list)  # list of (ticker, exchange) tuples
    stock_remove_requested = Signal(str, str, str)  # ticker, exchange, category_id (empty for all)
    stock_add_to_watchlist = Signal(str, str)  # ticker, exchange
    filter_changed = Signal(str)  # category name or "All Stocks"
    period_changed = Signal(str)  # period like "1D", "1W", etc.

    PERIODS = ["1D", "1W", "1M", "3M", "6M", "YTD", "1Y", "2Y", "5Y"]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.config = get_config()
        self._items: List[TreemapItem] = []
        self._layout_rects: List[QRectF] = []
        self._selected_ticker: Optional[str] = None
        self._hovered_index: int = -1
        self._compare_selection: List[int] = []
        self._current_category_id: Optional[str] = None  # Track current category for removal

        # View state
        self._zoom = 1.0
        self._pan_offset = QPointF(0, 0)
        self._last_mouse_pos: Optional[QPointF] = None
        self._is_panning = False

        # Color scale from config
        color_config = self.config.ui.treemap_color_scale
        self._min_color = color_config.min_color
        self._mid_color = color_config.mid_color
        self._max_color = color_config.max_color
        self._min_value = color_config.min_value
        self._max_value = color_config.max_value

        self._setup_ui()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        # Period selector
        period_label = QLabel("Period:")
        toolbar.addWidget(period_label)

        self.period_combo = QComboBox()
        self.period_combo.addItems(self.PERIODS)
        self.period_combo.setCurrentText("1D")
        self.period_combo.currentTextChanged.connect(self._on_period_changed)
        toolbar.addWidget(self.period_combo)

        # Category filter
        filter_label = QLabel("Filter:")
        toolbar.addWidget(filter_label)

        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All Stocks")
        self.filter_combo.addItem("Large Cap (>$200B)")
        self.filter_combo.addItem("Mid Cap ($20B-$200B)")
        self.filter_combo.addItem("Small Cap ($2B-$20B)")
        self.filter_combo.addItem("Tiny Stocks (<$2B)")
        self.filter_combo.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.filter_combo)

        toolbar.addStretch()

        # Legend
        self._create_legend(toolbar)

        layout.addLayout(toolbar)

        # Treemap canvas
        self.canvas = TreemapCanvas(self)
        self.canvas.item_clicked.connect(self._on_item_clicked)
        self.canvas.item_double_clicked.connect(self._on_item_double_clicked)
        self.canvas.item_hovered.connect(self._on_item_hovered)
        self.canvas.context_menu_requested.connect(self._on_context_menu)
        layout.addWidget(self.canvas, stretch=1)

    def _create_legend(self, layout: QHBoxLayout) -> None:
        """Create color legend."""
        legend_label = QLabel("Performance:")
        layout.addWidget(legend_label)

        # Color gradient legend
        for value, label in [(-5, "-5%"), (0, "0%"), (5, "+5%")]:
            color = interpolate_color(
                value,
                self._min_value,
                self._max_value,
                self._min_color,
                self._mid_color,
                self._max_color,
            )
            color_label = QLabel(f"  {label}")
            color_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {color};
                    color: {'#000' if value == 0 else '#fff'};
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-size: 11px;
                }}
            """)
            layout.addWidget(color_label)

    def set_items(self, items: List[TreemapItem]) -> None:
        """Set the items to display in the treemap."""
        self._items = items
        self._compute_layout()
        self.canvas.set_items(self._items)
        self.canvas.update()

    def set_categories(self, categories: List[str]) -> None:
        """Set available category filters."""
        current = self.filter_combo.currentText()
        self.filter_combo.clear()
        # Add built-in market cap filters
        self.filter_combo.addItem("All Stocks")
        self.filter_combo.addItem("Large Cap (>$200B)")
        self.filter_combo.addItem("Mid Cap ($20B-$200B)")
        self.filter_combo.addItem("Small Cap ($2B-$20B)")
        self.filter_combo.addItem("Tiny Stocks (<$2B)")
        # Add sector/category filters (exclude "Uncategorized" - those stocks show in All Stocks)
        for cat in categories:
            if cat != "Uncategorized":
                self.filter_combo.addItem(cat)

        # Restore selection if possible
        idx = self.filter_combo.findText(current)
        if idx >= 0:
            self.filter_combo.setCurrentIndex(idx)

    def get_selected_period(self) -> str:
        """Get the currently selected time period."""
        return self.period_combo.currentText()

    def get_selected_filter(self) -> str:
        """Get the currently selected filter."""
        return self.filter_combo.currentText()

    def set_current_category_id(self, category_id: Optional[str]) -> None:
        """Set the current category ID for removal operations."""
        self._current_category_id = category_id

    def _compute_layout(self) -> None:
        """Compute treemap layout using squarify algorithm."""
        if not self._items:
            return

        # Get canvas size
        width = self.canvas.width() - 4
        height = self.canvas.height() - 4

        if width <= 0 or height <= 0:
            return

        # Filter out zero or negative values
        valid_items = [item for item in self._items if item.value > 0]
        if not valid_items:
            return

        # Normalize values for squarify
        values = [item.value for item in valid_items]
        total = sum(values)
        normalized = [v / total * width * height for v in values]

        # Compute rectangles
        rects = squarify.squarify(normalized, 2, 2, width, height)

        # Assign layout to items
        for item, rect in zip(valid_items, rects):
            item.x = rect["x"]
            item.y = rect["y"]
            item.width = rect["dx"]
            item.height = rect["dy"]

    def _on_period_changed(self, period: str) -> None:
        """Handle period selection change."""
        self.period_changed.emit(period)

    def _on_filter_changed(self, filter_text: str) -> None:
        """Handle filter selection change."""
        self.filter_changed.emit(filter_text)

    def _on_item_clicked(self, index: int) -> None:
        """Handle item click."""
        if 0 <= index < len(self._items):
            item = self._items[index]
            self._selected_ticker = item.ticker
            self.stock_selected.emit(item.ticker, item.exchange)
            self.canvas.set_selected(index)

    def _on_item_double_clicked(self, index: int) -> None:
        """Handle item double-click."""
        if 0 <= index < len(self._items):
            item = self._items[index]
            self.stock_double_clicked.emit(item.ticker, item.exchange)

    def _on_item_hovered(self, index: int) -> None:
        """Handle item hover."""
        self._hovered_index = index

    def _on_context_menu(self, index: int, pos: QPointF) -> None:
        """Show context menu for an item."""
        if index < 0 or index >= len(self._items):
            return

        item = self._items[index]
        menu = QMenu(self)

        view_action = menu.addAction(f"View {item.ticker}")
        view_action.triggered.connect(
            lambda: self.stock_selected.emit(item.ticker, item.exchange)
        )

        open_action = menu.addAction("Open in New Window")
        open_action.triggered.connect(
            lambda: self.stock_double_clicked.emit(item.ticker, item.exchange)
        )

        menu.addSeparator()

        compare_action = menu.addAction("Add to Compare")
        compare_action.triggered.connect(
            lambda: self._add_to_compare(index)
        )

        watchlist_action = menu.addAction("Add to Watchlist")
        watchlist_action.triggered.connect(
            lambda: self.stock_add_to_watchlist.emit(item.ticker, item.exchange)
        )

        # Add remove from category option
        menu.addSeparator()
        current_filter = self.filter_combo.currentText()
        market_cap_filters = ("All Stocks", "Large Cap (>$200B)", "Mid Cap ($20B-$200B)",
                              "Small Cap ($2B-$20B)", "Tiny Stocks (<$2B)")

        if current_filter == "All Stocks":
            remove_action = menu.addAction("Remove from All Categories")
            remove_action.triggered.connect(
                lambda: self.stock_remove_requested.emit(item.ticker, item.exchange, "")
            )
        elif current_filter not in market_cap_filters and self._current_category_id:
            remove_action = menu.addAction(f"Remove from {current_filter}")
            remove_action.triggered.connect(
                lambda: self.stock_remove_requested.emit(
                    item.ticker, item.exchange, self._current_category_id
                )
            )

        menu.exec(self.mapToGlobal(pos.toPoint()))

    def _add_to_compare(self, index: int) -> None:
        """Add item to comparison selection."""
        if index not in self._compare_selection:
            self._compare_selection.append(index)
            if len(self._compare_selection) >= 2:
                items = [
                    (self._items[i].ticker, self._items[i].exchange)
                    for i in self._compare_selection
                ]
                self.stocks_compare_requested.emit(items)
                self._compare_selection.clear()

    def resizeEvent(self, event) -> None:
        """Handle resize events."""
        super().resizeEvent(event)
        QTimer.singleShot(0, self._compute_layout)
        QTimer.singleShot(10, self.canvas.update)


class TreemapCanvas(QWidget):
    """Canvas widget for rendering the treemap."""

    item_clicked = Signal(int)
    item_double_clicked = Signal(int)
    item_hovered = Signal(int)
    context_menu_requested = Signal(int, QPointF)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._items: List[TreemapItem] = []
        self._selected_index: int = -1
        self._hovered_index: int = -1

        config = get_config()
        color_config = config.ui.treemap_color_scale
        self._min_color = color_config.min_color
        self._mid_color = color_config.mid_color
        self._max_color = color_config.max_color
        self._min_value = color_config.min_value
        self._max_value = color_config.max_value

        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    def set_items(self, items: List[TreemapItem]) -> None:
        """Set items to render."""
        self._items = items
        self._selected_index = -1
        self._hovered_index = -1
        self.update()

    def set_selected(self, index: int) -> None:
        """Set selected item index."""
        self._selected_index = index
        self.update()

    def paintEvent(self, event) -> None:
        """Render the treemap."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor("#1F2937"))

        if not self._items:
            # Draw placeholder text
            painter.setPen(QColor("#6B7280"))
            painter.setFont(QFont("Segoe UI", 14))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "No data to display\nAdd stocks or refresh data"
            )
            return

        # Draw items
        for i, item in enumerate(self._items):
            self._draw_item(painter, item, i)

    def _draw_item(self, painter: QPainter, item: TreemapItem, index: int) -> None:
        """Draw a single treemap item."""
        if item.width < 2 or item.height < 2:
            return

        rect = QRectF(item.x, item.y, item.width, item.height)

        # Compute color based on performance
        color_hex = interpolate_color(
            item.change_percent * 100,  # Convert to percentage
            self._min_value,
            self._max_value,
            self._min_color,
            self._mid_color,
            self._max_color,
        )
        fill_color = QColor(color_hex)

        # Draw filled rectangle
        painter.fillRect(rect, QBrush(fill_color))

        # Draw border
        if index == self._selected_index:
            painter.setPen(QPen(QColor("#3B82F6"), 3))
        elif index == self._hovered_index:
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
        else:
            painter.setPen(QPen(QColor("#374151"), 1))

        painter.drawRect(rect)

        # Draw text if item is large enough
        if item.width > 40 and item.height > 30:
            self._draw_item_text(painter, item, rect)

    def _draw_item_text(
        self, painter: QPainter, item: TreemapItem, rect: QRectF
    ) -> None:
        """Draw text labels on an item."""
        # Determine text color based on background brightness
        color_hex = interpolate_color(
            item.change_percent * 100,
            self._min_value,
            self._max_value,
            self._min_color,
            self._mid_color,
            self._max_color,
        )
        bg_color = QColor(color_hex)
        brightness = (bg_color.red() * 299 + bg_color.green() * 587 + bg_color.blue() * 114) / 1000
        text_color = QColor("#000000") if brightness > 128 else QColor("#FFFFFF")

        painter.setPen(text_color)

        # Calculate font sizes based on rect size
        ticker_size = min(max(int(item.width / 5), 10), 18)
        change_size = min(max(int(item.width / 7), 8), 14)

        padding = 4
        inner_rect = rect.adjusted(padding, padding, -padding, -padding)

        # Draw ticker
        ticker_font = QFont("Segoe UI", ticker_size, QFont.Bold)
        painter.setFont(ticker_font)
        ticker_metrics = QFontMetrics(ticker_font)
        ticker_height = ticker_metrics.height()

        ticker_text = item.ticker
        if ticker_metrics.horizontalAdvance(ticker_text) > inner_rect.width():
            ticker_text = ticker_metrics.elidedText(
                ticker_text, Qt.ElideRight, int(inner_rect.width())
            )

        painter.drawText(
            inner_rect,
            Qt.AlignTop | Qt.AlignHCenter,
            ticker_text
        )

        # Draw change percentage and additional info if space allows
        change_font = QFont("Segoe UI", change_size)
        change_metrics = QFontMetrics(change_font)
        line_height = change_metrics.height()

        # Calculate available space below ticker
        available_height = inner_rect.height() - ticker_height - 4  # 4px gap

        if available_height > line_height:
            painter.setFont(change_font)

            # Build info text: price, change %, P/E, market cap
            change_text = format_percent(item.change_percent, decimals=2)

            # Determine how many lines we can fit
            max_lines = int(available_height / line_height)

            info_lines = []
            if max_lines >= 4 and item.price is not None:
                info_lines.append(f"${item.price:.2f}")
            info_lines.append(change_text)
            if max_lines >= 3 and item.pe_ratio is not None:
                info_lines.append(f"P/E: {item.pe_ratio:.1f}")
            if max_lines >= 4 and item.market_cap is not None:
                info_lines.append(format_large_number(item.market_cap))

            # Trim to max lines
            info_lines = info_lines[:max_lines]
            info_text = "\n".join(info_lines)

            painter.drawText(
                inner_rect,
                Qt.AlignBottom | Qt.AlignHCenter,
                info_text
            )

    def _get_item_at(self, pos: QPointF) -> int:
        """Get item index at position."""
        for i, item in enumerate(self._items):
            rect = QRectF(item.x, item.y, item.width, item.height)
            if rect.contains(pos):
                return i
        return -1

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press."""
        if event.button() == Qt.LeftButton:
            index = self._get_item_at(event.position())
            if index >= 0:
                self.item_clicked.emit(index)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Handle double click."""
        if event.button() == Qt.LeftButton:
            index = self._get_item_at(event.position())
            if index >= 0:
                self.item_double_clicked.emit(index)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move for hover effects."""
        index = self._get_item_at(event.position())

        if index != self._hovered_index:
            self._hovered_index = index
            self.item_hovered.emit(index)
            self.update()

            # Show tooltip
            if index >= 0:
                item = self._items[index]
                tooltip = self._build_tooltip(item)
                QToolTip.showText(event.globalPosition().toPoint(), tooltip, self)
            else:
                QToolTip.hideText()

    def _build_tooltip(self, item: TreemapItem) -> str:
        """Build tooltip HTML for an item."""
        change_color = "#22C55E" if item.change_percent >= 0 else "#EF4444"
        price_str = f"${item.price:.2f}" if item.price else "N/A"
        return f"""
        <div style="padding: 8px;">
            <b style="font-size: 14px;">{item.ticker}</b>
            <span style="color: #9CA3AF;"> - {item.name}</span><br/>
            <span style="font-size: 13px;">Price: {price_str}</span><br/>
            <span style="color: {change_color}; font-size: 13px;">
                {format_percent(item.change_percent, decimals=2)}
            </span><br/>
            <span style="color: #9CA3AF;">
                Market Cap: {format_large_number(item.value)}
            </span>
        </div>
        """

    def leaveEvent(self, event) -> None:
        """Handle mouse leave."""
        self._hovered_index = -1
        self.update()
        QToolTip.hideText()

    def contextMenuEvent(self, event) -> None:
        """Handle context menu."""
        index = self._get_item_at(event.pos())
        if index >= 0:
            self.context_menu_requested.emit(index, event.pos())

"""Interactive stock chart widget with candlesticks and indicators."""

from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from typing import Optional, List, Dict, Tuple, Any
import numpy as np

# Eastern Time offset (UTC-5 for EST, UTC-4 for EDT)
# For simplicity, using EST (UTC-5) - could be made dynamic
ET_OFFSET = timedelta(hours=-5)

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QLabel,
    QPushButton,
    QMenu,
    QCheckBox,
    QSplitter,
    QSizePolicy,
)
from PySide6.QtGui import QColor, QBrush, QPen
from PySide6.QtCore import QRectF

import pyqtgraph as pg
import pandas as pd

from investment_tool.config.settings import get_config


# Configure pyqtgraph
pg.setConfigOptions(antialias=True, background="#1F2937", foreground="#F9FAFB")


class MeasureViewBox(pg.ViewBox):
    """Custom ViewBox that supports measure mode for drawing price range rectangles."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._measure_mode = False
        self._measure_rect = None
        self._measure_label = None
        self._chart = None  # Reference to StockChart for data access
        # Disable default context menu so right-click can clear measure
        self.setMenuEnabled(False)

    def setChart(self, chart: "StockChart") -> None:
        """Set reference to the parent chart."""
        self._chart = chart

    def setMeasureMode(self, enabled: bool) -> None:
        """Enable or disable measure mode."""
        self._measure_mode = enabled
        if enabled:
            self.setMouseEnabled(x=False, y=False)
        else:
            self.setMouseEnabled(x=True, y=True)
            self._clearMeasure()

    def _clearMeasure(self) -> None:
        """Clear measure graphics."""
        if self._measure_rect is not None:
            self.removeItem(self._measure_rect)
            self._measure_rect = None
        if self._measure_label is not None:
            self.removeItem(self._measure_label)
            self._measure_label = None

    def mouseDragEvent(self, ev, axis=None):
        """Handle mouse drag for measure mode."""
        if not self._measure_mode:
            super().mouseDragEvent(ev, axis)
            return

        # Only handle left button
        if ev.button() != Qt.LeftButton:
            ev.ignore()
            return

        ev.accept()

        # Get positions in view (data) coordinates
        start_pos = self.mapSceneToView(ev.buttonDownScenePos())
        current_pos = self.mapSceneToView(ev.scenePos())

        x1, y1 = start_pos.x(), start_pos.y()
        x2, y2 = current_pos.x(), current_pos.y()

        # Draw/update the measure region
        self._drawMeasureRegion(x1, y1, x2, y2)

        if ev.isFinish():
            # Drag complete - keep the rectangle displayed
            pass

    def mouseClickEvent(self, ev):
        """Handle mouse click to clear measure region."""
        if self._measure_mode and ev.button() == Qt.RightButton:
            self._clearMeasure()
            ev.accept()
        else:
            super().mouseClickEvent(ev)

    def _drawMeasureRegion(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Draw the measure region rectangle from start to current position."""
        if self._chart is None:
            return

        display_data = getattr(self._chart, '_display_data', None)
        if display_data is None or display_data.empty:
            return

        # Clear previous
        self._clearMeasure()

        # Use exact mouse coordinates for the rectangle
        # y1 = start price, y2 = current price
        price1 = y1
        price2 = y2

        # Calculate stats
        diff = price2 - price1
        pct = (diff / price1 * 100) if price1 != 0 else 0

        # Calculate time difference
        max_idx = len(display_data) - 1
        idx1 = max(0, min(int(x1), max_idx))
        idx2 = max(0, min(int(x2), max_idx))

        time_str = ""
        try:
            t1 = display_data.index[idx1]
            t2 = display_data.index[idx2]

            # Handle both datetime and date objects
            if hasattr(t1, 'total_seconds'):
                # Already a timedelta-compatible type
                td = abs(t2 - t1)
                total_seconds = td.total_seconds()
            elif hasattr(t1, 'date') and callable(t1.date):
                # datetime object
                td = abs(t2 - t1)
                total_seconds = td.total_seconds()
            else:
                # date object - convert to days
                from datetime import date
                if isinstance(t1, date):
                    td = abs(t2 - t1)
                    total_seconds = td.days * 86400
                else:
                    # Fallback to bar count
                    total_seconds = None

            if total_seconds is not None:
                days = int(total_seconds // 86400)
                hours = int((total_seconds % 86400) // 3600)
                minutes = int((total_seconds % 3600) // 60)

                if days > 0:
                    time_str = f"{days}d {hours}h"
                elif hours > 0:
                    time_str = f"{hours}h {minutes}m"
                else:
                    time_str = f"{minutes}m"
            else:
                time_str = f"{abs(idx2 - idx1)} bars"
        except Exception:
            time_str = f"{abs(idx2 - idx1)} bars"

        # Color based on gain/loss
        if diff >= 0:
            fill_color = QColor(34, 197, 94, 77)   # Green 30% alpha
            border_color = QColor(34, 197, 94)
        else:
            fill_color = QColor(239, 68, 68, 77)  # Red 30% alpha
            border_color = QColor(239, 68, 68)

        # Draw rectangle from (x1,y1) to (x2,y2)
        rect_x = [x1, x2, x2, x1, x1]
        rect_y = [y1, y1, y2, y2, y1]
        self._measure_rect = pg.PlotCurveItem(
            rect_x, rect_y,
            pen=pg.mkPen(border_color, width=2),
            brush=pg.mkBrush(fill_color),
            fillLevel=min(y1, y2)  # Fill from bottom of rectangle
        )
        self.addItem(self._measure_rect, ignoreBounds=True)

        # Create label inside the rectangle (centered)
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2
        sign = "+" if diff >= 0 else ""
        text = f"${price1:.2f} → ${price2:.2f}\n{sign}${diff:.2f} ({sign}{pct:.1f}%)\n{time_str}"
        self._measure_label = pg.TextItem(text, color="#F9FAFB", anchor=(0.5, 0.5))
        self._measure_label.setPos(center_x, center_y)
        self.addItem(self._measure_label, ignoreBounds=True)


class CandlestickItem(pg.GraphicsObject):
    """Custom graphics item for candlestick chart."""

    def __init__(self, data: pd.DataFrame):
        super().__init__()
        self.data = data
        self.picture = None
        self._generate_picture()

    def _generate_picture(self) -> None:
        """Pre-render the candlesticks."""
        from PySide6.QtGui import QPainter, QPicture, QPen, QBrush

        self.picture = QPicture()
        painter = QPainter(self.picture)

        if self.data is None or self.data.empty:
            painter.end()
            return

        # Colors
        green = QColor("#22C55E")
        red = QColor("#EF4444")
        green_brush = QBrush(green)
        red_brush = QBrush(red)

        bar_width = 0.6

        for i, (idx, row) in enumerate(self.data.iterrows()):
            open_price = row["open"]
            high = row["high"]
            low = row["low"]
            close = row["close"]

            # Skip NaN values (future times in intraday view)
            if pd.isna(open_price) or pd.isna(close):
                continue

            is_bullish = close >= open_price
            color = green if is_bullish else red
            brush = green_brush if is_bullish else red_brush

            # Draw wick (high-low line)
            painter.setPen(pg.mkPen(color, width=1))
            painter.drawLine(
                pg.QtCore.QPointF(i, low),
                pg.QtCore.QPointF(i, high)
            )

            # Draw body
            painter.setBrush(brush)
            painter.setPen(pg.mkPen(color, width=1))

            body_top = max(open_price, close)
            body_bottom = min(open_price, close)
            body_height = body_top - body_bottom

            if body_height < 0.001:
                # Doji - just draw a line
                painter.drawLine(
                    pg.QtCore.QPointF(i - bar_width / 2, close),
                    pg.QtCore.QPointF(i + bar_width / 2, close)
                )
            else:
                painter.drawRect(
                    pg.QtCore.QRectF(
                        i - bar_width / 2,
                        body_bottom,
                        bar_width,
                        body_height
                    )
                )

        painter.end()

    def paint(self, painter, option, widget) -> None:
        """Paint the candlesticks."""
        if self.picture:
            self.picture.play(painter)

    def boundingRect(self):
        """Return bounding rectangle."""
        if self.data is None or self.data.empty:
            return pg.QtCore.QRectF(0, 0, 1, 1)

        # Use nanmin/nanmax to handle NaN values in intraday data
        low_min = self.data["low"].min(skipna=True)
        high_max = self.data["high"].max(skipna=True)
        if pd.isna(low_min) or pd.isna(high_max):
            return pg.QtCore.QRectF(0, 0, 1, 1)

        return pg.QtCore.QRectF(
            -1,
            low_min,
            len(self.data) + 1,
            high_max - low_min
        )

    def set_data(self, data: pd.DataFrame) -> None:
        """Update the data and regenerate picture."""
        self.data = data
        self._generate_picture()
        self.prepareGeometryChange()
        self.update()


class OHLCItem(pg.GraphicsObject):
    """Custom graphics item for OHLC bar chart."""

    def __init__(self, data: pd.DataFrame):
        super().__init__()
        self.data = data
        self.picture = None
        self._generate_picture()

    def _generate_picture(self) -> None:
        """Pre-render the OHLC bars."""
        from PySide6.QtGui import QPainter, QPicture, QPen

        self.picture = QPicture()
        painter = QPainter(self.picture)

        if self.data is None or self.data.empty:
            painter.end()
            return

        # Colors
        green = QColor("#22C55E")
        red = QColor("#EF4444")

        tick_width = 0.3  # Width of open/close ticks

        for i, (idx, row) in enumerate(self.data.iterrows()):
            open_price = row["open"]
            high = row["high"]
            low = row["low"]
            close = row["close"]

            # Skip NaN values (future times in intraday view)
            if pd.isna(open_price) or pd.isna(close):
                continue

            is_bullish = close >= open_price
            color = green if is_bullish else red
            pen = pg.mkPen(color, width=2)
            painter.setPen(pen)

            # Draw vertical line (high to low)
            painter.drawLine(
                pg.QtCore.QPointF(i, low),
                pg.QtCore.QPointF(i, high)
            )

            # Draw open tick (left side)
            painter.drawLine(
                pg.QtCore.QPointF(i - tick_width, open_price),
                pg.QtCore.QPointF(i, open_price)
            )

            # Draw close tick (right side)
            painter.drawLine(
                pg.QtCore.QPointF(i, close),
                pg.QtCore.QPointF(i + tick_width, close)
            )

        painter.end()

    def paint(self, painter, option, widget) -> None:
        """Paint the OHLC bars."""
        if self.picture:
            self.picture.play(painter)

    def boundingRect(self):
        """Return bounding rectangle."""
        if self.data is None or self.data.empty:
            return pg.QtCore.QRectF(0, 0, 1, 1)

        # Use skipna to handle NaN values in intraday data
        low_min = self.data["low"].min(skipna=True)
        high_max = self.data["high"].max(skipna=True)
        if pd.isna(low_min) or pd.isna(high_max):
            return pg.QtCore.QRectF(0, 0, 1, 1)

        return pg.QtCore.QRectF(
            -1,
            low_min,
            len(self.data) + 1,
            high_max - low_min
        )

    def set_data(self, data: pd.DataFrame) -> None:
        """Update the data and regenerate picture."""
        self.data = data
        self._generate_picture()
        self.prepareGeometryChange()
        self.update()


class VolumeItem(pg.BarGraphItem):
    """Custom bar graph item for volume."""

    def __init__(self, data: pd.DataFrame):
        self.price_data = data
        x, heights, brushes = self._prepare_data(data)
        super().__init__(x=x, height=heights, width=0.6, brushes=brushes)

    def _prepare_data(self, data: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, List]:
        """Prepare volume data for rendering."""
        if data is None or data.empty:
            return np.array([]), np.array([]), []

        x = np.arange(len(data))
        # Replace NaN volumes with 0
        heights = np.nan_to_num(data["volume"].values.astype(float), nan=0.0)

        # Color based on price direction
        brushes = []
        green = pg.mkBrush("#22C55E80")
        red = pg.mkBrush("#EF444480")
        transparent = pg.mkBrush("#00000000")

        for _, row in data.iterrows():
            # Use transparent for NaN rows (future times)
            if pd.isna(row["close"]) or pd.isna(row["open"]):
                brushes.append(transparent)
            elif row["close"] >= row["open"]:
                brushes.append(green)
            else:
                brushes.append(red)

        return x, heights, brushes

    def set_data(self, data: pd.DataFrame) -> None:
        """Update volume data."""
        self.price_data = data
        x, heights, brushes = self._prepare_data(data)
        self.setOpts(x=x, height=heights, brushes=brushes)


class StockChart(QWidget):
    """
    Interactive stock chart with candlesticks, volume, and technical indicators.
    """

    # Period is now controlled externally by main window
    indicator_toggled = Signal(str, bool)

    TIMEFRAMES = ["1D", "1W", "1M", "3M", "6M", "YTD", "1Y", "2Y", "5Y"]
    CHART_TYPES = ["Candlestick", "OHLC", "Line", "Area"]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.config = get_config()
        self._data: Optional[pd.DataFrame] = None
        self._ticker: Optional[str] = None
        self._exchange: Optional[str] = None

        # Indicator states
        self._indicators: Dict[str, bool] = {
            "SMA 20": False,
            "SMA 50": False,
            "SMA 200": False,
            "EMA 12": False,
            "EMA 26": False,
            "Bollinger": False,
        }

        # Indicator plot items
        self._indicator_items: Dict[str, pg.PlotDataItem] = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the chart UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toolbar
        toolbar = self._create_toolbar()
        layout.addLayout(toolbar)

        # Chart area with splitter for main chart and volume
        splitter = QSplitter(Qt.Vertical)
        layout.addWidget(splitter, stretch=1)

        # Main price chart with custom ViewBox for measure mode
        self._viewbox = MeasureViewBox()
        self.price_widget = pg.PlotWidget(viewBox=self._viewbox)
        self._viewbox.setChart(self)  # Give ViewBox access to chart data
        self._viewbox.setMeasureMode(True)  # Default to measure mode
        self.price_widget.setBackground("#1F2937")
        self.price_widget.showGrid(x=True, y=True, alpha=0.3)
        self.price_widget.setLabel("left", "Price", units="$")
        self.price_plot = self.price_widget.getPlotItem()

        # Enable crosshair
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#6B7280", width=1))
        self.hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#6B7280", width=1))
        self.price_widget.addItem(self.vline, ignoreBounds=True)
        self.price_widget.addItem(self.hline, ignoreBounds=True)

        # Crosshair label - stays fixed in top-left of visible area
        self.crosshair_label = pg.TextItem(anchor=(0, 0), color="#F9FAFB")
        self.price_widget.addItem(self.crosshair_label, ignoreBounds=True)

        self.price_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

        # Update label position when view changes (zoom/pan)
        self.price_widget.getViewBox().sigRangeChanged.connect(self._update_label_position)

        splitter.addWidget(self.price_widget)

        # Volume chart
        self.volume_widget = pg.PlotWidget()
        self.volume_widget.setBackground("#1F2937")
        self.volume_widget.showGrid(x=True, y=True, alpha=0.3)
        self.volume_widget.setLabel("left", "Volume")
        self.volume_widget.setMaximumHeight(120)

        # Link X axes
        self.volume_widget.setXLink(self.price_widget)

        splitter.addWidget(self.volume_widget)

        # Set splitter sizes
        splitter.setSizes([400, 100])

        # Initialize chart items
        self.candle_item: Optional[CandlestickItem] = None
        self.ohlc_item: Optional[OHLCItem] = None
        self.volume_item: Optional[VolumeItem] = None

    def _create_toolbar(self) -> QHBoxLayout:
        """Create chart toolbar."""
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        # Stock info label
        self.ticker_label = QLabel("No stock selected")
        self.ticker_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #F9FAFB;
            }
        """)
        toolbar.addWidget(self.ticker_label)

        self.price_label = QLabel("")
        self.price_label.setStyleSheet("color: #9CA3AF;")
        toolbar.addWidget(self.price_label)

        toolbar.addStretch()

        # Chart type
        type_label = QLabel("Type:")
        toolbar.addWidget(type_label)

        self.chart_type_combo = QComboBox()
        self.chart_type_combo.addItems(self.CHART_TYPES)
        self.chart_type_combo.setCurrentText(self.config.ui.default_chart_type.title())
        self.chart_type_combo.currentTextChanged.connect(self._on_chart_type_changed)
        toolbar.addWidget(self.chart_type_combo)

        # Measure mode checkbox
        self.measure_checkbox = QCheckBox("Measure Period ")
        self.measure_checkbox.setToolTip("Drag to measure price range (right-click to clear)")
        self.measure_checkbox.setChecked(True)  # Default to enabled
        self.measure_checkbox.toggled.connect(self._on_measure_toggled)
        toolbar.addWidget(self.measure_checkbox)

        # Store current period (controlled by main window)
        self._current_period = self.config.ui.default_timeframe

        # Indicators button
        self.indicators_btn = QPushButton("Indicators")
        self.indicators_btn.clicked.connect(self._show_indicators_menu)
        toolbar.addWidget(self.indicators_btn)

        return toolbar

    def _show_indicators_menu(self) -> None:
        """Show indicators selection menu."""
        menu = QMenu(self)

        for name, enabled in self._indicators.items():
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(enabled)
            action.triggered.connect(lambda checked, n=name: self._toggle_indicator(n, checked))

        menu.exec(self.indicators_btn.mapToGlobal(self.indicators_btn.rect().bottomLeft()))

    def _toggle_indicator(self, name: str, enabled: bool) -> None:
        """Toggle an indicator on/off."""
        self._indicators[name] = enabled
        self._update_indicators()
        self.indicator_toggled.emit(name, enabled)

    def set_data(
        self,
        data: pd.DataFrame,
        ticker: str,
        exchange: str,
    ) -> None:
        """Set price data to display."""
        self._data = data.copy()
        self._ticker = ticker
        self._exchange = exchange

        # Update labels with date
        date_str = ""
        if not data.empty and hasattr(data.index[0], 'strftime'):
            # Get the date from the first data point
            first_dt = data.index[0]
            if hasattr(first_dt, 'date'):
                # Convert to ET for display
                first_dt_et = first_dt + ET_OFFSET
                date_str = f" - {first_dt_et.strftime('%b %d, %Y')}"
            elif hasattr(first_dt, 'strftime'):
                date_str = f" - {first_dt.strftime('%b %d, %Y')}"
        self.ticker_label.setText(f"{ticker}.{exchange}{date_str}")

        if not data.empty:
            last_price = data["close"].iloc[-1]
            prev_close = data["close"].iloc[-2] if len(data) > 1 else last_price
            change = (last_price - prev_close) / prev_close

            change_color = "#22C55E" if change >= 0 else "#EF4444"
            sign = "+" if change >= 0 else ""
            self.price_label.setText(
                f"${last_price:.2f} "
                f"<span style='color: {change_color};'>{sign}{change*100:.2f}%</span>"
            )

        self._update_chart()

    def _update_chart(self) -> None:
        """Update chart with current data."""
        if self._data is None or self._data.empty:
            return

        # Clear existing items
        self.price_widget.clear()
        self.volume_widget.clear()

        # Re-add crosshair
        self.price_widget.addItem(self.vline, ignoreBounds=True)
        self.price_widget.addItem(self.hline, ignoreBounds=True)
        self.price_widget.addItem(self.crosshair_label, ignoreBounds=True)

        chart_type = self.chart_type_combo.currentText()

        # Determine if this is intraday data (has DatetimeIndex with time component)
        is_intraday = isinstance(self._data.index, pd.DatetimeIndex) and len(self._data) > 100

        # Check if data is already aggregated (e.g., 15-min bars from 1W period)
        # If the interval between points is >= 5 min, don't resample
        needs_resample = is_intraday
        is_live_1d = False  # Live 1D data from data server (1-min bars, no resample needed)
        if is_intraday and len(self._data) >= 2:
            time_diff = (self._data.index[1] - self._data.index[0]).total_seconds()
            if time_diff >= 300:  # 5 minutes or more - already aggregated
                needs_resample = False
            elif time_diff < 120:  # 1-2 minute data from today = live data
                # Check if this is today's data (live 1D)
                today = pd.Timestamp.now().normalize()
                if self._data.index[-1].normalize() == today:
                    is_live_1d = True
                    needs_resample = False  # Use 1-min bars for live data

        if chart_type == "Candlestick":
            # For candlestick with 1-min intraday data, aggregate to 5-minute bars
            # Exception: live 1D data uses 1-min bars directly (already has delta volumes)
            if is_live_1d:
                # Live 1D data: make bars connect by setting open = previous close
                display_data = self._data.copy()
                # Shift close to get previous bar's close, use as current bar's open
                display_data['open'] = display_data['close'].shift(1)
                # First bar keeps its original open
                if len(display_data) > 0:
                    display_data.iloc[0, display_data.columns.get_loc('open')] = self._data.iloc[0]['open']
                # Set high/low to just open/close (no wicks)
                display_data['high'] = display_data[['open', 'close']].max(axis=1)
                display_data['low'] = display_data[['open', 'close']].min(axis=1)
                display_data = self._filter_volume_outliers_preserve_index(display_data)
            elif needs_resample:
                display_data = self._data.resample('5min').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'last'  # EODHD intraday volume is cumulative
                })
                # Convert cumulative volume to per-period volume
                if 'volume' in display_data.columns:
                    display_data['volume'] = display_data['volume'].diff().fillna(display_data['volume'].iloc[0] if len(display_data) > 0 else 0)
                    display_data['volume'] = display_data['volume'].clip(lower=0)  # No negative volumes
                # Don't dropna() - keep full day index with NaN for future times
                # Remove outlier volume bars (e.g., closing auction totals) only for valid data
                valid_data = display_data.dropna()
                if not valid_data.empty:
                    display_data = self._filter_volume_outliers_preserve_index(display_data)
            else:
                display_data = self._data
            self._display_data = display_data
            self.candle_item = CandlestickItem(display_data)
            self.price_widget.addItem(self.candle_item)
        elif chart_type == "OHLC":
            # For OHLC with 1-min intraday data, aggregate to 5-minute bars
            # Exception: live 1D data uses 1-min bars directly (already has delta volumes)
            if is_live_1d:
                # Live 1D data: make bars connect by setting open = previous close
                display_data = self._data.copy()
                # Shift close to get previous bar's close, use as current bar's open
                display_data['open'] = display_data['close'].shift(1)
                # First bar keeps its original open
                if len(display_data) > 0:
                    display_data.iloc[0, display_data.columns.get_loc('open')] = self._data.iloc[0]['open']
                # Set high/low to just open/close (no wicks)
                display_data['high'] = display_data[['open', 'close']].max(axis=1)
                display_data['low'] = display_data[['open', 'close']].min(axis=1)
                display_data = self._filter_volume_outliers_preserve_index(display_data)
            elif needs_resample:
                display_data = self._data.resample('5min').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'last'  # EODHD intraday volume is cumulative
                })
                # Convert cumulative volume to per-period volume
                if 'volume' in display_data.columns:
                    display_data['volume'] = display_data['volume'].diff().fillna(display_data['volume'].iloc[0] if len(display_data) > 0 else 0)
                    display_data['volume'] = display_data['volume'].clip(lower=0)  # No negative volumes
                # Don't dropna() - keep full day index with NaN for future times
                valid_data = display_data.dropna()
                if not valid_data.empty:
                    display_data = self._filter_volume_outliers_preserve_index(display_data)
            else:
                display_data = self._data
            self._display_data = display_data
            self.ohlc_item = OHLCItem(display_data)
            self.price_widget.addItem(self.ohlc_item)
        elif chart_type == "Line":
            # For line chart, use raw 1-minute data for detail
            display_data = self._data
            if is_intraday:
                display_data = self._filter_volume_outliers_preserve_index(display_data)
            self._display_data = display_data
            # Use connect='finite' to skip NaN values (future times)
            self.price_widget.plot(
                np.arange(len(display_data)),
                display_data["close"].values,
                pen=pg.mkPen("#3B82F6", width=2),
                connect='finite'
            )
        elif chart_type == "Area":
            # For area chart, use raw 1-minute data for detail
            display_data = self._data
            if is_intraday:
                display_data = self._filter_volume_outliers_preserve_index(display_data)
            self._display_data = display_data
            # Use connect='finite' to skip NaN values (future times)
            curve = self.price_widget.plot(
                np.arange(len(display_data)),
                display_data["close"].values,
                pen=pg.mkPen("#3B82F6", width=2),
                connect='finite'
            )
            fill = pg.FillBetweenItem(
                curve,
                pg.PlotDataItem(np.arange(len(display_data)), np.zeros(len(display_data))),
                brush=pg.mkBrush("#3B82F640")
            )
            self.price_widget.addItem(fill)
        else:
            self._display_data = self._data

        # Add volume using display data
        display_data = getattr(self, '_display_data', self._data)
        self.volume_item = VolumeItem(display_data)
        self.volume_widget.addItem(self.volume_item)

        # Update indicators
        self._update_indicators()

        # Set X axis to show dates
        self._setup_date_axis()

        # Auto-range price widget
        self.price_widget.autoRange()

        # Set volume Y-axis range explicitly (0 to max volume with padding)
        display_data = getattr(self, '_display_data', self._data)
        if "volume" in display_data.columns:
            max_vol = display_data["volume"].max(skipna=True)
            if pd.notna(max_vol) and max_vol > 0:
                self.volume_widget.setYRange(0, max_vol * 1.1, padding=0)
            self.volume_widget.setXRange(0, len(display_data) - 1, padding=0.02)

    def _update_indicators(self) -> None:
        """Update indicator overlays."""
        if self._data is None or self._data.empty:
            return

        # Remove existing indicator items
        for item in self._indicator_items.values():
            self.price_widget.removeItem(item)
        self._indicator_items.clear()

        x = np.arange(len(self._data))
        close = self._data["close"].values

        # SMA indicators
        sma_configs = [
            ("SMA 20", 20, "#F59E0B"),
            ("SMA 50", 50, "#8B5CF6"),
            ("SMA 200", 200, "#EC4899"),
        ]

        for name, period, color in sma_configs:
            if self._indicators.get(name) and len(close) >= period:
                sma = self._calculate_sma(close, period)
                item = self.price_widget.plot(
                    x, sma, pen=pg.mkPen(color, width=1.5), name=name
                )
                self._indicator_items[name] = item

        # EMA indicators
        ema_configs = [
            ("EMA 12", 12, "#06B6D4"),
            ("EMA 26", 26, "#10B981"),
        ]

        for name, period, color in ema_configs:
            if self._indicators.get(name) and len(close) >= period:
                ema = self._calculate_ema(close, period)
                item = self.price_widget.plot(
                    x, ema, pen=pg.mkPen(color, width=1.5), name=name
                )
                self._indicator_items[name] = item

        # Bollinger Bands
        if self._indicators.get("Bollinger") and len(close) >= 20:
            sma = self._calculate_sma(close, 20)
            std = pd.Series(close).rolling(20).std().values

            upper = sma + 2 * std
            lower = sma - 2 * std

            upper_item = self.price_widget.plot(
                x, upper, pen=pg.mkPen("#9CA3AF", width=1, style=Qt.DashLine)
            )
            lower_item = self.price_widget.plot(
                x, lower, pen=pg.mkPen("#9CA3AF", width=1, style=Qt.DashLine)
            )
            middle_item = self.price_widget.plot(
                x, sma, pen=pg.mkPen("#9CA3AF", width=1)
            )

            self._indicator_items["Bollinger_upper"] = upper_item
            self._indicator_items["Bollinger_lower"] = lower_item
            self._indicator_items["Bollinger_middle"] = middle_item

    def _calculate_sma(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Simple Moving Average."""
        return pd.Series(data).rolling(window=period).mean().values

    def _calculate_ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average."""
        return pd.Series(data).ewm(span=period, adjust=False).mean().values

    def _filter_volume_outliers(self, data: pd.DataFrame) -> pd.DataFrame:
        """Remove volume outliers that are likely closing auction/total volumes."""
        if data is None or data.empty or len(data) < 3:
            return data

        volumes = data["volume"].values
        median_vol = np.median(volumes)

        # If last bar volume is more than 5x the median, it's likely a total/auction bar
        if volumes[-1] > median_vol * 5:
            return data.iloc[:-1]

        return data

    def _filter_volume_outliers_preserve_index(self, data: pd.DataFrame) -> pd.DataFrame:
        """Filter volume outliers while preserving the full index (including NaN future times)."""
        if data is None or data.empty:
            return data

        # Get valid (non-NaN) data for outlier detection
        valid_mask = data["volume"].notna()
        valid_volumes = data.loc[valid_mask, "volume"].values

        if len(valid_volumes) < 3:
            return data

        median_vol = np.median(valid_volumes)

        # Find the last valid data point
        valid_indices = data.index[valid_mask]
        if len(valid_indices) == 0:
            return data

        last_valid_idx = valid_indices[-1]
        last_valid_volume = data.loc[last_valid_idx, "volume"]

        # If last valid bar volume is more than 5x the median, zero it out
        if last_valid_volume > median_vol * 5:
            data = data.copy()
            data.loc[last_valid_idx, "volume"] = 0

        return data

    def _setup_date_axis(self) -> None:
        """Setup date axis labels."""
        display_data = getattr(self, '_display_data', self._data)
        if display_data is None or display_data.empty:
            return

        # Create date strings for x-axis - handle various date formats
        if isinstance(display_data.index, pd.DatetimeIndex):
            dates = display_data.index
        elif "date" in display_data.columns:
            dates = pd.to_datetime(display_data["date"])
        else:
            # Index contains date objects
            dates = pd.to_datetime(display_data.index)

        # Create axis with date labels
        date_axis = self.price_widget.getAxis("bottom")

        # Show subset of dates to avoid crowding
        n_ticks = min(10, len(dates))
        step = max(1, len(dates) // n_ticks)

        ticks = []
        # Check if this is intraday data (has time component)
        is_intraday = isinstance(display_data.index, pd.DatetimeIndex) and len(dates) > 0
        if is_intraday:
            # Check if times vary (not just dates)
            first_time = dates[0]
            is_intraday = hasattr(first_time, 'hour') and hasattr(first_time, 'minute')

        if is_intraday:
            # Check if data spans multiple days
            first_date = dates[0].date() if hasattr(dates[0], 'date') else dates[0]
            last_date = dates[-1].date() if hasattr(dates[-1], 'date') else dates[-1]
            is_multi_day = first_date != last_date

            if is_multi_day:
                # For multi-day intraday (1W view), show date at start of each day
                daily_ticks = []
                last_date_shown = None
                for i, dt in enumerate(dates):
                    dt_et = dt + ET_OFFSET if hasattr(dt, '__add__') else dt
                    current_date = dt_et.date() if hasattr(dt_et, 'date') else dt_et
                    if current_date != last_date_shown:
                        date_str = dt_et.strftime("%b %d") if hasattr(dt_et, 'strftime') else str(current_date)[:5]
                        daily_ticks.append((i, date_str))
                        last_date_shown = current_date
                ticks = daily_ticks
            else:
                # For single day intraday, show hourly ticks starting from market open
                # Find indices that correspond to each hour (9:30, 10:30, 11:30, etc.)
                hourly_ticks = []
                last_hour = -1
                for i, dt in enumerate(dates):
                    # Convert to ET
                    dt_et = dt + ET_OFFSET
                    hour = dt_et.hour
                    minute = dt_et.minute
                    # Show tick at :30 of each hour (market opens at 9:30)
                    if minute >= 30 and hour != last_hour:
                        if hour >= 9 and hour <= 16:  # Market hours 9:30 AM - 4:00 PM
                            time_str = f"{hour}:30" if hour >= 10 else f"9:30"
                            hourly_ticks.append((i, time_str))
                            last_hour = hour
                ticks = hourly_ticks
        else:
            # Use year format for long periods (1Y, 2Y, 5Y)
            long_periods = ("1Y", "2Y", "5Y")
            use_year_format = getattr(self, '_current_period', '') in long_periods

            for i in range(0, len(dates), step):
                dt = dates[i]
                if hasattr(dt, 'strftime'):
                    if use_year_format:
                        ticks.append((i, dt.strftime("%b '%y")))  # e.g., "Jan '23"
                    else:
                        ticks.append((i, dt.strftime("%b %d")))
                else:
                    ticks.append((i, str(dt)[:10]))

        date_axis.setTicks([ticks])

    def _on_mouse_moved(self, pos) -> None:
        """Handle mouse movement for crosshair."""
        if self._data is None or self._data.empty:
            return

        mouse_point = self.price_widget.plotItem.vb.mapSceneToView(pos)
        x = int(mouse_point.x())

        display_data = getattr(self, '_display_data', self._data)
        if display_data is None:
            return

        if 0 <= x < len(display_data):
            self.vline.setPos(x)
            self.hline.setPos(mouse_point.y())

            row = display_data.iloc[x]

            # Get timestamp/date for display
            time_str = ""
            if hasattr(row, 'name'):
                dt = row.name
                if hasattr(dt, 'strftime'):
                    # Check if this is intraday data by looking at the time component
                    # Daily data has time at 00:00 or no time at all
                    has_time = hasattr(dt, 'hour') and (dt.hour != 0 or dt.minute != 0)

                    if has_time:
                        # Intraday data - show date and time in ET
                        dt_et = dt + ET_OFFSET
                        current_period = self._current_period
                        if current_period == "1D":
                            time_str = dt_et.strftime("%H:%M") + " ET  "
                        else:
                            # For 1W (hourly data), show date and time
                            time_str = dt_et.strftime("%b %d %H:%M") + " ET  "
                    else:
                        # Daily data - show date only
                        time_str = dt.strftime("%b %d, %Y") + "  "

            # Handle volume that might be NA
            vol = row.get('volume', 0)
            vol_str = f"{int(vol):,}" if pd.notna(vol) else "N/A"

            self.crosshair_label.setText(
                f"{time_str}O: {row['open']:.2f}  H: {row['high']:.2f}  "
                f"L: {row['low']:.2f}  C: {row['close']:.2f}  "
                f"V: {vol_str}"
            )
            # Position label in top-left of visible area
            self._update_label_position()

    def _update_label_position(self, *args) -> None:
        """Update crosshair label to stay in top-left of visible area."""
        view_range = self.price_widget.getViewBox().viewRange()
        if view_range:
            x_min = view_range[0][0]
            y_min = view_range[1][0]
            y_max = view_range[1][1]
            # Position at top-left with offset from top (5% of visible range)
            y_offset = (y_max - y_min) * 0.02
            self.crosshair_label.setPos(x_min + 0.5, y_max - y_offset)

    def _on_measure_toggled(self, enabled: bool) -> None:
        """Handle measure mode toggle."""
        self._viewbox.setMeasureMode(enabled)

    def _on_chart_type_changed(self, chart_type: str) -> None:
        """Handle chart type change."""
        self._update_chart()

    def set_period(self, period: str) -> None:
        """Set the chart period (called by main window)."""
        self._current_period = period

    def get_period(self) -> str:
        """Get the current period."""
        return self._current_period

    def clear(self) -> None:
        """Clear the chart."""
        self._data = None
        self._ticker = None
        self._exchange = None
        self._viewbox._clearMeasure()
        self.price_widget.clear()
        self.volume_widget.clear()
        self.ticker_label.setText("No stock selected")
        self.price_label.setText("")

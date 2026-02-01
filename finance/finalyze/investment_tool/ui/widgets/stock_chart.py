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
from PySide6.QtGui import QColor

import pyqtgraph as pg
import pandas as pd

from investment_tool.config.settings import get_config


# Configure pyqtgraph
pg.setConfigOptions(antialias=True, background="#1F2937", foreground="#F9FAFB")


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

        return pg.QtCore.QRectF(
            -1,
            self.data["low"].min(),
            len(self.data) + 1,
            self.data["high"].max() - self.data["low"].min()
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

        return pg.QtCore.QRectF(
            -1,
            self.data["low"].min(),
            len(self.data) + 1,
            self.data["high"].max() - self.data["low"].min()
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
        heights = data["volume"].values.astype(float)

        # Color based on price direction
        brushes = []
        green = pg.mkBrush("#22C55E80")
        red = pg.mkBrush("#EF444480")

        for _, row in data.iterrows():
            if row["close"] >= row["open"]:
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

    period_changed = Signal(str)
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

        # Main price chart
        self.price_widget = pg.PlotWidget()
        self.price_widget.setBackground("#1F2937")
        self.price_widget.showGrid(x=True, y=True, alpha=0.3)
        self.price_widget.setLabel("left", "Price", units="$")
        self.price_plot = self.price_widget.getPlotItem()

        # Enable crosshair
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#6B7280", width=1))
        self.hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#6B7280", width=1))
        self.price_widget.addItem(self.vline, ignoreBounds=True)
        self.price_widget.addItem(self.hline, ignoreBounds=True)

        # Crosshair label
        self.crosshair_label = pg.TextItem(anchor=(0, 0), color="#F9FAFB")
        self.price_widget.addItem(self.crosshair_label, ignoreBounds=True)

        self.price_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

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

        # Timeframe
        tf_label = QLabel("Period:")
        toolbar.addWidget(tf_label)

        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(self.TIMEFRAMES)
        self.timeframe_combo.setCurrentText(self.config.ui.default_timeframe)
        self.timeframe_combo.currentTextChanged.connect(self._on_timeframe_changed)
        toolbar.addWidget(self.timeframe_combo)

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

        if chart_type == "Candlestick":
            # For candlestick with intraday data, aggregate to 5-minute bars
            if is_intraday:
                display_data = self._data.resample('5min').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }).dropna()
                # Remove outlier volume bars (e.g., closing auction totals)
                display_data = self._filter_volume_outliers(display_data)
            else:
                display_data = self._data
            self._display_data = display_data
            self.candle_item = CandlestickItem(display_data)
            self.price_widget.addItem(self.candle_item)
        elif chart_type == "OHLC":
            # For OHLC with intraday data, aggregate to 5-minute bars
            if is_intraday:
                display_data = self._data.resample('5min').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }).dropna()
                # Remove outlier volume bars (e.g., closing auction totals)
                display_data = self._filter_volume_outliers(display_data)
            else:
                display_data = self._data
            self._display_data = display_data
            self.ohlc_item = OHLCItem(display_data)
            self.price_widget.addItem(self.ohlc_item)
        elif chart_type == "Line":
            # For line chart, use raw 1-minute data for detail
            display_data = self._data
            if is_intraday:
                display_data = self._filter_volume_outliers(display_data)
            self._display_data = display_data
            self.price_widget.plot(
                np.arange(len(display_data)),
                display_data["close"].values,
                pen=pg.mkPen("#3B82F6", width=2)
            )
        elif chart_type == "Area":
            # For area chart, use raw 1-minute data for detail
            display_data = self._data
            if is_intraday:
                display_data = self._filter_volume_outliers(display_data)
            self._display_data = display_data
            curve = self.price_widget.plot(
                np.arange(len(display_data)),
                display_data["close"].values,
                pen=pg.mkPen("#3B82F6", width=2)
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
            max_vol = display_data["volume"].max()
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
            for i in range(0, len(dates), step):
                dt = dates[i]
                if hasattr(dt, 'strftime'):
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
                        current_period = self.timeframe_combo.currentText()
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
            self.crosshair_label.setPos(0, display_data["high"].max())

    def _on_chart_type_changed(self, chart_type: str) -> None:
        """Handle chart type change."""
        self._update_chart()

    def _on_timeframe_changed(self, timeframe: str) -> None:
        """Handle timeframe change."""
        self.period_changed.emit(timeframe)

    def clear(self) -> None:
        """Clear the chart."""
        self._data = None
        self._ticker = None
        self._exchange = None
        self.price_widget.clear()
        self.volume_widget.clear()
        self.ticker_label.setText("No stock selected")
        self.price_label.setText("")

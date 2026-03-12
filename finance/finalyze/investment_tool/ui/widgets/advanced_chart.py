"""Advanced full-screen chart widget with benchmark comparison, inflation adjustment,
growth/fall phase detection, and moving averages."""

from typing import Optional, List, Dict
import numpy as np

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QCheckBox,
    QLabel,
    QSplitter,
    QSizePolicy,
    QMenu,
    QToolButton,
)
from PySide6.QtGui import QColor, QFont, QAction

import pyqtgraph as pg
import pandas as pd
from loguru import logger


# Configure pyqtgraph (matches stock_chart.py)
pg.setConfigOptions(antialias=True, background="#1F2937", foreground="#F9FAFB")


class MeasureViewBox(pg.ViewBox):
    """ViewBox that draws a measure line on drag instead of zooming/panning.

    Left-drag draws a line between two points showing price change.
    Right-click clears the measure. Scroll wheel still zooms.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._measure_mode = True
        self._measure_line = None
        self._measure_label = None
        self._chart = None
        self.setMenuEnabled(False)
        # Disable drag-based pan/zoom — keep scroll zoom
        self.setMouseEnabled(x=False, y=False)

    def setChart(self, chart: "AdvancedChartWidget") -> None:
        self._chart = chart

    def setMeasureMode(self, enabled: bool) -> None:
        """Toggle between measure mode (draw line) and pan mode."""
        self._measure_mode = enabled
        if enabled:
            self.setMouseEnabled(x=False, y=False)
        else:
            self.setMouseEnabled(x=True, y=True)
            self._clearMeasure()

    def _clearMeasure(self) -> None:
        if self._measure_line is not None:
            self.removeItem(self._measure_line)
            self._measure_line = None
        if self._measure_label is not None:
            self.removeItem(self._measure_label)
            self._measure_label = None

    def mouseDragEvent(self, ev, axis=None):
        if not self._measure_mode:
            super().mouseDragEvent(ev, axis)
            return

        if ev.button() != Qt.LeftButton:
            ev.ignore()
            return

        ev.accept()
        start = self.mapSceneToView(ev.buttonDownScenePos())
        current = self.mapSceneToView(ev.scenePos())
        self._drawMeasure(start.x(), start.y(), current.x(), current.y())

    def mouseClickEvent(self, ev):
        if self._measure_mode and ev.button() == Qt.RightButton:
            self._clearMeasure()
            ev.accept()
        else:
            super().mouseClickEvent(ev)

    def wheelEvent(self, ev, axis=None):
        if self._measure_mode:
            # Temporarily enable mouse for scroll-wheel zoom
            self.setMouseEnabled(x=True, y=True)
            super().wheelEvent(ev, axis)
            self.setMouseEnabled(x=False, y=False)
        else:
            super().wheelEvent(ev, axis)

    def _drawMeasure(self, x1, y1, x2, y2):
        if self._chart is None or not hasattr(self._chart, "_plot_close"):
            return

        self._clearMeasure()

        close = self._chart._plot_close
        dates = self._chart._plot_dates
        max_idx = len(close) - 1

        # Use the actual drawn Y values (percentage) to derive prices
        base_price = close[0]
        price1 = base_price * (1 + y1 / 100)
        price2 = base_price * (1 + y2 / 100)
        diff = price2 - price1
        pct = (diff / price1 * 100) if price1 != 0 else 0

        # Time span + CAGR from X positions
        idx1 = max(0, min(int(round(x1)), max_idx))
        idx2 = max(0, min(int(round(x2)), max_idx))
        time_str = ""
        cagr_str = ""
        try:
            t1, t2 = dates[idx1], dates[idx2]
            td = abs(t2 - t1)
            days = td.days if hasattr(td, "days") else int(td.total_seconds() // 86400) if hasattr(td, "total_seconds") else abs(idx2 - idx1)
            if days > 0:
                time_str = f"  ({days}d)"
                if price1 > 0 and price2 > 0:
                    cagr = (price2 / price1) ** (365.25 / days) - 1
                    cagr_sign = "+" if cagr >= 0 else ""
                    cagr_str = f"  {cagr_sign}{cagr * 100:.1f}%/yr"
            else:
                time_str = f"  ({abs(idx2 - idx1)} bars)"
        except Exception:
            pass

        # Color
        if diff >= 0:
            line_color = QColor(34, 197, 94)   # green
        else:
            line_color = QColor(239, 68, 68)   # red

        # Draw line from start to end
        self._measure_line = pg.PlotCurveItem(
            [x1, x2], [y1, y2],
            pen=pg.mkPen(line_color, width=2, style=Qt.DashLine),
        )
        self.addItem(self._measure_line, ignoreBounds=True)

        # Label at midpoint
        sign = "+" if diff >= 0 else ""
        text = f"${price1:.2f} → ${price2:.2f}  {sign}${diff:.2f} ({sign}{pct:.1f}%){cagr_str}{time_str}"
        self._measure_label = pg.TextItem(text, color="#F9FAFB", anchor=(0.5, 1.2))
        self._measure_label.setFont(QFont("monospace", 10))
        self._measure_label.setPos((x1 + x2) / 2, (y1 + y2) / 2)
        self.addItem(self._measure_label, ignoreBounds=True)


class AdvancedChartWidget(QWidget):
    """
    Advanced chart with percentage-normalized overlays, benchmarks,
    inflation adjustment, growth/fall phases, and moving averages.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._data: Optional[pd.DataFrame] = None
        self._ticker: Optional[str] = None
        self._exchange: Optional[str] = None
        self._current_period: str = "1Y"

        # Benchmark data caches
        self._sp500_data: Optional[pd.DataFrame] = None
        self._gold_data: Optional[pd.DataFrame] = None
        self._cpi_data: Optional[pd.DataFrame] = None

        # Data manager reference (set externally)
        self._data_manager = None

        # Toggle states
        self._show_sp500 = False
        self._show_gold = False
        self._show_inflation = False
        self._phase_method: Optional[str] = None  # None, "sma60", "sma120", "macd", "ma200"
        self._show_ma30 = False
        self._show_ma60 = False
        self._show_ma120 = False

        # Plot items for cleanup
        self._overlay_items: List = []
        self._phase_items: List = []
        self._legend_items: List = []
        self._returns_label = None

        self._setup_ui()

    def set_data_manager(self, manager) -> None:
        """Set the data manager for fetching benchmark data."""
        self._data_manager = manager

    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Controls toolbar
        controls = QHBoxLayout()
        controls.setSpacing(6)

        # Ticker label
        self.ticker_label = QLabel("No stock selected")
        self.ticker_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #F9FAFB;")
        controls.addWidget(self.ticker_label)

        controls.addSpacing(16)

        # Benchmark toggles
        bench_label = QLabel("Benchmark:")
        bench_label.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        controls.addWidget(bench_label)

        self.sp500_btn = self._make_toggle("S&P 500", "#06B6D4")
        self.sp500_btn.toggled.connect(self._on_sp500_toggled)
        controls.addWidget(self.sp500_btn)

        self.gold_btn = self._make_toggle("Gold", "#F59E0B")
        self.gold_btn.toggled.connect(self._on_gold_toggled)
        controls.addWidget(self.gold_btn)

        controls.addSpacing(12)

        # Analysis toggles
        analysis_label = QLabel("Analysis:")
        analysis_label.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        controls.addWidget(analysis_label)

        self.inflation_btn = self._make_toggle("Inflation-Adj", "#A78BFA")
        self.inflation_btn.toggled.connect(self._on_inflation_toggled)
        controls.addWidget(self.inflation_btn)

        # Phases dropdown menu button
        self.phases_btn = QToolButton()
        self.phases_btn.setText("Phases")
        self.phases_btn.setFixedHeight(24)
        self.phases_btn.setPopupMode(QToolButton.InstantPopup)
        self.phases_btn.setStyleSheet("""
            QToolButton {
                background-color: #374151;
                color: #9CA3AF;
                border: 1px solid #4B5563;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }
            QToolButton:hover {
                background-color: #4B5563;
            }
            QToolButton::menu-indicator { image: none; }
        """)
        phases_menu = QMenu(self.phases_btn)
        self._phase_actions: Dict[str, QAction] = {}
        for key, label in [
            ("sma60", "SMA 60-day"),
            ("sma120", "SMA 120-day"),
            ("macd", "MACD Crossover"),
            ("ma200", "Price vs MA 200"),
        ]:
            action = phases_menu.addAction(label)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, k=key: self._on_phase_selected(k, checked))
            self._phase_actions[key] = action
        self.phases_btn.setMenu(phases_menu)
        controls.addWidget(self.phases_btn)

        controls.addSpacing(12)

        # MA toggles
        ma_label = QLabel("MA:")
        ma_label.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        controls.addWidget(ma_label)

        self.ma30_btn = self._make_toggle("30", "#F59E0B")
        self.ma30_btn.toggled.connect(self._on_ma30_toggled)
        controls.addWidget(self.ma30_btn)

        self.ma60_btn = self._make_toggle("60", "#8B5CF6")
        self.ma60_btn.toggled.connect(self._on_ma60_toggled)
        controls.addWidget(self.ma60_btn)

        self.ma120_btn = self._make_toggle("120", "#EC4899")
        self.ma120_btn.toggled.connect(self._on_ma120_toggled)
        controls.addWidget(self.ma120_btn)

        controls.addSpacing(12)

        # Measure mode checkbox
        self.measure_checkbox = QCheckBox("Measure")
        self.measure_checkbox.setToolTip("Drag to measure price range (right-click to clear). Uncheck to pan/zoom.")
        self.measure_checkbox.setChecked(True)
        self.measure_checkbox.toggled.connect(self._on_measure_toggled)
        controls.addWidget(self.measure_checkbox)

        controls.addStretch()

        layout.addLayout(controls)

        # Chart splitter (price + volume)
        splitter = QSplitter(Qt.Vertical)

        # Price chart with measure-line ViewBox
        self._viewbox = MeasureViewBox()
        self._viewbox.setChart(self)
        self.price_widget = pg.PlotWidget(viewBox=self._viewbox)
        self.price_widget.showGrid(x=True, y=True, alpha=0.15)
        self.price_widget.setLabel("left", "Change %")
        self.price_widget.getAxis("bottom").setStyle(showValues=False)

        # Crosshair
        self._vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#6B7280", width=1, style=Qt.DashLine))
        self._hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#6B7280", width=1, style=Qt.DashLine))
        self.price_widget.addItem(self._vline, ignoreBounds=True)
        self.price_widget.addItem(self._hline, ignoreBounds=True)

        # Crosshair label
        self._crosshair_label = pg.TextItem(anchor=(0, 0), color="#F9FAFB")
        self._crosshair_label.setFont(QFont("Segoe UI", 10))
        self.price_widget.addItem(self._crosshair_label, ignoreBounds=True)

        self.price_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

        splitter.addWidget(self.price_widget)

        # Volume chart
        self.volume_widget = pg.PlotWidget()
        self.volume_widget.showGrid(x=True, y=False, alpha=0.15)
        self.volume_widget.setLabel("left", "Volume")
        self.volume_widget.getAxis("bottom").setStyle(showValues=False)
        self.volume_widget.getViewBox().setMenuEnabled(False)
        self.volume_widget.setMaximumHeight(120)

        # Link X axes
        self.volume_widget.setXLink(self.price_widget)

        splitter.addWidget(self.volume_widget)

        splitter.setSizes([500, 120])
        layout.addWidget(splitter, stretch=1)

    def _make_toggle(self, text: str, color: str) -> QPushButton:
        """Create a toggle button with consistent styling."""
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setFixedHeight(24)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #374151;
                color: #9CA3AF;
                border: 1px solid #4B5563;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            QPushButton:checked {{
                background-color: {color};
                color: #FFFFFF;
                border-color: {color};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #4B5563;
            }}
        """)
        return btn

    # ---- Public API ----

    def set_data(self, data: pd.DataFrame, ticker: str, exchange: str, visible_start=None) -> None:
        """Set price data to display.

        Args:
            visible_start: If provided, data before this date is used only for
                           MA warmup and not displayed on the chart.
        """
        if data is None or data.empty:
            self.clear()
            return

        self._data = data.copy()
        self._ticker = ticker
        self._exchange = exchange
        self._visible_start = visible_start

        # Clear benchmark caches when stock changes
        self._sp500_data = None
        self._gold_data = None
        self._cpi_data = None

        self.ticker_label.setText(f"{ticker}.{exchange}")
        self._redraw()

    def set_period(self, period: str) -> None:
        """Set the chart period."""
        self._current_period = period

    def get_period(self) -> str:
        """Get the current period."""
        return self._current_period

    def clear(self) -> None:
        """Clear the chart."""
        self._data = None
        self._ticker = None
        self._exchange = None
        self._clear_overlays()
        self._viewbox._clearMeasure()
        self.price_widget.clear()
        self.volume_widget.clear()
        # Re-apply axis settings (clear() can remove them)
        self.price_widget.setLabel("left", "Change %")
        self.price_widget.getAxis("bottom").setStyle(showValues=False)
        self.volume_widget.setLabel("left", "Volume")
        self.volume_widget.getAxis("bottom").setStyle(showValues=False)
        # Re-add crosshair items
        self.price_widget.addItem(self._vline, ignoreBounds=True)
        self.price_widget.addItem(self._hline, ignoreBounds=True)
        self.price_widget.addItem(self._crosshair_label, ignoreBounds=True)
        self.ticker_label.setText("No stock selected")

    # ---- Toggle handlers ----

    def _on_sp500_toggled(self, checked: bool) -> None:
        self._show_sp500 = checked
        self._redraw()

    def _on_gold_toggled(self, checked: bool) -> None:
        self._show_gold = checked
        self._redraw()

    def _on_inflation_toggled(self, checked: bool) -> None:
        self._show_inflation = checked
        self._redraw()

    def _on_phase_selected(self, method: str, checked: bool) -> None:
        """Handle phase method selection (radio-like: only one active at a time)."""
        if checked:
            self._phase_method = method
            # Uncheck other phase actions
            for key, action in self._phase_actions.items():
                if key != method:
                    action.setChecked(False)
            # Update button appearance to show active
            self.phases_btn.setStyleSheet("""
                QToolButton {
                    background-color: #34D399;
                    color: #FFFFFF;
                    border: 1px solid #34D399;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QToolButton:hover { background-color: #2EB886; }
                QToolButton::menu-indicator { image: none; }
            """)
        else:
            self._phase_method = None
            self.phases_btn.setStyleSheet("""
                QToolButton {
                    background-color: #374151;
                    color: #9CA3AF;
                    border: 1px solid #4B5563;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 11px;
                }
                QToolButton:hover { background-color: #4B5563; }
                QToolButton::menu-indicator { image: none; }
            """)
        self._redraw()

    def _on_ma30_toggled(self, checked: bool) -> None:
        self._show_ma30 = checked
        self._redraw()

    def _on_ma60_toggled(self, checked: bool) -> None:
        self._show_ma60 = checked
        self._redraw()

    def _on_ma120_toggled(self, checked: bool) -> None:
        self._show_ma120 = checked
        self._redraw()

    def _on_measure_toggled(self, checked: bool) -> None:
        """Toggle between measure mode and pan mode."""
        self._viewbox.setMeasureMode(checked)

    # ---- Drawing ----

    def _clear_overlays(self) -> None:
        """Remove all overlay plot items."""
        for item in self._overlay_items:
            try:
                self.price_widget.removeItem(item)
            except Exception:
                pass
        self._overlay_items.clear()

        for item in self._phase_items:
            try:
                self.price_widget.removeItem(item)
            except Exception:
                pass
        self._phase_items.clear()

        for item in self._legend_items:
            try:
                self.price_widget.removeItem(item)
            except Exception:
                pass
        self._legend_items.clear()

    def _redraw(self) -> None:
        """Redraw the entire chart with current data and toggle states."""
        if self._data is None or self._data.empty:
            return

        self._viewbox._clearMeasure()
        self.price_widget.clear()
        self.volume_widget.clear()
        self._overlay_items.clear()
        self._phase_items.clear()
        self._legend_items.clear()
        self._benchmark_cagrs: List[tuple] = []  # [(label, color, cagr)]

        # Re-apply axis settings (clear() can remove them)
        y_label = "Inflation-Adj %" if self._show_inflation else "Change %"
        self.price_widget.setLabel("left", y_label)
        self.price_widget.getAxis("bottom").setStyle(showValues=False)
        self.volume_widget.setLabel("left", "Volume")
        self.volume_widget.getAxis("bottom").setStyle(showValues=False)

        # Re-add crosshair
        self.price_widget.addItem(self._vline, ignoreBounds=True)
        self.price_widget.addItem(self._hline, ignoreBounds=True)
        self.price_widget.addItem(self._crosshair_label, ignoreBounds=True)

        full_data = self._data.copy()
        full_data = full_data.dropna(subset=["close"])
        if full_data.empty:
            return

        full_close = full_data["close"].values.astype(float)

        # Apply inflation adjustment if enabled
        if self._show_inflation:
            full_close = self._apply_inflation_adjustment(full_data, full_close)

        # Determine visible range (trim warmup data used for MA computation)
        vis_start = 0
        if hasattr(self, "_visible_start") and self._visible_start is not None:
            for i, idx in enumerate(full_data.index):
                idx_date = idx.date() if hasattr(idx, "date") else idx
                vs = self._visible_start.date() if hasattr(self._visible_start, "date") else self._visible_start
                if idx_date >= vs:
                    vis_start = i
                    break

        # Visible slice for display
        data = full_data.iloc[vis_start:]
        close = full_close[vis_start:]

        # Percentage normalize from visible start
        x = np.arange(len(data))
        pct = (close / close[0] - 1) * 100

        # Store for crosshair
        self._plot_x = x
        self._plot_dates = data.index
        self._plot_close = close
        self._plot_pct = pct

        # Primary stock line
        pen = pg.mkPen("#FFFFFF", width=2)
        curve = self.price_widget.plot(x, pct, pen=pen, name=self._ticker)
        self._overlay_items.append(curve)

        # Volume bars
        self._draw_volume(data, x)

        # Benchmarks
        if self._show_sp500:
            self._draw_benchmark("GSPC", "INDX", "#06B6D4", "S&P 500", data)
        if self._show_gold:
            self._draw_benchmark("GLD", "US", "#F59E0B", "Gold", data)

        # Moving averages — compute on full data, display only the visible slice
        if self._show_ma30 and len(full_close) >= 30:
            self._draw_ma(x, full_close, vis_start, 30, "#F59E0B", close[0])
        if self._show_ma60 and len(full_close) >= 60:
            self._draw_ma(x, full_close, vis_start, 60, "#8B5CF6", close[0])
        if self._show_ma120 and len(full_close) >= 120:
            self._draw_ma(x, full_close, vis_start, 120, "#EC4899", close[0])

        # Growth/Fall phases
        if self._phase_method:
            self._draw_phases(x, pct, close, self._phase_method)

        # Annualized return legend
        self._draw_returns_legend(data, close)

        # Auto-range and position legend
        self.price_widget.autoRange()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._position_returns_legend)

    def _draw_volume(self, data: pd.DataFrame, x: np.ndarray) -> None:
        """Draw volume bars in the volume sub-chart."""
        if "volume" not in data.columns:
            return

        volumes = np.nan_to_num(data["volume"].values.astype(float), nan=0.0)

        # Color based on price direction
        brushes = []
        green = pg.mkBrush("#22C55E80")
        red = pg.mkBrush("#EF444480")

        closes = data["close"].values
        opens = data["open"].values if "open" in data.columns else closes

        for i in range(len(data)):
            c = closes[i]
            o = opens[i]
            if pd.isna(c) or pd.isna(o):
                brushes.append(pg.mkBrush("#00000000"))
            elif c >= o:
                brushes.append(green)
            else:
                brushes.append(red)

        bar_item = pg.BarGraphItem(x=x, height=volumes, width=0.6, brushes=brushes)
        self.volume_widget.addItem(bar_item)

    def _draw_benchmark(
        self, ticker: str, exchange: str, color: str, label: str, stock_data: pd.DataFrame,
    ) -> None:
        """Fetch and draw a benchmark overlay (percentage-normalized).

        If inflation adjustment is active, it is applied to the benchmark too.
        """
        if not self._data_manager:
            return

        try:
            # Use the same date range as the stock
            dates = stock_data.index
            start = dates.min()
            end = dates.max()

            # Convert to date objects
            if hasattr(start, "date"):
                start_date = start.date()
            else:
                start_date = pd.Timestamp(str(start)).date()
            if hasattr(end, "date"):
                end_date = end.date()
            else:
                end_date = pd.Timestamp(str(end)).date()

            # Fetch benchmark daily prices
            bench = self._data_manager.get_daily_prices(ticker, exchange, start_date, end_date)
            if bench is None or bench.empty:
                logger.warning(f"No benchmark data for {ticker}.{exchange}")
                return

            bench = bench.dropna(subset=["close"])
            if bench.empty:
                return

            bench_close = bench["close"].values.astype(float)

            # Apply inflation adjustment to benchmark if enabled
            if self._show_inflation:
                bench_close = self._apply_inflation_adjustment(bench, bench_close)

            bench_pct = (bench_close / bench_close[0] - 1) * 100

            # Map benchmark dates to stock x-axis positions
            # Create a mapping from stock date to x position
            stock_date_to_x = {}
            for i, d in enumerate(stock_data.index):
                date_key = d.date() if hasattr(d, "date") else pd.Timestamp(str(d)).date()
                stock_date_to_x[date_key] = i

            # Build aligned arrays
            bench_x = []
            bench_y = []
            for i, d in enumerate(bench.index):
                date_key = d.date() if hasattr(d, "date") else pd.Timestamp(str(d)).date()
                if date_key in stock_date_to_x:
                    bench_x.append(stock_date_to_x[date_key])
                    bench_y.append(bench_pct[i])

            if bench_x:
                pen = pg.mkPen(color, width=1.5, style=Qt.DashLine)
                curve = self.price_widget.plot(
                    np.array(bench_x), np.array(bench_y),
                    pen=pen, name=label,
                )
                self._overlay_items.append(curve)

                # Store benchmark CAGR for legend
                if len(bench_close) >= 2:
                    bench_dates = bench.index
                    td = bench_dates[-1] - bench_dates[0]
                    days = td.days if hasattr(td, "days") else abs(len(bench_close))
                    if days > 0 and bench_close[0] > 0:
                        cagr = (bench_close[-1] / bench_close[0]) ** (365.25 / days) - 1
                        self._benchmark_cagrs.append((label, color, cagr))

        except Exception as e:
            logger.warning(f"Failed to draw benchmark {ticker}: {e}")

    def _draw_ma(self, x: np.ndarray, full_close: np.ndarray, vis_start: int, period: int, color: str, base_price: float) -> None:
        """Draw a moving average line (percentage-normalized).

        Computes MA on full_close (includes warmup data), then trims to the
        visible range starting at vis_start so the MA line has no NaN gaps.
        """
        sma_full = pd.Series(full_close).rolling(window=period).mean().values
        sma = sma_full[vis_start:]
        sma_pct = (sma / base_price - 1) * 100

        pen = pg.mkPen(color, width=1.5)
        curve = self.price_widget.plot(x, sma_pct, pen=pen, name=f"MA {period}")
        self._overlay_items.append(curve)

    def _draw_phases(self, x: np.ndarray, pct: np.ndarray, close: np.ndarray, method: str) -> None:
        """Detect and draw growth/fall phases using the selected method."""
        phases = self._detect_phases(close, method)

        for phase in phases:
            start_idx = phase["start_idx"]
            end_idx = phase["end_idx"]
            is_growth = phase["phase"] == "growth"

            # Shaded region
            color = QColor("#22C55E") if is_growth else QColor("#EF4444")
            color.setAlpha(30)

            region = pg.LinearRegionItem(
                values=[start_idx, end_idx],
                orientation=pg.LinearRegionItem.Vertical,
                brush=pg.mkBrush(color),
                movable=False,
            )
            region.setZValue(-10)
            for line in region.lines:
                line.setPen(pg.mkPen(None))
            self.price_widget.addItem(region)
            self._phase_items.append(region)

            # Trend line through phase
            phase_x = x[start_idx:end_idx + 1]
            phase_y = pct[start_idx:end_idx + 1]
            if len(phase_x) >= 2:
                coeffs = np.polyfit(phase_x, phase_y, 1)
                trend_y = np.polyval(coeffs, phase_x)

                trend_color = "#22C55E" if is_growth else "#EF4444"
                pen = pg.mkPen(trend_color, width=2.5)
                curve = self.price_widget.plot(phase_x, trend_y, pen=pen)
                self._phase_items.append(curve)

                # Annualized return label at trend line midpoint
                p_start = close[start_idx]
                p_end = close[end_idx]
                if hasattr(self, "_plot_dates") and len(self._plot_dates) > end_idx:
                    td = self._plot_dates[end_idx] - self._plot_dates[start_idx]
                    days = td.days if hasattr(td, "days") else (end_idx - start_idx)
                else:
                    days = end_idx - start_idx
                if days > 0 and p_start > 0:
                    cagr = (p_end / p_start) ** (365.25 / days) - 1
                    cagr_sign = "+" if cagr >= 0 else ""
                    label = pg.TextItem(
                        f"{cagr_sign}{cagr * 100:.1f}%/yr",
                        color=trend_color,
                        anchor=(0.5, 1.2),
                    )
                    label.setFont(QFont("Segoe UI", 9))
                    mid_i = len(phase_x) // 2
                    label.setPos(phase_x[mid_i], trend_y[mid_i])
                    self.price_widget.addItem(label, ignoreBounds=True)
                    self._phase_items.append(label)

    def _draw_returns_legend(self, data: pd.DataFrame, close: np.ndarray) -> None:
        """Draw annualized return (CAGR) labels for all visible lines."""
        lines = []

        # Stock CAGR
        if len(close) >= 2:
            dates = data.index
            td = dates[-1] - dates[0]
            days = td.days if hasattr(td, "days") else len(close)
            if days > 0 and close[0] > 0:
                cagr = (close[-1] / close[0]) ** (365.25 / days) - 1
                sign = "+" if cagr >= 0 else ""
                lines.append(f'<span style="color:#FFFFFF">{self._ticker}: {sign}{cagr * 100:.1f}%/yr</span>')

        # Benchmark CAGRs
        for blabel, color, cagr in self._benchmark_cagrs:
            sign = "+" if cagr >= 0 else ""
            lines.append(f'<span style="color:{color}">{blabel}: {sign}{cagr * 100:.1f}%/yr</span>')

        if not lines:
            return

        html = "<br>".join(lines)
        self._returns_label = pg.TextItem(html=html, anchor=(1, 0))
        self._returns_label.setFont(QFont("Segoe UI", 10))
        self.price_widget.addItem(self._returns_label, ignoreBounds=True)
        self._legend_items.append(self._returns_label)

    def _position_returns_legend(self) -> None:
        """Position the returns legend in the top-right corner of the chart."""
        if hasattr(self, "_returns_label") and self._returns_label is not None:
            vr = self.price_widget.plotItem.vb.viewRange()
            self._returns_label.setPos(vr[0][1], vr[1][1])

    def _detect_phases(self, close: np.ndarray, method: str) -> List[Dict]:
        """Detect growth/fall phases using the specified method.

        Methods:
            sma60/sma120 — smoothed derivative sign changes
            macd — MACD(12,26) line crossing signal(9) line
            ma200 — price above/below 200-day moving average
        """
        if method in ("sma60", "sma120"):
            window = 60 if method == "sma60" else 120
            return self._detect_phases_sma(close, window)
        elif method == "macd":
            return self._detect_phases_macd(close)
        elif method == "ma200":
            return self._detect_phases_ma200(close)
        return []

    def _detect_phases_sma(self, close: np.ndarray, smooth_window: int) -> List[Dict]:
        """Detect phases via smoothed derivative sign changes."""
        if len(close) < smooth_window + 2:
            return []

        smoothed = pd.Series(close).rolling(smooth_window, min_periods=1).mean().values
        diff = np.diff(smoothed)

        signs = np.sign(diff)
        for i in range(1, len(signs)):
            if signs[i] == 0:
                signs[i] = signs[i - 1]

        sign_changes = np.where(np.diff(signs) != 0)[0]
        boundaries = [0] + (sign_changes + 1).tolist() + [len(close) - 1]

        phases = []
        for i in range(len(boundaries) - 1):
            s, e = boundaries[i], boundaries[i + 1]
            if e - s < 3:
                continue
            mid = (s + e) // 2
            direction = "growth" if (mid < len(diff) and diff[mid] > 0) else (
                "growth" if close[e] > close[s] else "fall"
            )
            phases.append({"start_idx": s, "end_idx": e, "phase": direction})
        return phases

    def _detect_phases_macd(self, close: np.ndarray) -> List[Dict]:
        """Detect phases via MACD(12,26) crossing signal(9) line."""
        if len(close) < 35:
            return []

        s = pd.Series(close)
        ema12 = s.ewm(span=12, adjust=False).mean().values
        ema26 = s.ewm(span=26, adjust=False).mean().values
        macd_line = ema12 - ema26
        signal_line = pd.Series(macd_line).ewm(span=9, adjust=False).mean().values

        # Phase = growth when MACD > signal, fall when MACD < signal
        above = macd_line > signal_line

        phases = []
        start_idx = 0
        current_phase = "growth" if above[0] else "fall"

        for i in range(1, len(close)):
            new_phase = "growth" if above[i] else "fall"
            if new_phase != current_phase:
                if i - start_idx >= 3:
                    phases.append({"start_idx": start_idx, "end_idx": i, "phase": current_phase})
                start_idx = i
                current_phase = new_phase

        if len(close) - start_idx >= 3:
            phases.append({"start_idx": start_idx, "end_idx": len(close) - 1, "phase": current_phase})
        return phases

    def _detect_phases_ma200(self, close: np.ndarray) -> List[Dict]:
        """Detect phases based on price position relative to 200-day MA."""
        window = min(200, len(close) // 2)
        if window < 10:
            return []

        ma = pd.Series(close).rolling(window, min_periods=1).mean().values
        above = close > ma

        phases = []
        start_idx = 0
        current_phase = "growth" if above[0] else "fall"

        for i in range(1, len(close)):
            new_phase = "growth" if above[i] else "fall"
            if new_phase != current_phase:
                if i - start_idx >= 3:
                    phases.append({"start_idx": start_idx, "end_idx": i, "phase": current_phase})
                start_idx = i
                current_phase = new_phase

        if len(close) - start_idx >= 3:
            phases.append({"start_idx": start_idx, "end_idx": len(close) - 1, "phase": current_phase})
        return phases

    def _apply_inflation_adjustment(self, data: pd.DataFrame, close: np.ndarray) -> np.ndarray:
        """Apply inflation adjustment to prices.

        Uses CPI data from FRED if available, otherwise falls back to a
        fixed 3% annual rate estimate.
        """
        dates = data.index
        end = dates.max()

        # Try CPI data from FRED first
        if self._data_manager:
            try:
                start = dates.min()
                start_str = start.date().isoformat() if hasattr(start, "date") else str(start)[:10]
                end_str = end.date().isoformat() if hasattr(end, "date") else str(end)[:10]

                from investment_tool.config.settings import get_config
                cpi_series = get_config().analysis.cpi_series
                cpi_data = self._data_manager.get_cpi_data(start_str, end_str, series=cpi_series)
                if cpi_data is not None and not cpi_data.empty:
                    cpi_data = cpi_data.set_index("date") if "date" in cpi_data.columns else cpi_data
                    cpi_data.index = pd.to_datetime(cpi_data.index)
                    daily_index = pd.date_range(start=cpi_data.index.min(), end=end, freq="D")
                    cpi_daily = cpi_data.reindex(daily_index).ffill()
                    latest_cpi = cpi_daily["value"].iloc[-1]

                    adjusted = close.copy()
                    for i, d in enumerate(dates):
                        d_ts = pd.Timestamp(d)
                        mask = cpi_daily.index <= d_ts
                        if mask.any():
                            cpi_at_date = cpi_daily.loc[mask, "value"].iloc[-1]
                        else:
                            cpi_at_date = latest_cpi
                        if cpi_at_date > 0:
                            adjusted[i] = close[i] * (latest_cpi / cpi_at_date)

                    logger.info("Applied CPI-based inflation adjustment")
                    return adjusted
            except Exception as e:
                logger.warning(f"FRED CPI fetch failed, using fixed rate: {e}")

        # Fallback: fixed 3% annual inflation rate
        ANNUAL_RATE = 0.03
        end_ts = pd.Timestamp(end)
        adjusted = close.copy()
        for i, d in enumerate(dates):
            d_ts = pd.Timestamp(d)
            years = (end_ts - d_ts).days / 365.25
            adjusted[i] = close[i] * (1 + ANNUAL_RATE) ** years

        logger.info("Applied fixed 3%/yr inflation adjustment (no CPI data)")
        return adjusted

    # ---- Crosshair ----

    def _on_mouse_moved(self, pos) -> None:
        """Handle mouse move for crosshair."""
        if self._data is None or not hasattr(self, "_plot_x"):
            return

        vb = self.price_widget.plotItem.vb
        if not self.price_widget.sceneBoundingRect().contains(pos):
            return

        mouse_point = vb.mapSceneToView(pos)
        x_val = mouse_point.x()
        y_val = mouse_point.y()

        self._vline.setPos(x_val)
        self._hline.setPos(y_val)

        # Find nearest data point
        idx = int(round(x_val))
        if 0 <= idx < len(self._plot_x):
            price = self._plot_close[idx]
            pct = self._plot_pct[idx]
            d = self._plot_dates[idx]
            date_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]

            self._crosshair_label.setText(
                f"{date_str}  ${price:.2f}  ({pct:+.1f}%)"
            )
            # Position label in top-left of view
            view_range = vb.viewRange()
            self._crosshair_label.setPos(view_range[0][0], view_range[1][1])

        # Keep returns legend in top-right
        self._position_returns_legend()

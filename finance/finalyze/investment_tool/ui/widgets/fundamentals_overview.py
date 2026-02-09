"""Fundamentals overview widget showing company data in sectioned grids."""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QScrollArea,
    QGroupBox,
    QGridLayout,
    QLabel,
)
import pyqtgraph as pg
import numpy as np

from investment_tool.utils.helpers import format_large_number

logger = logging.getLogger(__name__)


# Value formatting types
_RATIO = "ratio"          # 2 decimal places: 28.50
_PERCENT = "percent"      # decimal -> percentage: 0.253 -> 25.30%
_CURRENCY_LARGE = "currency_large"  # format_large_number with $: $2.8T
_CURRENCY = "currency"    # dollar format: $6.43
_NUMBER_LARGE = "number_large"      # large number without $: 15.7B
_TEXT = "text"            # raw text

# Section definitions: (section_title, [(label, key, format_type), ...])
_SECTIONS: List[Tuple[str, List[Tuple[str, str, str]]]] = [
    ("Company Overview", [
        ("Name", "name", _TEXT),
        ("Sector", "sector", _TEXT),
        ("Industry", "industry", _TEXT),
        ("Exchange", "exchange", _TEXT),
        ("Currency", "currency", _TEXT),
    ]),
    ("Valuation", [
        ("P/E Ratio", "pe_ratio", _RATIO),
        ("Forward P/E", "forward_pe", _RATIO),
        ("PEG Ratio", "peg_ratio", _RATIO),
        ("P/B Ratio", "pb_ratio", _RATIO),
        ("P/S Ratio", "ps_ratio", _RATIO),
        ("EV/Revenue", "ev_revenue", _RATIO),
        ("EV/EBITDA", "ev_ebitda", _RATIO),
        ("Enterprise Value", "enterprise_value", _CURRENCY_LARGE),
    ]),
    ("Profitability", [
        ("Profit Margin", "profit_margin", _PERCENT),
        ("Operating Margin", "operating_margin", _PERCENT),
        ("ROE", "roe", _PERCENT),
        ("ROA", "roa", _PERCENT),
        ("Gross Profit TTM", "gross_profit_ttm", _CURRENCY_LARGE),
        ("EBITDA", "ebitda", _CURRENCY_LARGE),
        ("Revenue TTM", "revenue_ttm", _CURRENCY_LARGE),
    ]),
    ("Growth", [
        ("Revenue Growth YoY", "quarterly_revenue_growth_yoy", _PERCENT),
        ("Earnings Growth YoY", "quarterly_earnings_growth_yoy", _PERCENT),
        ("EPS (TTM)", "diluted_eps_ttm", _CURRENCY),
        ("EPS Estimate", "eps_estimate_current_year", _CURRENCY),
        ("Target Price", "wall_street_target_price", _CURRENCY),
    ]),
    ("Dividends", [
        ("Dividend Yield", "dividend_yield", _PERCENT),
        ("Dividend/Share", "dividend_share", _CURRENCY),
    ]),
    ("Share Statistics", [
        ("Shares Outstanding", "shares_outstanding", _NUMBER_LARGE),
        ("Float", "shares_float", _NUMBER_LARGE),
        ("% Insiders", "percent_insiders", _RATIO),
        ("% Institutions", "percent_institutions", _RATIO),
        ("Short Interest", "shares_short", _NUMBER_LARGE),
        ("Short Ratio", "short_ratio", _RATIO),
    ]),
    ("Technicals", [
        ("Beta", "beta", _RATIO),
        ("52W High", "week_52_high", _CURRENCY),
        ("52W Low", "week_52_low", _CURRENCY),
        ("50-Day MA", "day_50_ma", _CURRENCY),
        ("200-Day MA", "day_200_ma", _CURRENCY),
    ]),
]


class FundamentalsOverviewWidget(QWidget):
    """Scrollable widget showing company fundamentals in sectioned grids."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._data_manager = None
        self._ticker: Optional[str] = None
        self._exchange: Optional[str] = None
        self._value_labels: Dict[str, QLabel] = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(8, 8, 8, 0)
        self.ticker_label = QLabel("Select a stock")
        self.ticker_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #F9FAFB;"
        )
        header_layout.addWidget(self.ticker_label)
        layout.addLayout(header_layout)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: #1F2937; }"
            "QScrollBar:vertical { background: #1F2937; width: 8px; }"
            "QScrollBar::handle:vertical { background: #4B5563; border-radius: 4px; }"
        )

        container = QWidget()
        container.setStyleSheet("background: #1F2937;")
        self._container_layout = QVBoxLayout(container)
        self._container_layout.setContentsMargins(8, 8, 8, 8)
        self._container_layout.setSpacing(12)

        # Build sections
        for section_title, fields in _SECTIONS:
            group = self._create_section(section_title, fields)
            self._container_layout.addWidget(group)

        # Shares Outstanding History chart
        self._shares_chart_group = self._create_shares_chart()
        self._container_layout.addWidget(self._shares_chart_group)

        self._container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _create_section(
        self, title: str, fields: List[Tuple[str, str, str]]
    ) -> QGroupBox:
        group = QGroupBox(title)
        group.setStyleSheet(
            "QGroupBox { "
            "  background: #374151; border: 1px solid #4B5563; "
            "  border-radius: 6px; margin-top: 12px; padding: 8px; "
            "  font-weight: bold; color: #F9FAFB; "
            "}"
            "QGroupBox::title { "
            "  subcontrol-origin: margin; left: 10px; padding: 0 4px; "
            "}"
        )

        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setContentsMargins(8, 20, 8, 8)

        # Two columns of label:value pairs
        col_count = 2
        for i, (label_text, key, fmt) in enumerate(fields):
            row = i // col_count
            col = (i % col_count) * 2

            label = QLabel(label_text)
            label.setStyleSheet("color: #9CA3AF; font-size: 12px;")

            value = QLabel("--")
            value.setStyleSheet("color: #F9FAFB; font-size: 12px; font-weight: bold;")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            grid.addWidget(label, row, col)
            grid.addWidget(value, row, col + 1)

            self._value_labels[key] = value

        group.setLayout(grid)
        return group

    def _create_shares_chart(self) -> QGroupBox:
        """Create the Shares Outstanding History chart section."""
        group = QGroupBox("Shares Outstanding History")
        group.setStyleSheet(
            "QGroupBox { "
            "  background: #374151; border: 1px solid #4B5563; "
            "  border-radius: 6px; margin-top: 12px; padding: 8px; "
            "  font-weight: bold; color: #F9FAFB; "
            "}"
            "QGroupBox::title { "
            "  subcontrol-origin: margin; left: 10px; padding: 0 4px; "
            "}"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 20, 8, 8)

        # Latest value label
        self._shares_latest_label = QLabel("Latest: --")
        self._shares_latest_label.setStyleSheet(
            "color: #F9FAFB; font-size: 12px; font-weight: bold;"
        )
        layout.addWidget(self._shares_latest_label)

        # Chart
        self._shares_plot = pg.PlotWidget()
        self._shares_plot.setBackground("#2D3748")
        self._shares_plot.setFixedHeight(180)
        self._shares_plot.showGrid(x=False, y=True, alpha=0.2)
        self._shares_plot.getPlotItem().hideAxis("bottom")
        self._shares_plot.getPlotItem().getAxis("left").setStyle(showValues=True)
        self._shares_plot.getPlotItem().getAxis("left").setPen(pg.mkPen("#6B7280"))
        self._shares_plot.getPlotItem().getAxis("left").setTextPen(pg.mkPen("#9CA3AF"))
        layout.addWidget(self._shares_plot)

        # Legend labels
        legend_layout = QGridLayout()
        legend_layout.setSpacing(8)
        for i, (color, label) in enumerate([
            ("#3B82F6", "SEC EDGAR"),
            ("#F97316", "EODHD"),
            ("#22C55E", "yfinance"),
        ]):
            dot = QLabel(f"<span style='color:{color};'>\u25CF</span> {label}")
            dot.setStyleSheet("color: #9CA3AF; font-size: 11px;")
            legend_layout.addWidget(dot, 0, i)
        layout.addLayout(legend_layout)

        group.setLayout(layout)
        return group

    def set_data_manager(self, data_manager) -> None:
        self._data_manager = data_manager

    def set_ticker(self, ticker: str, exchange: str) -> None:
        self._ticker = ticker
        self._exchange = exchange
        self.ticker_label.setText(f"Fundamentals - {ticker}")
        self._fetch_and_display()
        self._fetch_shares_history()

    def set_period(self, period: str) -> None:
        """No-op: fundamentals don't change with period."""
        pass

    def clear(self) -> None:
        self._ticker = None
        self._exchange = None
        self.ticker_label.setText("Select a stock")
        for label in self._value_labels.values():
            label.setText("--")
            label.setStyleSheet("color: #F9FAFB; font-size: 12px; font-weight: bold;")
        self._shares_plot.clear()
        self._shares_latest_label.setText("Latest: --")

    def _fetch_and_display(self) -> None:
        if not self._data_manager or not self._ticker:
            return

        try:
            fundamentals = self._data_manager.get_fundamentals(
                self._ticker, self._exchange
            )
            if not fundamentals:
                return

            highlights = fundamentals.get("highlights", {})
            if not highlights:
                return

            self._populate(highlights)
        except Exception as e:
            logger.error(f"Failed to fetch fundamentals for {self._ticker}: {e}")

    def _fetch_shares_history(self) -> None:
        """Fetch and display shares outstanding history chart."""
        if not self._data_manager or not self._ticker:
            return

        try:
            result = self._data_manager.get_shares_history(
                self._ticker, self._exchange
            )
            if not result:
                return

            history = result.get("shares_history", [])
            latest = result.get("latest_shares_outstanding")

            if latest:
                self._shares_latest_label.setText(
                    f"Latest: {format_large_number(latest, decimals=2)}"
                )

            if history:
                self._populate_shares_chart(history)
        except Exception as e:
            logger.error(f"Failed to fetch shares history for {self._ticker}: {e}")

    def _populate_shares_chart(self, history: List[Dict[str, Any]]) -> None:
        """Populate the shares outstanding chart with historical data."""
        self._shares_plot.clear()

        if not history:
            return

        # Source -> color mapping
        source_colors = {
            "sec_edgar": "#3B82F6",
            "eodhd": "#F97316",
            "yfinance": "#22C55E",
        }

        # Group data by source
        by_source: Dict[str, List[Tuple[float, int]]] = {}
        for entry in history:
            source = entry.get("source", "unknown")
            report_date = entry.get("report_date")
            shares = entry.get("shares_outstanding")
            if not report_date or not shares:
                continue

            if isinstance(report_date, str):
                try:
                    dt = datetime.strptime(report_date, "%Y-%m-%d")
                except ValueError:
                    continue
            else:
                dt = datetime.combine(report_date, datetime.min.time())

            timestamp = dt.timestamp()
            by_source.setdefault(source, []).append((timestamp, shares))

        # Plot each source as a separate scatter/line
        for source, points in by_source.items():
            points.sort(key=lambda p: p[0])
            x = np.array([p[0] for p in points])
            y = np.array([p[1] for p in points], dtype=np.float64)
            color = source_colors.get(source, "#9CA3AF")

            # Line plot
            pen = pg.mkPen(color=color, width=1.5)
            self._shares_plot.plot(x, y, pen=pen)

            # Scatter dots
            scatter = pg.ScatterPlotItem(
                x=x, y=y, size=6,
                pen=pg.mkPen(color, width=1),
                brush=pg.mkBrush(color),
            )
            self._shares_plot.addItem(scatter)

        # Format Y-axis with B/M suffix
        axis = self._shares_plot.getPlotItem().getAxis("left")
        axis.setTickSpacing(major=1e9, minor=5e8)

        def _format_y(values):
            return [(v, format_large_number(v, decimals=1)) for v in values]

        # Custom tick strings — pyqtgraph uses setTicks or we can override
        # Simpler approach: just let auto-range handle it

    def _populate(self, data: Dict[str, Any]) -> None:
        for _, fields in _SECTIONS:
            for _, key, fmt in fields:
                label = self._value_labels.get(key)
                if not label:
                    continue

                value = data.get(key)
                text, color = self._format_value(value, fmt)
                label.setText(text)
                label.setStyleSheet(
                    f"color: {color}; font-size: 12px; font-weight: bold;"
                )

    def _format_value(
        self, value: Any, fmt: str
    ) -> Tuple[str, str]:
        """Format a value and return (text, color)."""
        default_color = "#F9FAFB"

        if value is None:
            return "--", "#6B7280"

        if fmt == _TEXT:
            return str(value), default_color

        try:
            num = float(value)
        except (ValueError, TypeError):
            return str(value), default_color

        if fmt == _RATIO:
            return f"{num:.2f}", default_color

        if fmt == _PERCENT:
            pct = num * 100
            color = "#22C55E" if pct >= 0 else "#EF4444"
            return f"{pct:.2f}%", color

        if fmt == _CURRENCY_LARGE:
            formatted = format_large_number(abs(num), decimals=2)
            if num < 0:
                return f"-${formatted}", default_color
            return f"${formatted}", default_color

        if fmt == _CURRENCY:
            return f"${num:,.2f}", default_color

        if fmt == _NUMBER_LARGE:
            return format_large_number(num, decimals=2), default_color

        return str(value), default_color

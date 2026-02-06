"""Quarterly financials display widget with grouped bar charts."""

from dataclasses import dataclass
from datetime import date
from typing import Optional, List, Dict, Any
from enum import Enum
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QLabel,
)
import pyqtgraph as pg
import numpy as np

logger = logging.getLogger(__name__)


class FinancialMetric(Enum):
    """Available financial metrics to display."""
    GROSS_REVENUE = "Gross Revenue"
    GROSS_PROFIT = "Gross Profit"
    AFTER_TAX_INCOME = "Net Income"
    CASH_RESERVE = "Cash Reserve"
    TOTAL_CASH = "Total Cash"


@dataclass
class QuarterlyFinancial:
    """Single quarter financial data."""
    ticker: str
    quarter: str  # "Q1", "Q2", "Q3", "Q4"
    year: int
    report_date: date
    gross_revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    after_tax_income: Optional[float] = None
    cash_reserve: Optional[float] = None
    total_cash: Optional[float] = None

    @property
    def fiscal_period(self) -> str:
        return f"{self.quarter} {self.year}"


class FinancialAxisItem(pg.AxisItem):
    """Custom axis for formatting large financial numbers."""

    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            if v is None or np.isnan(v):
                strings.append("")
            elif abs(v) >= 1e12:
                strings.append(f"${v/1e12:.1f}T")
            elif abs(v) >= 1e9:
                strings.append(f"${v/1e9:.1f}B")
            elif abs(v) >= 1e6:
                strings.append(f"${v/1e6:.1f}M")
            elif abs(v) >= 1e3:
                strings.append(f"${v/1e3:.1f}K")
            else:
                strings.append(f"${v:,.0f}")
        return strings


# Year color palette
YEAR_COLORS = [
    "#3B82F6",  # Blue (most recent)
    "#22C55E",  # Green
    "#F59E0B",  # Orange
    "#8B5CF6",  # Purple
    "#EC4899",  # Pink
    "#06B6D4",  # Cyan
    "#EF4444",  # Red
]


class QuarterlyFinancialsWidget(QWidget):
    """Widget displaying quarterly financial data as bar charts."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._data_manager = None
        self._ticker: Optional[str] = None
        self._exchange: Optional[str] = None
        self._current_period: str = "1Y"
        self._quarterly_data: List[QuarterlyFinancial] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header with ticker and metric selector
        header = self._create_header()
        layout.addLayout(header)

        # Main chart area
        self.chart = self._create_chart()
        layout.addWidget(self.chart, stretch=1)

        # Legend
        self.legend_widget = QWidget()
        self.legend_layout = QHBoxLayout(self.legend_widget)
        self.legend_layout.setContentsMargins(0, 0, 0, 0)
        self.legend_layout.addStretch()
        layout.addWidget(self.legend_widget)

    def _create_header(self) -> QHBoxLayout:
        """Create header with ticker label and metric selector."""
        header = QHBoxLayout()

        self.ticker_label = QLabel("Select a stock")
        self.ticker_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #F9FAFB;")
        header.addWidget(self.ticker_label)

        header.addStretch()

        # Metric selector
        metric_label = QLabel("Metric:")
        metric_label.setStyleSheet("color: #9CA3AF;")
        header.addWidget(metric_label)

        self.metric_combo = QComboBox()
        self.metric_combo.setMinimumWidth(150)
        for metric in FinancialMetric:
            self.metric_combo.addItem(metric.value, metric)
        self.metric_combo.currentIndexChanged.connect(self._on_metric_changed)
        header.addWidget(self.metric_combo)

        return header

    def _create_chart(self) -> pg.PlotWidget:
        """Create the bar chart widget."""
        # Custom Y axis for financial formatting
        y_axis = FinancialAxisItem(orientation='left')

        chart = pg.PlotWidget(axisItems={'left': y_axis})
        chart.setBackground("#1F2937")
        chart.showGrid(x=False, y=True, alpha=0.3)
        chart.getAxis("bottom").setStyle(tickTextOffset=10)
        chart.getAxis("bottom").setTextPen(pg.mkPen("#9CA3AF"))
        chart.getAxis("left").setTextPen(pg.mkPen("#9CA3AF"))

        # Hide auto-range button
        chart.hideButtons()

        return chart

    def set_data_manager(self, data_manager) -> None:
        """Set the data manager."""
        self._data_manager = data_manager

    def set_ticker(self, ticker: str, exchange: str) -> None:
        """Set the current ticker and update display."""
        self._ticker = ticker
        self._exchange = exchange
        self.ticker_label.setText(f"Quarterly Financials - {ticker}")
        self._fetch_and_display()

    def set_period(self, period: str) -> None:
        """Set the period for display mode."""
        self._current_period = period
        self._update_chart()

    def _fetch_and_display(self) -> None:
        """Fetch fundamentals and update display."""
        if not self._data_manager or not self._ticker:
            return

        try:
            fundamentals = self._data_manager.get_fundamentals(
                self._ticker, self._exchange
            )
            if fundamentals:
                self._quarterly_data = self._parse_quarterly_data(fundamentals)
                self._update_chart()
            else:
                logger.warning(f"No fundamentals data for {self._ticker}")
                self._quarterly_data = []
                self._update_chart()
        except Exception as e:
            logger.error(f"Failed to fetch fundamentals for {self._ticker}: {e}")
            self._quarterly_data = []
            self._update_chart()

    def _parse_quarterly_data(self, fundamentals: Dict[str, Any]) -> List[QuarterlyFinancial]:
        """Parse EODHD fundamentals into QuarterlyFinancial objects."""
        quarterly_data = []

        # Get quarterly income statements
        income_quarterly = fundamentals.get("Financials", {}).get(
            "Income_Statement", {}
        ).get("quarterly", {})

        # Get quarterly balance sheets
        balance_quarterly = fundamentals.get("Financials", {}).get(
            "Balance_Sheet", {}
        ).get("quarterly", {})

        # Combine by date
        for date_key, income in income_quarterly.items():
            try:
                report_date = date.fromisoformat(date_key)
            except ValueError:
                logger.warning(f"Invalid date format: {date_key}")
                continue

            quarter, year = self._date_to_quarter(report_date)

            # Get corresponding balance sheet
            balance = balance_quarterly.get(date_key, {})

            # Parse values safely
            cash = self._safe_float(balance.get("cash"))
            short_term_inv = self._safe_float(balance.get("shortTermInvestments"))

            qf = QuarterlyFinancial(
                ticker=self._ticker,
                quarter=quarter,
                year=year,
                report_date=report_date,
                gross_revenue=self._safe_float(income.get("totalRevenue")),
                gross_profit=self._safe_float(income.get("grossProfit")),
                after_tax_income=self._safe_float(income.get("netIncome")),
                cash_reserve=cash,
                total_cash=(cash or 0) + (short_term_inv or 0) if cash is not None else None,
            )
            quarterly_data.append(qf)

        # Sort by date descending (newest first)
        quarterly_data.sort(key=lambda x: x.report_date, reverse=True)

        return quarterly_data

    def _safe_float(self, value) -> Optional[float]:
        """Safely convert a value to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _date_to_quarter(self, report_date: date) -> tuple:
        """Convert report date to fiscal quarter and year."""
        month = report_date.month

        if month in (1, 2, 3):
            return "Q1", report_date.year
        elif month in (4, 5, 6):
            return "Q2", report_date.year
        elif month in (7, 8, 9):
            return "Q3", report_date.year
        else:
            return "Q4", report_date.year

    def _update_chart(self) -> None:
        """Update the chart based on current period and metric."""
        self.chart.clear()

        if not self._quarterly_data:
            # Show empty message
            text = pg.TextItem("No quarterly data available", color="#9CA3AF", anchor=(0.5, 0.5))
            self.chart.addItem(text)
            text.setPos(0.5, 0.5)
            return

        metric = self.metric_combo.currentData()
        is_short_period = self._current_period in ("1D", "1W", "1M", "3M", "6M", "YTD", "1Y")

        if is_short_period:
            self._render_combined_view(metric)
        else:
            self._render_grouped_view(metric)

    def _render_combined_view(self, metric: FinancialMetric) -> None:
        """Render last 4 quarters in a simple bar chart."""
        # Take last 4 quarters
        quarters = self._quarterly_data[:4]
        if not quarters:
            return

        quarters = list(reversed(quarters))  # Oldest first

        x = np.arange(len(quarters))
        values = np.array([self._get_metric_value(q, metric) or 0 for q in quarters])
        labels = [f"{q.quarter}\n{q.year}" for q in quarters]

        # Color based on value trend
        colors = []
        for i, v in enumerate(values):
            if i > 0 and v > values[i - 1]:
                colors.append("#22C55E")  # Green for growth
            elif i > 0 and v < values[i - 1]:
                colors.append("#EF4444")  # Red for decline
            else:
                colors.append("#3B82F6")  # Blue for neutral/first

        # Create bars
        bar_width = 0.6
        for i, (xval, height, color) in enumerate(zip(x, values, colors)):
            bar = pg.BarGraphItem(
                x=[xval], height=[height], width=bar_width,
                brush=pg.mkBrush(color), pen=pg.mkPen(color, width=1)
            )
            self.chart.addItem(bar)

        # Set x-axis labels
        x_axis = self.chart.getAxis("bottom")
        x_axis.setTicks([[(i, labels[i]) for i in range(len(labels))]])

        # Set y-axis label
        self.chart.setLabel("left", metric.value)

        # Auto-range with padding
        self.chart.setXRange(-0.5, len(quarters) - 0.5, padding=0.1)
        if len(values) > 0 and np.max(values) > 0:
            self.chart.setYRange(0, np.max(values) * 1.1)

        # Clear legend for combined view (no year grouping needed)
        self._clear_legend()

    def _render_grouped_view(self, metric: FinancialMetric) -> None:
        """Render quarters grouped by Q number across years."""
        if not self._quarterly_data:
            return

        # Determine number of years based on period
        if self._current_period == "2Y":
            num_years = 2
        elif self._current_period == "5Y":
            num_years = 5
        else:
            num_years = 3  # Default for 3M, etc.

        # Get unique years (most recent first)
        years = sorted(set(q.year for q in self._quarterly_data), reverse=True)[:num_years]
        years = list(reversed(years))  # Oldest first for display

        quarters = ["Q1", "Q2", "Q3", "Q4"]

        # Build data matrix: quarters x years
        bar_width = 0.8 / len(years) if years else 0.2
        x_positions = []
        labels = []

        for q_idx, quarter in enumerate(quarters):
            for y_idx, year in enumerate(years):
                # Find data point for this quarter/year
                value = self._find_quarter_value(quarter, year, metric)
                if value is None:
                    value = 0

                # Calculate bar position
                x = q_idx + (y_idx - len(years) / 2 + 0.5) * bar_width
                color = YEAR_COLORS[y_idx % len(YEAR_COLORS)]

                bar = pg.BarGraphItem(
                    x=[x], height=[value], width=bar_width * 0.9,
                    brush=pg.mkBrush(color), pen=pg.mkPen(color, width=1)
                )
                self.chart.addItem(bar)

            labels.append(quarter)

        # Set x-axis ticks to quarter labels
        x_axis = self.chart.getAxis("bottom")
        x_axis.setTicks([[(i, q) for i, q in enumerate(quarters)]])

        # Set y-axis label
        self.chart.setLabel("left", metric.value)

        # Auto-range
        self.chart.setXRange(-0.5, len(quarters) - 0.5, padding=0.1)

        # Find max value for y-range
        all_values = []
        for q in self._quarterly_data:
            val = self._get_metric_value(q, metric)
            if val is not None:
                all_values.append(val)
        if all_values:
            self.chart.setYRange(0, max(all_values) * 1.1)

        # Update legend
        self._update_legend(years)

    def _find_quarter_value(self, quarter: str, year: int, metric: FinancialMetric) -> Optional[float]:
        """Find value for a specific quarter and year."""
        for qf in self._quarterly_data:
            if qf.quarter == quarter and qf.year == year:
                return self._get_metric_value(qf, metric)
        return None

    def _get_metric_value(self, qf: QuarterlyFinancial, metric: FinancialMetric) -> Optional[float]:
        """Get the value for a specific metric."""
        mapping = {
            FinancialMetric.GROSS_REVENUE: qf.gross_revenue,
            FinancialMetric.GROSS_PROFIT: qf.gross_profit,
            FinancialMetric.AFTER_TAX_INCOME: qf.after_tax_income,
            FinancialMetric.CASH_RESERVE: qf.cash_reserve,
            FinancialMetric.TOTAL_CASH: qf.total_cash,
        }
        return mapping.get(metric)

    def _on_metric_changed(self, index: int) -> None:
        """Handle metric selection change."""
        self._update_chart()

    def _update_legend(self, years: List[int]) -> None:
        """Update the year legend."""
        self._clear_legend()

        for i, year in enumerate(years):
            color = YEAR_COLORS[i % len(YEAR_COLORS)]

            # Color box
            color_box = QLabel()
            color_box.setFixedSize(16, 16)
            color_box.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
            self.legend_layout.addWidget(color_box)

            # Year label
            label = QLabel(str(year))
            label.setStyleSheet("color: #F9FAFB; margin-right: 16px;")
            self.legend_layout.addWidget(label)

        self.legend_layout.addStretch()

    def _clear_legend(self) -> None:
        """Clear the legend."""
        while self.legend_layout.count():
            item = self.legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def clear(self) -> None:
        """Clear the display."""
        self._ticker = None
        self._exchange = None
        self._quarterly_data = []
        self.ticker_label.setText("Select a stock")
        self.chart.clear()
        self._clear_legend()

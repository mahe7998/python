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
from PySide6.QtGui import QCursor
import pyqtgraph as pg
import numpy as np

logger = logging.getLogger(__name__)


class FinancialMetric(Enum):
    """Available financial metrics to display."""
    # Income Statement
    GROSS_REVENUE = "Gross Revenue"
    GROSS_PROFIT = "Gross Profit"
    AFTER_TAX_INCOME = "Net Income"
    OPERATING_INCOME = "Operating Income"
    EBIT = "EBIT"
    COST_OF_REVENUE = "Cost of Revenue"
    RD_EXPENSE = "R&D Expense"
    # Balance Sheet
    CASH_RESERVE = "Cash Reserve"
    TOTAL_CASH = "Total Cash"
    TOTAL_ASSETS = "Total Assets"
    TOTAL_LIABILITIES = "Total Liabilities"
    STOCKHOLDERS_EQUITY = "Stockholders' Equity"
    LONG_TERM_DEBT = "Long-Term Debt"
    # Cash Flow
    OPERATING_CASH_FLOW = "Operating Cash Flow"
    CAPITAL_EXPENDITURE = "Capital Expenditure"
    FREE_CASH_FLOW = "Free Cash Flow"
    DIVIDENDS_PAID = "Dividends Paid"


# Group separators for the combo box: (index_after, label)
_METRIC_GROUPS = [
    (7, "--- Balance Sheet ---"),
    (13, "--- Cash Flow ---"),
]


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
    operating_income: Optional[float] = None
    ebit: Optional[float] = None
    cost_of_revenue: Optional[float] = None
    rd_expense: Optional[float] = None
    cash_reserve: Optional[float] = None
    total_cash: Optional[float] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    stockholders_equity: Optional[float] = None
    long_term_debt: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    capital_expenditure: Optional[float] = None
    free_cash_flow: Optional[float] = None
    dividends_paid: Optional[float] = None

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
        self._bar_regions: List[Dict] = []

        self._setup_ui()

        # Custom floating tooltip (persists while mouse is over a bar)
        self._tooltip = QLabel(None, Qt.ToolTip)
        self._tooltip.setStyleSheet(
            "QLabel {"
            "  background-color: #1F2937;"
            "  color: #F9FAFB;"
            "  border: 1px solid #374151;"
            "  border-radius: 4px;"
            "  padding: 6px 8px;"
            "}"
        )
        self._tooltip.hide()

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
        self.metric_combo.setMinimumWidth(180)
        # Add metrics with group separators
        idx = 0
        for metric in FinancialMetric:
            # Check if we need a separator before this item
            for sep_idx, sep_label in _METRIC_GROUPS:
                if idx == sep_idx:
                    self.metric_combo.insertSeparator(self.metric_combo.count())
            self.metric_combo.addItem(metric.value, metric)
            idx += 1
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
        chart.getAxis("bottom").setHeight(40)
        chart.getAxis("left").setTextPen(pg.mkPen("#9CA3AF"))

        # Hide auto-range button
        chart.hideButtons()

        # Enable mouse tracking for tooltip hit-testing
        self._plot_item = chart.plotItem
        chart.scene().sigMouseMoved.connect(self._on_mouse_moved)

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
        """Parse fundamentals into QuarterlyFinancial objects.

        Handles both the new structured format (data server) and legacy EODHD format.
        """
        quarterly_data = []

        # New structured format: data has "quarterly_financials" list
        if "quarterly_financials" in fundamentals:
            for item in fundamentals["quarterly_financials"]:
                try:
                    report_date = date.fromisoformat(item["report_date"])
                except (ValueError, KeyError):
                    continue

                cash = self._safe_float(item.get("cash"))
                short_term_inv = self._safe_float(item.get("short_term_investments"))

                qf = QuarterlyFinancial(
                    ticker=self._ticker,
                    quarter=item.get("quarter", ""),
                    year=item.get("year", 0),
                    report_date=report_date,
                    gross_revenue=self._safe_float(item.get("total_revenue")),
                    gross_profit=self._safe_float(item.get("gross_profit")),
                    after_tax_income=self._safe_float(item.get("net_income")),
                    operating_income=self._safe_float(item.get("operating_income")),
                    ebit=self._safe_float(item.get("ebit")),
                    cost_of_revenue=self._safe_float(item.get("cost_of_revenue")),
                    rd_expense=self._safe_float(item.get("research_development")),
                    cash_reserve=cash,
                    total_cash=(cash or 0) + (short_term_inv or 0) if cash is not None else None,
                    total_assets=self._safe_float(item.get("total_assets")),
                    total_liabilities=self._safe_float(item.get("total_liabilities")),
                    stockholders_equity=self._safe_float(item.get("stockholders_equity")),
                    long_term_debt=self._safe_float(item.get("long_term_debt")),
                    operating_cash_flow=self._safe_float(item.get("operating_cash_flow")),
                    capital_expenditure=self._safe_float(item.get("capital_expenditure")),
                    free_cash_flow=self._safe_float(item.get("free_cash_flow")),
                    dividends_paid=self._safe_float(item.get("dividends_paid")),
                )
                quarterly_data.append(qf)

            quarterly_data.sort(key=lambda x: x.report_date, reverse=True)
            return quarterly_data

        # Legacy EODHD format fallback
        income_quarterly = fundamentals.get("Financials", {}).get(
            "Income_Statement", {}
        ).get("quarterly", {})
        balance_quarterly = fundamentals.get("Financials", {}).get(
            "Balance_Sheet", {}
        ).get("quarterly", {})
        cashflow_quarterly = fundamentals.get("Financials", {}).get(
            "Cash_Flow", {}
        ).get("quarterly", {})

        for date_key, income in income_quarterly.items():
            try:
                report_date = date.fromisoformat(date_key)
            except ValueError:
                continue

            quarter, year = self._date_to_quarter(report_date)
            balance = balance_quarterly.get(date_key, {})
            cashflow = cashflow_quarterly.get(date_key, {})

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
                operating_income=self._safe_float(income.get("operatingIncome")),
                ebit=self._safe_float(income.get("ebit")),
                cost_of_revenue=self._safe_float(income.get("costOfRevenue")),
                rd_expense=self._safe_float(income.get("researchDevelopment")),
                cash_reserve=cash,
                total_cash=(cash or 0) + (short_term_inv or 0) if cash is not None else None,
                total_assets=self._safe_float(balance.get("totalAssets")),
                total_liabilities=self._safe_float(balance.get("totalLiab")),
                stockholders_equity=self._safe_float(balance.get("totalStockholderEquity")),
                long_term_debt=self._safe_float(balance.get("longTermDebt")),
                operating_cash_flow=self._safe_float(cashflow.get("totalCashFromOperatingActivities")),
                capital_expenditure=self._safe_float(cashflow.get("capitalExpenditures")),
                free_cash_flow=self._safe_float(cashflow.get("freeCashFlow")),
                dividends_paid=self._safe_float(cashflow.get("dividendsPaid")),
            )
            quarterly_data.append(qf)

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
        self._bar_regions = []
        self.chart.clear()

        if not self._quarterly_data:
            # Show empty message
            text = pg.TextItem("No quarterly data available", color="#9CA3AF", anchor=(0.5, 0.5))
            self.chart.addItem(text)
            text.setPos(0.5, 0.5)
            return

        metric = self.metric_combo.currentData()
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
            self._bar_regions.append({
                "x_min": xval - bar_width / 2,
                "x_max": xval + bar_width / 2,
                "quarter": quarters[i].quarter,
                "year": quarters[i].year,
                "value": float(height),
            })

        # Set x-axis labels
        x_axis = self.chart.getAxis("bottom")
        x_axis.setTicks([[(i, labels[i]) for i in range(len(labels))]])

        # Set y-axis label
        self.chart.setLabel("left", metric.value)

        # Auto-range with padding, supporting negative values
        self.chart.setXRange(-0.5, len(quarters) - 0.5, padding=0.1)
        if len(values) > 0:
            min_val = min(0, float(np.min(values)))
            max_val = float(np.max(values))
            if max_val > min_val:
                padding = (max_val - min_val) * 0.1
                self.chart.setYRange(min_val - padding, max_val + padding)

        # Clear legend for combined view (no year grouping needed)
        self._clear_legend()

    def _render_grouped_view(self, metric: FinancialMetric) -> None:
        """Render quarters grouped by Q number across years."""
        if not self._quarterly_data:
            return

        num_years = 5

        # Get unique years (most recent first)
        years = sorted(set(q.year for q in self._quarterly_data), reverse=True)[:num_years]
        years = list(reversed(years))  # Oldest first for display

        quarters = ["Q1", "Q2", "Q3", "Q4"]

        # Build data matrix: quarters x years
        bar_width = 0.8 / len(years) if years else 0.2

        for q_idx, quarter in enumerate(quarters):
            for y_idx, year in enumerate(years):
                # Find data point for this quarter/year
                value = self._find_quarter_value(quarter, year, metric)
                if value is None:
                    value = 0

                # Calculate bar position
                x = q_idx + (y_idx - len(years) / 2 + 0.5) * bar_width
                color = YEAR_COLORS[y_idx % len(YEAR_COLORS)]

                actual_width = bar_width * 0.9
                bar = pg.BarGraphItem(
                    x=[x], height=[value], width=actual_width,
                    brush=pg.mkBrush(color), pen=pg.mkPen(color, width=1)
                )
                self.chart.addItem(bar)
                self._bar_regions.append({
                    "x_min": x - actual_width / 2,
                    "x_max": x + actual_width / 2,
                    "quarter": quarter,
                    "year": year,
                    "value": float(value),
                })

        # Set x-axis ticks to quarter labels
        x_axis = self.chart.getAxis("bottom")
        x_axis.setTicks([[(i, q) for i, q in enumerate(quarters)]])

        # Set y-axis label
        self.chart.setLabel("left", metric.value)

        # Auto-range, supporting negative values
        self.chart.setXRange(-0.5, len(quarters) - 0.5, padding=0.1)

        all_values = []
        for q in self._quarterly_data:
            val = self._get_metric_value(q, metric)
            if val is not None:
                all_values.append(val)
        if all_values:
            min_val = min(0, min(all_values))
            max_val = max(all_values)
            if max_val > min_val:
                padding = (max_val - min_val) * 0.1
                self.chart.setYRange(min_val - padding, max_val + padding)

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
            FinancialMetric.OPERATING_INCOME: qf.operating_income,
            FinancialMetric.EBIT: qf.ebit,
            FinancialMetric.COST_OF_REVENUE: qf.cost_of_revenue,
            FinancialMetric.RD_EXPENSE: qf.rd_expense,
            FinancialMetric.CASH_RESERVE: qf.cash_reserve,
            FinancialMetric.TOTAL_CASH: qf.total_cash,
            FinancialMetric.TOTAL_ASSETS: qf.total_assets,
            FinancialMetric.TOTAL_LIABILITIES: qf.total_liabilities,
            FinancialMetric.STOCKHOLDERS_EQUITY: qf.stockholders_equity,
            FinancialMetric.LONG_TERM_DEBT: qf.long_term_debt,
            FinancialMetric.OPERATING_CASH_FLOW: qf.operating_cash_flow,
            FinancialMetric.CAPITAL_EXPENDITURE: qf.capital_expenditure,
            FinancialMetric.FREE_CASH_FLOW: qf.free_cash_flow,
            FinancialMetric.DIVIDENDS_PAID: qf.dividends_paid,
        }
        return mapping.get(metric)

    def _format_value(self, v: float) -> str:
        """Format a financial value with appropriate suffix."""
        negative = v < 0
        av = abs(v)
        if av >= 1e12:
            s = f"${av/1e12:.2f}T"
        elif av >= 1e9:
            s = f"${av/1e9:.2f}B"
        elif av >= 1e6:
            s = f"${av/1e6:.2f}M"
        elif av >= 1e3:
            s = f"${av/1e3:.2f}K"
        else:
            s = f"${av:,.0f}"
        return f"-{s}" if negative else s

    def _on_mouse_moved(self, pos) -> None:
        """Handle mouse movement over chart for tooltip display."""
        if not self._bar_regions:
            self._tooltip.hide()
            return

        vb = self._plot_item.vb
        mouse_point = vb.mapSceneToView(pos)
        mx, my = mouse_point.x(), mouse_point.y()

        for region in self._bar_regions:
            val = region["value"]
            if region["x_min"] <= mx <= region["x_max"]:
                # Check y bounds (handle negative bars)
                hit = (val >= 0 and 0 <= my <= val) or (val < 0 and val <= my <= 0)
                if hit:
                    html = self._build_tooltip_html(region)
                    self._tooltip.setText(html)
                    self._tooltip.adjustSize()
                    cursor_pos = QCursor.pos()
                    self._tooltip.move(cursor_pos.x() + 16, cursor_pos.y() + 16)
                    self._tooltip.show()
                    return

        self._tooltip.hide()

    def _build_tooltip_html(self, region: Dict) -> str:
        """Build rich HTML tooltip for a hovered bar."""
        quarter = region["quarter"]
        year = region["year"]
        value = region["value"]
        metric = self.metric_combo.currentData()

        # Exact value
        formatted_value = self._format_value(value)

        # Annual total: sum all quarters of this year for the current metric
        annual_values = []
        for qf in self._quarterly_data:
            if qf.year == year:
                v = self._get_metric_value(qf, metric)
                if v is not None:
                    annual_values.append(v)
        annual_total = sum(annual_values) if annual_values else None
        num_quarters = len(annual_values)

        # % of annual
        pct_of_annual = None
        if annual_total and annual_total != 0 and value >= 0:
            pct_of_annual = value / annual_total * 100

        # YoY change
        prev_value = self._find_quarter_value(quarter, year - 1, metric)
        yoy_change = None
        if prev_value is not None and prev_value != 0:
            yoy_change = (value - prev_value) / abs(prev_value) * 100

        # Build HTML
        rows = f'<tr><td>Value:</td><td align="right"><b>{formatted_value}</b></td></tr>'

        if annual_total is not None:
            rows += (
                f'<tr><td>Annual Total:&nbsp;&nbsp;</td>'
                f'<td align="right">{self._format_value(annual_total)} ({num_quarters} quarter{"s" if num_quarters != 1 else ""})</td></tr>'
            )

        if pct_of_annual is not None:
            rows += f'<tr><td>% of Annual:</td><td align="right">{pct_of_annual:.1f}%</td></tr>'

        if yoy_change is not None:
            color = "#22C55E" if yoy_change >= 0 else "#EF4444"
            sign = "+" if yoy_change >= 0 else ""
            rows += (
                f'<tr><td>YoY Change:</td>'
                f'<td align="right" style="color: {color};">{sign}{yoy_change:.1f}%</td></tr>'
            )

        if prev_value is not None:
            rows += (
                f'<tr><td>{quarter} {year - 1}:</td>'
                f'<td align="right">{self._format_value(prev_value)}</td></tr>'
            )

        html = (
            f'<div style="font-family: monospace; font-size: 12px;">'
            f'<b>{quarter} {year} &mdash; {metric.value}</b><br>'
            f'<hr>'
            f'<table>{rows}</table>'
            f'</div>'
        )
        return html

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

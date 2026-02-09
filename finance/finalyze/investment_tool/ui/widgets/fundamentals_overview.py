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
from PySide6.QtGui import QCursor
import pyqtgraph as pg
import numpy as np

class SharesAxisItem(pg.AxisItem):
    """Custom Y-axis formatting shares with K/M/B suffixes."""

    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            if v is None or np.isnan(v):
                strings.append("")
            elif abs(v) >= 1e9:
                strings.append(f"{v / 1e9:.1f}B")
            elif abs(v) >= 1e6:
                strings.append(f"{v / 1e6:.0f}M")
            elif abs(v) >= 1e3:
                strings.append(f"{v / 1e3:.0f}K")
            else:
                strings.append(f"{v:,.0f}")
        return strings

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
        self._shares_bar_regions: List[Dict] = []
        self._shares_splits: List[Dict] = []  # detected splits

        self._setup_ui()

        # Custom floating tooltip for shares chart
        self._shares_tooltip = QLabel(None, Qt.ToolTip)
        self._shares_tooltip.setStyleSheet(
            "QLabel {"
            "  background-color: #1F2937;"
            "  color: #F9FAFB;"
            "  border: 1px solid #374151;"
            "  border-radius: 4px;"
            "  padding: 6px 8px;"
            "}"
        )
        self._shares_tooltip.hide()

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

        # Chart with custom Y-axis
        y_axis = SharesAxisItem(orientation='left')
        self._shares_plot = pg.PlotWidget(axisItems={'left': y_axis})
        self._shares_plot.setBackground("#2D3748")
        self._shares_plot.setFixedHeight(180)
        self._shares_plot.showGrid(x=False, y=True, alpha=0.2)
        # Show bottom axis with dates
        self._shares_plot.getPlotItem().getAxis("bottom").setPen(pg.mkPen("#6B7280"))
        self._shares_plot.getPlotItem().getAxis("bottom").setTextPen(pg.mkPen("#9CA3AF"))
        self._shares_plot.getPlotItem().getAxis("bottom").setStyle(tickTextOffset=8)
        self._shares_plot.getPlotItem().getAxis("bottom").setHeight(35)
        self._shares_plot.getPlotItem().getAxis("left").setStyle(showValues=True)
        self._shares_plot.getPlotItem().getAxis("left").setPen(pg.mkPen("#6B7280"))
        self._shares_plot.getPlotItem().getAxis("left").setTextPen(pg.mkPen("#9CA3AF"))
        self._shares_plot.hideButtons()
        layout.addWidget(self._shares_plot)

        # Connect mouse move for tooltip
        self._shares_plot_item = self._shares_plot.plotItem
        self._shares_plot.scene().sigMouseMoved.connect(self._on_shares_mouse_moved)

        # Legend labels
        legend_layout = QGridLayout()
        legend_layout.setSpacing(8)
        for i, (color, label) in enumerate([
            ("#3B82F6", "SEC EDGAR"),
            ("#F97316", "EODHD"),
            ("#22C55E", "yfinance"),
            ("#EF4444", "Split"),
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
        self._shares_bar_regions = []
        self._shares_splits = []
        self._shares_tooltip.hide()
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

            # Fetch actual split dates from daily price data
            splits = []
            try:
                splits = self._data_manager.get_split_history(
                    self._ticker, self._exchange
                )
            except Exception as e:
                logger.debug(f"Could not fetch split history: {e}")

            if history:
                self._populate_shares_chart(history, splits)
        except Exception as e:
            logger.error(f"Failed to fetch shares history for {self._ticker}: {e}")

    def _populate_shares_chart(
        self, history: List[Dict[str, Any]], splits: List[Dict[str, Any]] = None,
    ) -> None:
        """Populate the shares outstanding chart with split-adjusted bars."""
        self._shares_plot.clear()
        self._shares_bar_regions = []
        self._shares_splits = []

        if not history:
            return

        # Collect all points: (timestamp, raw_shares, source, date_str)
        all_points: List[Tuple[float, float, str, str]] = []
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
                date_str = report_date
            else:
                dt = datetime.combine(report_date, datetime.min.time())
                date_str = report_date.isoformat()

            all_points.append((dt.timestamp(), float(shares), source, date_str))

        if not all_points:
            return

        all_points.sort(key=lambda p: p[0])

        # Filter outliers: remove points where shares are >10x the median
        # (catches SEC EDGAR data errors like values stored in wrong units)
        if len(all_points) >= 3:
            shares_vals = sorted(p[1] for p in all_points)
            median = shares_vals[len(shares_vals) // 2]
            all_points = [p for p in all_points if p[1] < median * 10]

        if not all_points:
            return

        # Build split info from actual daily price data (accurate dates)
        split_timestamps = []
        if splits:
            for s in splits:
                try:
                    sdt = datetime.strptime(s["date"], "%Y-%m-%d")
                except (ValueError, KeyError):
                    continue
                sts = sdt.timestamp()
                self._shares_splits.append({
                    "date": s["date"],
                    "ratio": f'{s["ratio"]}:1',
                    "ratio_num": s["ratio"],
                    "timestamp": sts,
                })
                split_timestamps.append(sts)

        # For each bar, determine which splits occurred AFTER it (to compute
        # the cumulative adjustment factor that normalizes it to post-split scale)
        # Working backwards: most recent bar has factor=1.
        # Each split that occurred after bar i means bar i needs multiplying up.
        cumulative_factor = [1.0] * len(all_points)
        for i in range(len(all_points)):
            factor = 1.0
            for sp in self._shares_splits:
                if sp["timestamp"] > all_points[i][0]:
                    factor *= sp["ratio_num"]
            cumulative_factor[i] = factor

        # For the bar that straddles a split (the split date falls between
        # this bar's date and the previous bar's date), we pro-rata:
        # days_before_split use pre-split count * full factor,
        # days_after_split use post-split count (factor / split_ratio).
        # The bar's raw value is post-split, so we weight accordingly.
        split_bar_indices = set()
        for sp in self._shares_splits:
            sp_ts = sp["timestamp"]
            for i in range(1, len(all_points)):
                prev_ts = all_points[i - 1][0]
                curr_ts = all_points[i][0]
                if prev_ts < sp_ts <= curr_ts:
                    split_bar_indices.add(i)
                    break

        adjusted_values = []
        for i, (ts, raw_shares, source, date_str) in enumerate(all_points):
            if i in split_bar_indices and i > 0:
                # This bar's period straddles a split
                prev_ts = all_points[i - 1][0]
                curr_ts = ts
                total_days = max((curr_ts - prev_ts) / 86400, 1)

                # Find which split(s) fall in this bar's period
                for sp in self._shares_splits:
                    if prev_ts < sp["timestamp"] <= curr_ts:
                        split_ts = sp["timestamp"]
                        ratio = sp["ratio_num"]
                        days_before = (split_ts - prev_ts) / 86400
                        days_after = (curr_ts - split_ts) / 86400

                        # Before split: shares were raw/ratio, adjusted to current scale
                        pre_split_adj = (raw_shares / ratio) * cumulative_factor[i] * ratio
                        post_split_adj = raw_shares * cumulative_factor[i]

                        weighted = (
                            pre_split_adj * days_before + post_split_adj * days_after
                        ) / total_days
                        adjusted_values.append(weighted)
                        break
                else:
                    adjusted_values.append(raw_shares * cumulative_factor[i])
            else:
                adjusted_values.append(raw_shares * cumulative_factor[i])

        # Source -> color mapping
        source_colors = {
            "sec_edgar": "#3B82F6",
            "eodhd": "#F97316",
            "yfinance": "#22C55E",
        }
        split_color = "#EF4444"

        # Bar width
        bar_width_ts = 86400 * 20
        if len(all_points) > 1:
            gaps = [all_points[i][0] - all_points[i - 1][0] for i in range(1, len(all_points))]
            avg_gap = sum(gaps) / len(gaps)
            bar_width_ts = avg_gap * 0.6

        for i, (ts, raw_shares, source, date_str) in enumerate(all_points):
            adjusted = adjusted_values[i]
            is_split = i in split_bar_indices
            color = split_color if is_split else source_colors.get(source, "#9CA3AF")

            bar = pg.BarGraphItem(
                x=[ts], height=[adjusted], width=bar_width_ts,
                brush=pg.mkBrush(color), pen=pg.mkPen(color, width=1),
            )
            self._shares_plot.addItem(bar)
            self._shares_bar_regions.append({
                "x_min": ts - bar_width_ts / 2,
                "x_max": ts + bar_width_ts / 2,
                "timestamp": ts,
                "shares": raw_shares,
                "adjusted": adjusted,
                "source": source,
                "date": date_str,
                "is_split": is_split,
            })

        # X-axis: date labels
        timestamps = [p[0] for p in all_points]
        n_ticks = min(6, len(timestamps))
        if n_ticks > 1:
            indices = np.linspace(0, len(timestamps) - 1, n_ticks, dtype=int)
        else:
            indices = [0]
        tick_list = []
        for idx in indices:
            ts = timestamps[idx]
            dt = datetime.fromtimestamp(ts)
            tick_list.append((ts, dt.strftime("%b %Y")))
        self._shares_plot.getPlotItem().getAxis("bottom").setTicks([tick_list])

        # Y-axis: start at 0
        max_adj = max(adjusted_values) if adjusted_values else 1
        self._shares_plot.setYRange(0, max_adj * 1.1)

        # X-axis range with padding
        ts_min = timestamps[0]
        ts_max = timestamps[-1]
        ts_pad = (ts_max - ts_min) * 0.05 if ts_max > ts_min else bar_width_ts
        self._shares_plot.setXRange(ts_min - ts_pad, ts_max + ts_pad)

    def _on_shares_mouse_moved(self, pos) -> None:
        """Handle mouse movement over shares chart for tooltip."""
        if not self._shares_bar_regions:
            self._shares_tooltip.hide()
            return

        vb = self._shares_plot_item.vb
        mouse_point = vb.mapSceneToView(pos)
        mx, my = mouse_point.x(), mouse_point.y()

        for region in self._shares_bar_regions:
            if region["x_min"] <= mx <= region["x_max"] and 0 <= my <= region["adjusted"]:
                html = self._build_shares_tooltip(region)
                self._shares_tooltip.setText(html)
                self._shares_tooltip.adjustSize()
                cursor_pos = QCursor.pos()
                self._shares_tooltip.move(cursor_pos.x() + 16, cursor_pos.y() + 16)
                self._shares_tooltip.show()
                return

        self._shares_tooltip.hide()

    def _build_shares_tooltip(self, region: Dict) -> str:
        """Build HTML tooltip for a shares outstanding bar."""
        date_str = region["date"]
        shares = region["shares"]
        adjusted = region["adjusted"]
        source = region["source"]
        ts = region["timestamp"]
        is_split = region["is_split"]

        source_labels = {
            "sec_edgar": "SEC EDGAR",
            "eodhd": "EODHD",
            "yfinance": "yfinance",
        }

        rows = (
            f'<tr><td>Shares:&nbsp;&nbsp;</td>'
            f'<td align="right"><b>{format_large_number(shares, decimals=2)}</b></td></tr>'
            f'<tr><td>Exact:</td>'
            f'<td align="right">{shares:,.0f}</td></tr>'
        )

        if abs(adjusted - shares) > 1:
            rows += (
                f'<tr><td>Adjusted:</td>'
                f'<td align="right">{format_large_number(adjusted, decimals=2)}</td></tr>'
            )

        rows += (
            f'<tr><td>Source:</td>'
            f'<td align="right">{source_labels.get(source, source)}</td></tr>'
        )

        if is_split:
            # Find the most recent split on or before this bar's date
            split_match = None
            for sp in self._shares_splits:
                if sp["timestamp"] <= ts:
                    split_match = sp
            if split_match:
                rows += (
                    f'<tr><td>Split:</td>'
                    f'<td align="right" style="color: #EF4444;">'
                    f'<b>{split_match["ratio"]}</b> ({split_match["date"]})</td></tr>'
                )

        # Find last split on or before this date
        last_split = None
        for split in self._shares_splits:
            if split["timestamp"] <= ts:
                last_split = split
        if last_split and not is_split:
            rows += (
                f'<tr><td>Last Split:</td>'
                f'<td align="right"><b>{last_split["ratio"]}</b> ({last_split["date"]})</td></tr>'
            )

        html = (
            f'<div style="font-family: monospace; font-size: 12px;">'
            f'<b>{date_str}</b><br><hr>'
            f'<table>{rows}</table>'
            f'</div>'
        )
        return html

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

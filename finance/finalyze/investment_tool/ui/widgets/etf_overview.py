"""ETF Overview widget showing fund info, performance, holdings, and allocations."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Optional, Dict, Any, List

import requests
from PySide6.QtCore import Qt, QThread, Signal
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


class HoldingsPerformanceWorker(QThread):
    """Background thread to fetch performance data for all ETF holdings."""

    finished = Signal(dict)  # {symbol: {period: change_pct, ...}, ...}

    def __init__(self, symbols: List[str], data_manager):
        super().__init__()
        self._symbols = symbols
        self._dm = data_manager

    def run(self):
        if not self._dm or not self._symbols:
            self.finished.emit({})
            return

        today = date.today()
        jan1 = date(today.year, 1, 1)

        periods = {
            "1D": (today - timedelta(days=7), today, True),   # daily_change=True
            "1M": (today - timedelta(days=35), today, False),
            "YTD": (jan1 - timedelta(days=5), today, False),
            "1Y": (today - timedelta(days=370), today, False),
        }

        results: Dict[str, Dict[str, Optional[float]]] = {s: {} for s in self._symbols}

        def fetch_period(period_name, start, end, daily_change):
            try:
                batch = self._dm.get_batch_daily_changes(
                    self._symbols, start, end, daily_change=daily_change
                )
                return period_name, batch
            except Exception as e:
                logger.warning(f"Holdings performance fetch failed for {period_name}: {e}")
                return period_name, {}

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(fetch_period, name, start, end, dc)
                for name, (start, end, dc) in periods.items()
            ]
            for f in futures:
                period_name, batch = f.result()
                for sym, data in batch.items():
                    if sym in results:
                        results[sym][period_name] = data.get("change")

        self.finished.emit(results)


class ETFOverviewWidget(QWidget):
    """Scrollable widget showing ETF-specific data: fund info, performance,
    holdings, sector allocation, and geographic allocation."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._value_labels: Dict[str, QLabel] = {}
        self._data_manager = None
        self._perf_worker: Optional[HoldingsPerformanceWorker] = None
        self._holding_list: List[Dict[str, Any]] = []  # current holdings for perf fill-in
        self._setup_ui()

    def set_data_manager(self, dm) -> None:
        self._data_manager = dm

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(8, 8, 8, 0)
        self.ticker_label = QLabel("ETF Overview")
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

        # 1. Fund Info
        self._fund_info_group = self._create_fund_info()
        self._container_layout.addWidget(self._fund_info_group)

        # 2. Performance
        self._performance_group = self._create_performance()
        self._container_layout.addWidget(self._performance_group)

        # 3. Holdings
        self._holdings_group = self._create_holdings()
        self._container_layout.addWidget(self._holdings_group)

        # 4. Sector Allocation
        self._sector_group, self._sector_plot = self._create_bar_chart("Sector Allocation")
        self._container_layout.addWidget(self._sector_group)

        # 5. Geographic Allocation
        self._geo_group, self._geo_plot = self._create_bar_chart("Geographic Allocation")
        self._container_layout.addWidget(self._geo_group)

        self._container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _groupbox_style(self) -> str:
        return (
            "QGroupBox { "
            "  background: #374151; border: 1px solid #4B5563; "
            "  border-radius: 6px; margin-top: 12px; padding: 8px; "
            "  font-weight: bold; color: #F9FAFB; "
            "}"
            "QGroupBox::title { "
            "  subcontrol-origin: margin; left: 10px; padding: 0 4px; "
            "}"
        )

    def _create_fund_info(self) -> QGroupBox:
        group = QGroupBox("Fund Info")
        group.setStyleSheet(self._groupbox_style())

        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setContentsMargins(8, 20, 8, 8)

        fields = [
            ("Category", "category"),
            ("Fund Family", "fund_family"),
            ("Net Assets", "net_assets"),
            ("Expense Ratio", "expense_ratio"),
            ("Inception Date", "inception_date"),
            ("Yield", "yield"),
        ]

        col_count = 2
        for i, (label_text, key) in enumerate(fields):
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

    def _create_performance(self) -> QGroupBox:
        group = QGroupBox("Performance")
        group.setStyleSheet(self._groupbox_style())

        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setContentsMargins(8, 20, 8, 8)

        fields = [
            ("YTD", "ytd"),
            ("1 Month", "1m"),
            ("3 Month", "3m"),
            ("6 Month", "6m"),
            ("1 Year", "1y"),
            ("3 Year", "3y"),
            ("5 Year", "5y"),
            ("10 Year", "10y"),
        ]

        col_count = 2
        for i, (label_text, key) in enumerate(fields):
            row = i // col_count
            col = (i % col_count) * 2

            label = QLabel(label_text)
            label.setStyleSheet("color: #9CA3AF; font-size: 12px;")

            value = QLabel("--")
            value.setStyleSheet("color: #F9FAFB; font-size: 12px; font-weight: bold;")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            grid.addWidget(label, row, col)
            grid.addWidget(value, row, col + 1)

            self._value_labels[f"perf_{key}"] = value

        group.setLayout(grid)
        return group

    def _create_holdings(self) -> QGroupBox:
        group = QGroupBox("Holdings")
        group.setStyleSheet(self._groupbox_style())

        self._holdings_layout = QVBoxLayout()
        self._holdings_layout.setContentsMargins(8, 20, 8, 8)

        self._holdings_grid = QGridLayout()
        self._holdings_grid.setSpacing(4)
        self._holdings_layout.addLayout(self._holdings_grid)

        group.setLayout(self._holdings_layout)
        return group

    def _create_bar_chart(self, title: str):
        group = QGroupBox(title)
        group.setStyleSheet(self._groupbox_style())

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 20, 8, 8)

        plot = pg.PlotWidget()
        plot.setBackground("#2D3748")
        plot.setFixedHeight(220)
        plot.showGrid(x=True, y=False, alpha=0.2)
        plot.hideButtons()

        bottom_axis = plot.getPlotItem().getAxis("bottom")
        bottom_axis.setPen(pg.mkPen("#6B7280"))
        bottom_axis.setTextPen(pg.mkPen("#9CA3AF"))

        left_axis = plot.getPlotItem().getAxis("left")
        left_axis.setPen(pg.mkPen("#6B7280"))
        left_axis.setTextPen(pg.mkPen("#9CA3AF"))

        layout.addWidget(plot)
        group.setLayout(layout)
        return group, plot

    # ── Column indices for the holdings grid ──
    _COL_TICKER = 0
    _COL_NAME = 1
    _COL_WEIGHT = 2
    _COL_1D = 3
    _COL_1M = 4
    _COL_YTD = 5
    _COL_1Y = 6
    _NUM_COLS = 7

    def update_data(self, data: dict) -> None:
        """Update the widget with parsed ETF data dict."""
        if not data:
            return

        # 1. Fund Info
        self._value_labels["category"].setText(
            data.get("Fund_Category") or data.get("Category") or "--"
        )
        self._value_labels["fund_family"].setText(
            data.get("Fund_Family") or "--"
        )

        total_assets = data.get("TotalAssets") or data.get("Net_Assets")
        if total_assets:
            self._value_labels["net_assets"].setText(format_large_number(float(total_assets)))
        else:
            self._value_labels["net_assets"].setText("--")

        expense = data.get("Ongoing_Charge") or data.get("NetExpenseRatio")
        if expense is not None:
            try:
                self._value_labels["expense_ratio"].setText(f"{float(expense)*100:.2f}%")
            except (ValueError, TypeError):
                self._value_labels["expense_ratio"].setText("--")
        else:
            self._value_labels["expense_ratio"].setText("--")

        self._value_labels["inception_date"].setText(
            data.get("Inception_Date") or "--"
        )

        yld = data.get("Yield")
        if yld is not None:
            try:
                self._value_labels["yield"].setText(f"{float(yld)*100:.2f}%")
            except (ValueError, TypeError):
                self._value_labels["yield"].setText("--")
        else:
            self._value_labels["yield"].setText("--")

        # 2. Performance
        perf = data.get("Performance", {})
        perf_map = {
            "ytd": "Returns_YTD",
            "1m": "Returns_1M",
            "3m": "Returns_3M",
            "6m": "Returns_6M",
            "1y": "Returns_1Y",
            "3y": "Returns_3Y",
            "5y": "Returns_5Y",
            "10y": "Returns_10Y",
        }
        for key, eodhd_key in perf_map.items():
            val = perf.get(eodhd_key)
            label = self._value_labels[f"perf_{key}"]
            if val is not None:
                try:
                    pct = float(val)
                    color = "#22C55E" if pct >= 0 else "#EF4444"
                    label.setText(f"{pct:+.2f}%")
                    label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold;")
                except (ValueError, TypeError):
                    label.setText("--")
                    label.setStyleSheet("color: #F9FAFB; font-size: 12px; font-weight: bold;")
            else:
                label.setText("--")
                label.setStyleSheet("color: #F9FAFB; font-size: 12px; font-weight: bold;")

        # 3. Holdings — build list and render table
        holdings = data.get("Holdings") or data.get("Top_10_Holdings") or {}
        self._holding_list = []
        for h_key, h_val in holdings.items():
            if isinstance(h_val, dict):
                self._holding_list.append({
                    "symbol": f"{h_val.get('Code', '')}.{h_val.get('Exchange', '')}",
                    "ticker": h_val.get("Code") or h_key,
                    "name": h_val.get("Name") or h_key,
                    "weight": h_val.get("Assets_%"),
                })

        self._holding_list.sort(
            key=lambda x: float(x["weight"]) if x["weight"] is not None else 0,
            reverse=True,
        )

        self._rebuild_holdings_grid()

        # Sync holdings to data server as tracked stocks, then fetch performance
        self._sync_holdings_and_fetch_performance()

        # 4. Sector/Industry Allocation — prefer per-holding Industry breakdown
        industry_weights = self._aggregate_holdings_field(holdings, "Industry")
        if industry_weights:
            self._sector_group.setTitle("Industry Allocation")
            self._update_bar_chart(self._sector_plot, industry_weights)
        else:
            self._sector_group.setTitle("Sector Allocation")
            self._update_bar_chart(
                self._sector_plot,
                data.get("Sector_Weights", {}),
                weight_key="Equity_%",
            )

        # 5. Geographic Allocation — prefer per-holding Country breakdown
        country_weights = self._aggregate_holdings_field(holdings, "Country")
        if country_weights:
            self._geo_group.setTitle("Country Allocation")
            self._update_bar_chart(self._geo_plot, country_weights)
        else:
            self._update_bar_chart(
                self._geo_plot,
                data.get("World_Regions", {}),
                weight_key="Equity_%",
            )

    @staticmethod
    def _aggregate_holdings_field(holdings: dict, field: str) -> dict:
        """Aggregate holdings weights by a field (e.g. Industry or Country).

        Returns dict of {field_value: weight} suitable for _update_bar_chart,
        or empty dict if data is insufficient.
        """
        from collections import defaultdict
        totals: Dict[str, float] = defaultdict(float)
        for h_val in holdings.values():
            if not isinstance(h_val, dict):
                continue
            key = h_val.get(field) or ""
            if not key:
                key = "Other"
            try:
                weight = float(h_val.get("Assets_%", 0))
            except (ValueError, TypeError):
                continue
            totals[key] += weight

        if not totals:
            return {}
        # Return as simple {name: weight} dict
        return dict(totals)

    def _rebuild_holdings_grid(self, perf_data: Optional[Dict] = None) -> None:
        """Rebuild the holdings grid with current data and optional perf data."""
        # Clear old widgets
        while self._holdings_grid.count():
            item = self._holdings_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        hdr_style = "color: #9CA3AF; font-size: 11px; font-weight: bold;"
        headers = ["Ticker", "Name", "Weight", "1D", "1M", "YTD", "1Y"]
        for col, text in enumerate(headers):
            lbl = QLabel(text)
            lbl.setStyleSheet(hdr_style)
            if col >= self._COL_WEIGHT:
                lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._holdings_grid.addWidget(lbl, 0, col)

        self._holdings_group.setTitle(f"Holdings ({len(self._holding_list)})")

        for i, h in enumerate(self._holding_list):
            row = i + 1

            ticker_label = QLabel(h["ticker"])
            ticker_label.setStyleSheet("color: #60A5FA; font-size: 11px;")
            self._holdings_grid.addWidget(ticker_label, row, self._COL_TICKER)

            name_label = QLabel(h["name"])
            name_label.setStyleSheet("color: #F9FAFB; font-size: 11px;")
            self._holdings_grid.addWidget(name_label, row, self._COL_NAME)

            weight_label = QLabel("--")
            weight_label.setStyleSheet("color: #F9FAFB; font-size: 11px; font-weight: bold;")
            weight_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            try:
                weight_label.setText(f"{float(h['weight']):.2f}%")
            except (ValueError, TypeError):
                pass
            self._holdings_grid.addWidget(weight_label, row, self._COL_WEIGHT)

            # Performance columns
            symbol = h["symbol"]
            for col, period in [(self._COL_1D, "1D"), (self._COL_1M, "1M"),
                                (self._COL_YTD, "YTD"), (self._COL_1Y, "1Y")]:
                perf_label = QLabel("..." if perf_data is None else "--")
                perf_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                perf_label.setStyleSheet("color: #6B7280; font-size: 11px;")

                if perf_data and symbol in perf_data:
                    change = perf_data[symbol].get(period)
                    if change is not None:
                        try:
                            pct = float(change) * 100
                            color = "#22C55E" if pct >= 0 else "#EF4444"
                            perf_label.setText(f"{pct:+.1f}%")
                            perf_label.setStyleSheet(f"color: {color}; font-size: 11px;")
                        except (ValueError, TypeError):
                            pass

                self._holdings_grid.addWidget(perf_label, row, col)

    def _sync_holdings_and_fetch_performance(self) -> None:
        """Sync ETF holdings to data server as tracked stocks, then
        kick off background performance fetch."""
        if not self._holding_list:
            return

        # Sync holdings to data server
        data_server_url = os.getenv("DATA_SERVER_URL", "").rstrip("/")
        if data_server_url:
            stocks = []
            for h in self._holding_list:
                parts = h["symbol"].split(".")
                if len(parts) == 2 and parts[0] and parts[1]:
                    stocks.append({"ticker": parts[0], "exchange": parts[1]})
            if stocks:
                try:
                    resp = requests.post(
                        f"{data_server_url}/tracking/stocks/sync",
                        json={"stocks": stocks},
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        logger.info(
                            f"Synced {result.get('added', 0)} ETF holdings to data server "
                            f"(total tracked: {result.get('total_tracked', 0)})"
                        )
                except Exception as e:
                    logger.warning(f"Could not sync ETF holdings: {e}")

        # Start background performance fetch
        if not self._data_manager:
            return

        symbols = [h["symbol"] for h in self._holding_list if "." in h["symbol"]]
        if not symbols:
            return

        # Cancel previous worker if still running
        if self._perf_worker and self._perf_worker.isRunning():
            self._perf_worker.quit()
            self._perf_worker.wait(2000)

        self._perf_worker = HoldingsPerformanceWorker(symbols, self._data_manager)
        self._perf_worker.finished.connect(self._on_performance_loaded)
        self._perf_worker.start()

    def _on_performance_loaded(self, perf_data: dict) -> None:
        """Called when background performance data is ready."""
        self._rebuild_holdings_grid(perf_data)

    def _update_bar_chart(
        self, plot: pg.PlotWidget, data: dict, weight_key: str = "Equity_%"
    ) -> None:
        """Update a horizontal bar chart with allocation data."""
        plot.clear()

        if not data:
            return

        entries = []
        for name, val in data.items():
            if isinstance(val, dict):
                w = val.get(weight_key)
            else:
                w = val
            if w is not None:
                try:
                    entries.append((str(name), float(w)))
                except (ValueError, TypeError):
                    pass

        if not entries:
            return

        # Sort ascending (largest at top)
        entries.sort(key=lambda x: x[1])

        names = [e[0] for e in entries]
        values = [e[1] for e in entries]
        y_pos = np.arange(len(entries))

        bar = pg.BarGraphItem(
            x0=0,
            y=y_pos,
            width=values,
            height=0.6,
            brush=pg.mkBrush("#3B82F6"),
            pen=pg.mkPen("#2563EB", width=1),
        )
        plot.addItem(bar)

        left_axis = plot.getPlotItem().getAxis("left")
        ticks = [(i, name) for i, name in enumerate(names)]
        left_axis.setTicks([ticks])
        left_axis.setStyle(tickTextOffset=5)

        bottom_axis = plot.getPlotItem().getAxis("bottom")
        bottom_axis.setLabel("%")

        max_val = max(values) if values else 100
        plot.setXRange(0, max_val * 1.15)
        plot.setYRange(-0.5, len(entries) - 0.5)

        for i, (name, val) in enumerate(entries):
            text = pg.TextItem(f"{val:.1f}%", color="#F9FAFB", anchor=(0, 0.5))
            text.setPos(val + max_val * 0.01, i)
            plot.addItem(text)

    def set_ticker_label(self, ticker: str, name: str = "") -> None:
        """Update the header label."""
        if name:
            self.ticker_label.setText(f"{ticker} — {name}")
        else:
            self.ticker_label.setText(f"{ticker} ETF Overview")

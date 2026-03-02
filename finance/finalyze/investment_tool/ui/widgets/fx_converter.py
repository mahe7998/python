"""FX Converter widget with historical chart and conversion tool."""

from datetime import date, datetime, timedelta
from typing import Optional, Dict

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QDate, QEvent
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QDateEdit,
    QFrame,
    QSplitter,
    QSizePolicy,
)

from investment_tool.config.settings import get_config
from investment_tool.data.manager import DataManager

# All supported currencies
CURRENCIES = [
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "HKD", "KRW", "CNY",
    "INR", "BRL", "SEK", "NOK", "DKK", "PLN", "SGD", "TWD", "IDR", "ILS", "CLP",
]

PERIOD_DAYS = {"1Y": 365, "2Y": 730, "3Y": 1095, "5Y": 1825, "10Y": 3650}


class FXConverterWidget(QWidget):
    """FX rate chart and conversion tool."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data_manager: Optional[DataManager] = None
        self._rates_cache: Dict[str, Dict[str, float]] = {}
        self._setup_ui()

    def set_data_manager(self, dm: DataManager) -> None:
        self.data_manager = dm
        self._update_chart()

    def _install_mouse_tracking(self) -> None:
        vp = self.chart.viewport()
        vp.setMouseTracking(True)
        vp.removeEventFilter(self)
        vp.installEventFilter(self)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._install_mouse_tracking()

    # ── UI setup ─────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left panel (two columns, fixed width)
        left = QWidget()
        left.setFixedWidth(400)
        left.setStyleSheet("background-color: #1F2937;")
        left_layout = QHBoxLayout(left)
        left_layout.setContentsMargins(12, 10, 6, 10)
        left_layout.setSpacing(10)

        # ── Column 1: Currency pair + period ──
        col1 = QVBoxLayout()
        col1.setSpacing(4)

        pair_label = QLabel("Currency Pair")
        pair_label.setStyleSheet("color: #9CA3AF; font-size: 10px; font-weight: bold;")
        col1.addWidget(pair_label)

        combo_style = (
            "QComboBox { font-size: 10px; }"
            "QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: right center;"
            "  width: 18px; border-left: 1px solid #4B5563; }"
            "QComboBox::down-arrow { image: none;"
            "  border-left: 4px solid transparent; border-right: 4px solid transparent;"
            "  border-top: 5px solid #9CA3AF; }"
        )
        config = get_config()
        self.from_combo = QComboBox()
        self.from_combo.setStyleSheet(combo_style)
        self.from_combo.addItems(CURRENCIES)
        self.from_combo.setCurrentText(config.ui.fx_from_currency)
        col1.addWidget(self.from_combo)

        swap_btn = QPushButton("\u21c4 Swap")
        swap_btn.setFixedHeight(29)
        swap_btn.setStyleSheet(
            "QPushButton { background: #374151; color: #9CA3AF; border: 1px solid #4B5563; "
            "border-radius: 4px; font-size: 10px; }"
            "QPushButton:hover { background: #4B5563; color: #F9FAFB; }"
        )
        swap_btn.clicked.connect(self._swap_currencies)
        col1.addWidget(swap_btn)

        self.to_combo = QComboBox()
        self.to_combo.setStyleSheet(combo_style)
        self.to_combo.addItems(CURRENCIES)
        self.to_combo.setCurrentText(config.ui.fx_to_currency)
        col1.addWidget(self.to_combo)

        col1.addSpacing(6)

        period_label = QLabel("Period")
        period_label.setStyleSheet("color: #9CA3AF; font-size: 10px; font-weight: bold;")
        col1.addWidget(period_label)

        period_row = QHBoxLayout()
        period_row.setSpacing(3)
        self._period_buttons: list[QPushButton] = []
        self._selected_period = "1Y"
        for label in PERIOD_DAYS:
            btn = QPushButton(label)
            btn.setFixedHeight(29)
            btn.setCheckable(True)
            btn.setChecked(label == self._selected_period)
            btn.clicked.connect(lambda checked, l=label: self._on_period_clicked(l))
            self._period_buttons.append(btn)
            period_row.addWidget(btn)
        self._style_period_buttons()
        col1.addLayout(period_row)

        col1.addStretch()
        left_layout.addLayout(col1, 2)

        # ── Vertical separator ──
        vsep = QFrame()
        vsep.setFrameShape(QFrame.VLine)
        vsep.setStyleSheet("color: #4B5563;")
        left_layout.addWidget(vsep)

        # ── Column 2: Converter ──
        col2 = QVBoxLayout()
        col2.setSpacing(4)

        amt_label = QLabel("Amount")
        amt_label.setStyleSheet("color: #D1D5DB; font-size: 10px;")
        col2.addWidget(amt_label)
        self.amount_edit = QLineEdit("100")
        self.amount_edit.setStyleSheet(
            "background: #374151; color: #F9FAFB; border: 1px solid #4B5563; "
            "border-radius: 4px; padding: 3px 6px;"
        )
        col2.addWidget(self.amount_edit)

        date_label = QLabel("Date")
        date_label.setStyleSheet("color: #D1D5DB; font-size: 10px;")
        col2.addWidget(date_label)
        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setMinimumDate(QDate(2000, 1, 1))
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setStyleSheet(
            "QDateEdit { background: #374151; color: #F9FAFB; border: 1px solid #4B5563; "
            "border-radius: 4px; padding: 3px 6px; font-size: 10px; }"
            "QDateEdit::drop-down { subcontrol-origin: padding; subcontrol-position: right center; "
            "width: 20px; border-left: 1px solid #4B5563; }"
            "QDateEdit::down-arrow { image: none; border-left: 4px solid transparent; "
            "border-right: 4px solid transparent; border-top: 5px solid #9CA3AF; }"
        )
        cal = self.date_edit.calendarWidget()
        if cal:
            cal.setMinimumWidth(300)
            cal.setStyleSheet(
                "QCalendarWidget QAbstractItemView { font-size: 11px; }"
                "QCalendarWidget QAbstractItemView:disabled { color: #4B5563; }"
                "QCalendarWidget QToolButton::menu-indicator { image: none; }"
                "QCalendarWidget QToolButton#qt_calendar_monthbutton::menu-indicator,"
                "QCalendarWidget QToolButton#qt_calendar_yearbutton::menu-indicator {"
                "  subcontrol-origin: padding; subcontrol-position: center right;"
                "  width: 0px; height: 0px;"
                "  border-left: 4px solid transparent; border-right: 4px solid transparent;"
                "  border-top: 5px solid #9CA3AF; margin-right: 4px;"
                "}"
            )
        col2.addWidget(self.date_edit)

        col2.addSpacing(4)
        result_sep = QFrame()
        result_sep.setFrameShape(QFrame.HLine)
        result_sep.setStyleSheet("color: #6B7280;")
        col2.addWidget(result_sep)
        col2.addSpacing(2)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("color: #F9FAFB; font-size: 12px; font-weight: bold;")
        col2.addWidget(self.result_label)

        self.rate_label = QLabel("")
        self.rate_label.setWordWrap(True)
        self.rate_label.setStyleSheet("color: #9CA3AF; font-size: 10px;")
        col2.addWidget(self.rate_label)

        col2.addStretch()
        left_layout.addLayout(col2, 3)

        # Right panel — chart
        self.chart = pg.PlotWidget(
            axisItems={"bottom": pg.DateAxisItem(orientation="bottom")},
            background="#111827",
        )
        self.chart.showGrid(x=True, y=True, alpha=0.15)
        self.chart.plotItem.setContentsMargins(0, 0, 0, 0)
        self.chart.plotItem.getViewBox().setDefaultPadding(0.02)
        # Remove title space
        self.chart.plotItem.titleLabel.setVisible(False)
        self.chart.plotItem.layout.setRowFixedHeight(0, 0)
        self.chart.setMouseEnabled(x=False, y=False)
        self.chart.setMenuEnabled(False)
        self.chart.getPlotItem().getViewBox().setMouseMode(pg.ViewBox.PanMode)
        # Enable mouse tracking so hover works without clicking
        self.chart.setMouseTracking(True)
        self._install_mouse_tracking()
        self.chart.getAxis("left").setStyle(tickFont=pg.QtGui.QFont("monospace", 8))
        self.chart.getAxis("bottom").setStyle(tickFont=pg.QtGui.QFont("monospace", 8))
        self.chart.getAxis("left").setTextPen("#9CA3AF")
        self.chart.getAxis("bottom").setTextPen("#9CA3AF")

        # Crosshair
        self._vline = pg.InfiniteLine(angle=90, pen=pg.mkPen("#6B7280", width=1, style=Qt.DashLine))
        self._hline = pg.InfiniteLine(angle=0, pen=pg.mkPen("#6B7280", width=1, style=Qt.DashLine))
        self._vline.setVisible(False)
        self._hline.setVisible(False)
        self.chart.addItem(self._vline, ignoreBounds=True)
        self.chart.addItem(self._hline, ignoreBounds=True)

        self._crosshair_label = pg.TextItem(color="#F9FAFB", anchor=(0, 0))
        self._crosshair_label.setVisible(False)
        self.chart.addItem(self._crosshair_label, ignoreBounds=True)

        self._chart_xs = np.array([])
        self._chart_ys = np.array([])
        self.chart.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self.chart.scene().sigMouseClicked.connect(self._on_chart_clicked)

        layout.addWidget(left)
        layout.addWidget(self.chart, 1)

        # Connect signals
        self.from_combo.currentTextChanged.connect(self._on_pair_changed)
        self.to_combo.currentTextChanged.connect(self._on_pair_changed)
        self.amount_edit.textChanged.connect(self._update_conversion)
        self.date_edit.dateChanged.connect(self._update_conversion)

    def _style_period_buttons(self) -> None:
        for btn in self._period_buttons:
            if btn.isChecked():
                btn.setStyleSheet(
                    "QPushButton { background: #3B82F6; color: #F9FAFB; border: none; "
                    "border-radius: 4px; font-size: 10px; font-weight: bold; }"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { background: #374151; color: #9CA3AF; border: 1px solid #4B5563; "
                    "border-radius: 4px; font-size: 10px; }"
                    "QPushButton:hover { background: #4B5563; color: #F9FAFB; }"
                )

    # ── Slots ────────────────────────────────────────────────────

    def _swap_currencies(self) -> None:
        f, t = self.from_combo.currentText(), self.to_combo.currentText()
        self.from_combo.blockSignals(True)
        self.to_combo.blockSignals(True)
        self.from_combo.setCurrentText(t)
        self.to_combo.setCurrentText(f)
        self.from_combo.blockSignals(False)
        self.to_combo.blockSignals(False)
        self._on_pair_changed()

    def _on_period_clicked(self, label: str) -> None:
        self._selected_period = label
        for btn in self._period_buttons:
            btn.setChecked(btn.text() == label)
        self._style_period_buttons()
        self._update_chart()

    def _on_pair_changed(self, _text=None) -> None:
        self._save_currency_pair()
        self._update_chart()

    def _save_currency_pair(self) -> None:
        config = get_config()
        config.ui.fx_from_currency = self.from_combo.currentText()
        config.ui.fx_to_currency = self.to_combo.currentText()
        from pathlib import Path
        config.save(Path.home() / ".investment_tool" / "settings.yaml")

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseMove:
            scene_pos = self.chart.mapToScene(event.position().toPoint())
            self._on_mouse_moved(scene_pos)
        return False

    def _on_mouse_moved(self, pos) -> None:
        if len(self._chart_xs) == 0:
            return
        vb = self.chart.plotItem.vb
        mouse_point = vb.mapSceneToView(pos)
        x = mouse_point.x()
        y = mouse_point.y()

        # Snap to nearest data point
        idx = int(np.searchsorted(self._chart_xs, x))
        idx = np.clip(idx, 0, len(self._chart_xs) - 1)
        snap_x = self._chart_xs[idx]
        snap_y = self._chart_ys[idx]

        self._vline.setPos(snap_x)
        self._hline.setPos(snap_y)
        self._vline.setVisible(True)
        self._hline.setVisible(True)

        dt_str = datetime.fromtimestamp(snap_x).strftime("%Y-%m-%d")
        self._crosshair_label.setText(f"{dt_str}\n{snap_y:.4f}")
        self._crosshair_label.setPos(snap_x, snap_y)
        self._crosshair_label.setVisible(True)

    def _on_chart_clicked(self, event) -> None:
        if len(self._chart_xs) == 0:
            return
        pos = event.scenePos()
        vb = self.chart.plotItem.vb
        mouse_point = vb.mapSceneToView(pos)
        x = mouse_point.x()

        idx = int(np.searchsorted(self._chart_xs, x))
        idx = np.clip(idx, 0, len(self._chart_xs) - 1)
        snap_x = self._chart_xs[idx]

        clicked_date = datetime.fromtimestamp(snap_x).date()
        self.date_edit.setDate(QDate(clicked_date.year, clicked_date.month, clicked_date.day))

    # ── Data helpers ─────────────────────────────────────────────

    def _fetch_rates(self, currency: str, from_date: str, to_date: str) -> Dict[str, float]:
        """Fetch rate_to_usd for a currency. Returns {date_str: rate}."""
        if currency == "USD":
            return {}
        key = f"{currency}|{from_date}|{to_date}"
        if key in self._rates_cache:
            return self._rates_cache[key]
        if not self.data_manager:
            return {}
        rates = self.data_manager.get_forex_rates(currency, from_date, to_date)
        self._rates_cache[key] = rates
        return rates

    @staticmethod
    def _adjust_gbp(rates: Dict[str, float], currency: str) -> Dict[str, float]:
        """GBp → GBP: multiply by 100 (rates are stored as GBp→USD)."""
        if currency == "GBP":
            return {d: v * 100 for d, v in rates.items()}
        return rates

    def _compute_cross_rates(
        self, from_ccy: str, to_ccy: str, from_date: str, to_date: str,
    ) -> list[tuple[float, float]]:
        """Return sorted list of (timestamp, cross_rate) for from→to."""
        from_rates = self._adjust_gbp(
            self._fetch_rates(from_ccy, from_date, to_date), from_ccy,
        )
        to_rates = self._adjust_gbp(
            self._fetch_rates(to_ccy, from_date, to_date), to_ccy,
        )

        if from_ccy == "USD":
            # 1 USD → to_ccy = 1 / to_to_usd
            dates = sorted(to_rates.keys())
            points = []
            for d in dates:
                rate = to_rates[d]
                if rate:
                    ts = datetime.strptime(d, "%Y-%m-%d").timestamp()
                    points.append((ts, 1.0 / rate))
            return points

        if to_ccy == "USD":
            # 1 from_ccy → USD = from_to_usd
            dates = sorted(from_rates.keys())
            return [
                (datetime.strptime(d, "%Y-%m-%d").timestamp(), from_rates[d])
                for d in dates if from_rates[d]
            ]

        # Cross rate: from_to_usd / to_to_usd
        common = sorted(set(from_rates.keys()) & set(to_rates.keys()))
        points = []
        for d in common:
            if from_rates[d] and to_rates[d]:
                ts = datetime.strptime(d, "%Y-%m-%d").timestamp()
                points.append((ts, from_rates[d] / to_rates[d]))
        return points

    # ── Chart ────────────────────────────────────────────────────

    def _update_chart(self) -> None:
        self.chart.clear()
        self._chart_xs = np.array([])
        self._chart_ys = np.array([])
        # Re-add crosshair items after clear
        self.chart.addItem(self._vline, ignoreBounds=True)
        self.chart.addItem(self._hline, ignoreBounds=True)
        self.chart.addItem(self._crosshair_label, ignoreBounds=True)
        self._vline.setVisible(False)
        self._hline.setVisible(False)
        self._crosshair_label.setVisible(False)
        self._rates_cache.clear()

        from_ccy = self.from_combo.currentText()
        to_ccy = self.to_combo.currentText()
        if from_ccy == to_ccy:
            self._update_conversion()
            return

        days = PERIOD_DAYS[self._selected_period]
        to_date = date.today().isoformat()
        from_date = (date.today() - timedelta(days=days)).isoformat()

        points = self._compute_cross_rates(from_ccy, to_ccy, from_date, to_date)
        if not points:
            self._update_conversion()
            return

        xs = np.array([p[0] for p in points])
        ys = np.array([p[1] for p in points])

        self._chart_xs = xs
        self._chart_ys = ys
        pen = pg.mkPen(color="#3B82F6", width=1.5)
        self.chart.plot(xs, ys, pen=pen)

        self._update_conversion()

    # ── Converter ────────────────────────────────────────────────

    def _update_conversion(self) -> None:
        from_ccy = self.from_combo.currentText()
        to_ccy = self.to_combo.currentText()

        # Parse amount
        try:
            amount = float(self.amount_edit.text())
        except ValueError:
            self.result_label.setText("")
            self.rate_label.setText("")
            return

        if from_ccy == to_ccy:
            self.result_label.setText(f"{amount:,.2f} {from_ccy} =\n{amount:,.2f} {to_ccy}")
            self.rate_label.setText(f"Rate: 1 {from_ccy} = 1 {to_ccy}")
            return

        # Get rate for chosen date
        sel_date = self.date_edit.date().toPython()  # returns datetime.date
        # Fetch 10 extra days back to handle weekends/holidays
        lookup_from = (sel_date - timedelta(days=10)).isoformat()
        lookup_to = sel_date.isoformat()

        points = self._compute_cross_rates(from_ccy, to_ccy, lookup_from, lookup_to)
        if not points:
            self.result_label.setText("No rate data")
            self.rate_label.setText("")
            return

        # Find closest date <= selected (ffill)
        sel_ts = datetime.combine(sel_date, datetime.min.time()).timestamp()
        rate = None
        for ts, r in reversed(points):
            if ts <= sel_ts + 86400:  # include same-day
                rate = r
                break
        if rate is None:
            rate = points[-1][1]

        converted = amount * rate
        self.result_label.setText(f"{amount:,.2f} {from_ccy} =\n{converted:,.2f} {to_ccy}")
        self.rate_label.setText(f"Rate: 1 {from_ccy} =\n       {rate:.4f} {to_ccy}")

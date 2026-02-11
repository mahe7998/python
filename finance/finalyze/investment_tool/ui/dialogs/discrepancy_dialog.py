"""Dialog for reviewing EODHD vs yfinance quarterly data discrepancies."""

from typing import List, Dict, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QCheckBox,
    QWidget,
)


def _format_value(v) -> str:
    """Format a financial value with appropriate suffix."""
    if v is None:
        return "N/A"
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


FIELD_LABELS = {
    "total_revenue": "Revenue",
    "gross_profit": "Gross Profit",
    "net_income": "Net Income",
    "operating_income": "Op. Income",
}


class DiscrepancyDialog(QDialog):
    """Dialog showing EODHD vs yfinance discrepancies with override options."""

    def __init__(
        self,
        ticker: str,
        discrepancies: List[Dict[str, Any]],
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self._ticker = ticker
        self._discrepancies = discrepancies
        self._checkboxes: List[QCheckBox] = []
        self._selected_overrides: List[Dict[str, Any]] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle(f"Data Discrepancy - {self._ticker}")
        self.setMinimumSize(750, 400)
        self.setStyleSheet("""
            QDialog {
                background: #111827;
            }
            QLabel {
                color: #F3F4F6;
            }
            QTableWidget {
                background: #1F2937;
                border: 1px solid #374151;
                border-radius: 6px;
                gridline-color: #374151;
                color: #F3F4F6;
                selection-background-color: #374151;
            }
            QTableWidget::item {
                padding: 4px 8px;
            }
            QHeaderView::section {
                background: #374151;
                color: #F3F4F6;
                border: 1px solid #4B5563;
                padding: 6px;
                font-weight: bold;
            }
            QPushButton {
                background: #3B82F6;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
                color: white;
            }
            QPushButton:hover {
                background: #2563EB;
            }
            QPushButton:disabled {
                background: #4B5563;
                color: #9CA3AF;
            }
            QPushButton[secondary="true"] {
                background: #374151;
                color: #F3F4F6;
            }
            QPushButton[secondary="true"]:hover {
                background: #4B5563;
            }
            QCheckBox {
                color: #F3F4F6;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #4B5563;
                background: #374151;
            }
            QCheckBox::indicator:checked {
                background: #3B82F6;
                border-color: #3B82F6;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel(
            f"EODHD vs yfinance data discrepancies found for {self._ticker}.\n"
            "Select quarters to override with yfinance values."
        )
        header.setWordWrap(True)
        header.setStyleSheet("font-size: 13px; color: #D1D5DB;")
        layout.addWidget(header)

        # Build flat rows: one per field diff per quarter
        rows = []
        for disc in self._discrepancies:
            for diff in disc["field_diffs"]:
                rows.append({
                    "quarter": f"{disc['quarter']} {disc['year']}",
                    "report_date": disc["report_date"],
                    "field": diff["field"],
                    "eodhd_value": diff["eodhd_value"],
                    "yfinance_value": diff["yfinance_value"],
                    "pct_diff": diff["pct_diff"],
                    "yfinance_record": disc["yfinance_record"],
                })

        # Table
        table = QTableWidget(len(rows), 5)
        table.setHorizontalHeaderLabels(["Quarter", "Field", "EODHD", "yfinance", "% Diff"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)

        for i, row in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(row["quarter"]))
            table.setItem(i, 1, QTableWidgetItem(FIELD_LABELS.get(row["field"], row["field"])))

            eodhd_item = QTableWidgetItem(_format_value(row["eodhd_value"]))
            table.setItem(i, 2, eodhd_item)

            yf_item = QTableWidgetItem(_format_value(row["yfinance_value"]))
            table.setItem(i, 3, yf_item)

            pct_item = QTableWidgetItem(f"{row['pct_diff']:.1f}%")
            pct_item.setForeground(Qt.red if row["pct_diff"] > 10 else Qt.yellow)
            table.setItem(i, 4, pct_item)

        layout.addWidget(table, stretch=1)

        # Per-quarter checkboxes
        seen_quarters = {}
        for disc in self._discrepancies:
            key = disc["report_date"]
            if key not in seen_quarters:
                seen_quarters[key] = disc

        checkbox_layout = QVBoxLayout()
        for report_date, disc in seen_quarters.items():
            label = f"{disc['quarter']} {disc['year']} ({report_date})"
            cb = QCheckBox(f"Override {label} with yfinance")
            cb.setChecked(True)
            cb.setProperty("report_date", report_date)
            cb.setProperty("yfinance_record", disc["yfinance_record"])
            self._checkboxes.append(cb)
            checkbox_layout.addWidget(cb)

        layout.addLayout(checkbox_layout)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        keep_btn = QPushButton("Keep EODHD")
        keep_btn.setProperty("secondary", True)
        keep_btn.clicked.connect(self.reject)
        button_layout.addWidget(keep_btn)

        accept_btn = QPushButton("Accept yfinance")
        accept_btn.clicked.connect(self._on_accept)
        button_layout.addWidget(accept_btn)

        layout.addLayout(button_layout)

    def _on_accept(self) -> None:
        """Collect selected overrides and accept."""
        self._selected_overrides = []
        for cb in self._checkboxes:
            if cb.isChecked():
                self._selected_overrides.append(cb.property("yfinance_record"))
        self.accept()

    def get_selected_overrides(self) -> List[Dict[str, Any]]:
        """Return the list of yfinance records selected for override."""
        return self._selected_overrides

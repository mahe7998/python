"""Add stock dialog with search functionality."""

from typing import Optional, List, Callable

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QComboBox,
    QGroupBox,
    QFormLayout,
    QCheckBox,
    QWidget,
    QProgressBar,
)

from investment_tool.data.models import CompanyInfo
from investment_tool.data.manager import DataManager


class AddStockDialog(QDialog):
    """Dialog for searching and adding stocks."""

    stock_added = Signal(str, str)  # ticker, exchange

    def __init__(
        self,
        data_manager: Optional[DataManager] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.data_manager = data_manager
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._perform_search)
        self._search_results: List[CompanyInfo] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        self.setWindowTitle("Add Stock")
        self.setMinimumSize(500, 450)

        layout = QVBoxLayout(self)

        # Search section
        search_group = QGroupBox("Search")
        search_layout = QVBoxLayout(search_group)

        # Search input
        search_input_layout = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter ticker or company name...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._perform_search)
        search_input_layout.addWidget(self.search_input)

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._perform_search)
        search_input_layout.addWidget(self.search_btn)

        search_layout.addLayout(search_input_layout)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.hide()
        search_layout.addWidget(self.progress_bar)

        # Results list
        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self._on_result_double_clicked)
        self.results_list.currentItemChanged.connect(self._on_result_selected)
        search_layout.addWidget(self.results_list)

        layout.addWidget(search_group)

        # Manual entry section
        manual_group = QGroupBox("Or Enter Manually")
        manual_layout = QFormLayout(manual_group)

        self.ticker_input = QLineEdit()
        self.ticker_input.setPlaceholderText("e.g., AAPL")
        manual_layout.addRow("Ticker:", self.ticker_input)

        self.exchange_combo = QComboBox()
        self.exchange_combo.addItems([
            "US", "XETRA", "LSE", "TSE", "HK", "SHG", "SHE",
            "PA", "AS", "SW", "MI", "MC", "TO", "V", "AX"
        ])
        manual_layout.addRow("Exchange:", self.exchange_combo)

        layout.addWidget(manual_group)

        # Options
        options_layout = QHBoxLayout()

        self.add_to_watchlist = QCheckBox("Add to current watchlist")
        self.add_to_watchlist.setChecked(True)
        options_layout.addWidget(self.add_to_watchlist)

        self.fetch_data = QCheckBox("Fetch historical data")
        self.fetch_data.setChecked(True)
        options_layout.addWidget(self.fetch_data)

        options_layout.addStretch()

        layout.addLayout(options_layout)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("secondary", True)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.add_btn = QPushButton("Add Stock")
        self.add_btn.clicked.connect(self._on_add)
        self.add_btn.setEnabled(False)
        button_layout.addWidget(self.add_btn)

        layout.addLayout(button_layout)

        # Connect ticker input to enable/disable add button
        self.ticker_input.textChanged.connect(self._update_add_button)

    def set_data_manager(self, manager: DataManager) -> None:
        """Set the data manager for search functionality."""
        self.data_manager = manager

    def _on_search_text_changed(self, text: str) -> None:
        """Handle search text change with debouncing."""
        # Reset timer on each keystroke
        self._search_timer.stop()

        if len(text) >= 2:
            # Wait 300ms before searching
            self._search_timer.start(300)

    def _perform_search(self) -> None:
        """Perform the search."""
        query = self.search_input.text().strip()

        if len(query) < 2:
            return

        if not self.data_manager:
            # Show message about no data manager
            self.results_list.clear()
            self.results_list.addItem("Search requires API connection")
            return

        self.progress_bar.show()
        self.search_btn.setEnabled(False)

        try:
            self._search_results = self.data_manager.search_tickers(query)
            self._display_results()
        except Exception as e:
            self.results_list.clear()
            self.results_list.addItem(f"Search error: {str(e)}")
        finally:
            self.progress_bar.hide()
            self.search_btn.setEnabled(True)

    def _display_results(self) -> None:
        """Display search results."""
        self.results_list.clear()

        if not self._search_results:
            self.results_list.addItem("No results found")
            return

        for company in self._search_results:
            text = f"{company.ticker}.{company.exchange} - {company.name}"
            if company.country:
                text += f" ({company.country})"

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, company)
            self.results_list.addItem(item)

    def _on_result_selected(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        """Handle result selection."""
        if current is None:
            return

        company = current.data(Qt.UserRole)
        if isinstance(company, CompanyInfo):
            self.ticker_input.setText(company.ticker)

            # Set exchange if in combo box
            idx = self.exchange_combo.findText(company.exchange)
            if idx >= 0:
                self.exchange_combo.setCurrentIndex(idx)

            self._update_add_button()

    def _on_result_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle result double-click to add immediately."""
        company = item.data(Qt.UserRole)
        if isinstance(company, CompanyInfo):
            self.ticker_input.setText(company.ticker)
            idx = self.exchange_combo.findText(company.exchange)
            if idx >= 0:
                self.exchange_combo.setCurrentIndex(idx)
            self._on_add()

    def _update_add_button(self) -> None:
        """Update add button enabled state."""
        ticker = self.ticker_input.text().strip()
        self.add_btn.setEnabled(len(ticker) > 0)

    def _on_add(self) -> None:
        """Handle add button click."""
        ticker = self.ticker_input.text().strip().upper()
        exchange = self.exchange_combo.currentText()

        if not ticker:
            return

        # Emit signal
        self.stock_added.emit(ticker, exchange)

        # Optionally fetch data
        if self.fetch_data.isChecked() and self.data_manager:
            try:
                self.data_manager.refresh_company_data(ticker, exchange)
            except Exception:
                pass  # Silently fail data fetch

        self.accept()

    def get_result(self) -> tuple:
        """Get the selected stock and options."""
        return (
            self.ticker_input.text().strip().upper(),
            self.exchange_combo.currentText(),
            self.add_to_watchlist.isChecked(),
            self.fetch_data.isChecked(),
        )

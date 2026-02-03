"""Add stock dialog with search functionality."""

from typing import Optional, List

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
    QCheckBox,
    QWidget,
    QProgressBar,
    QApplication,
)

from investment_tool.data.models import CompanyInfo
from investment_tool.data.manager import DataManager
from investment_tool.config.categories import get_category_manager

# Country code to flag emoji mapping
COUNTRY_FLAGS = {
    "USA": "US",
    "United States": "US",
    "UK": "GB",
    "United Kingdom": "GB",
    "Germany": "DE",
    "France": "FR",
    "Japan": "JP",
    "China": "CN",
    "Hong Kong": "HK",
    "Canada": "CA",
    "Australia": "AU",
    "Switzerland": "CH",
    "Netherlands": "NL",
    "Spain": "ES",
    "Italy": "IT",
    "Brazil": "BR",
    "India": "IN",
    "South Korea": "KR",
    "Taiwan": "TW",
    "Singapore": "SG",
    "Mexico": "MX",
    "Sweden": "SE",
    "Norway": "NO",
    "Denmark": "DK",
    "Finland": "FI",
    "Belgium": "BE",
    "Austria": "AT",
    "Ireland": "IE",
    "Portugal": "PT",
    "Poland": "PL",
    "Russia": "RU",
    "South Africa": "ZA",
    "Israel": "IL",
    "New Zealand": "NZ",
}


def get_flag_emoji(country: str) -> str:
    """Convert country name to flag emoji."""
    if not country:
        return ""
    code = COUNTRY_FLAGS.get(country, country[:2].upper() if len(country) >= 2 else "")
    if len(code) == 2:
        # Convert country code to flag emoji
        return chr(ord(code[0]) + 127397) + chr(ord(code[1]) + 127397)
    return ""


class AddStockDialog(QDialog):
    """Dialog for searching and adding stocks."""

    stock_added = Signal(str, str)  # ticker, exchange

    # Asset type options for filter
    ASSET_TYPES = [
        ("All Types", None),
        ("Stocks", "stock"),
        ("ETFs", "etf"),
        ("Funds", "fund"),
        ("Indices", "index"),
        ("Bonds", "bond"),
        ("Crypto", "crypto"),
    ]

    # Common exchanges for filter
    EXCHANGES = [
        ("All Markets", None),
        ("US (NYSE/NASDAQ)", "US"),
        ("London (LSE)", "LSE"),
        ("Germany (XETRA)", "XETRA"),
        ("France (Paris)", "PA"),
        ("Japan (Tokyo)", "TSE"),
        ("Hong Kong", "HK"),
        ("China (Shanghai)", "SHG"),
        ("China (Shenzhen)", "SHE"),
        ("Canada (Toronto)", "TO"),
        ("Australia (ASX)", "AU"),
        ("Switzerland", "SW"),
        ("Netherlands", "AS"),
        ("Spain (Madrid)", "MC"),
        ("Italy (Milan)", "MI"),
        ("Brazil", "SA"),
        ("India (NSE)", "NSE"),
        ("India (BSE)", "BSE"),
        ("South Korea", "KO"),
        ("Taiwan", "TW"),
        ("Singapore", "SG"),
    ]

    def __init__(
        self,
        data_manager: Optional[DataManager] = None,
        parent: Optional[QWidget] = None,
        require_category: bool = True,
    ):
        super().__init__(parent)
        self.data_manager = data_manager
        self.category_manager = get_category_manager()
        self._require_category = require_category
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._perform_search)
        self._search_results: List[CompanyInfo] = []
        self._selected_company: Optional[CompanyInfo] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        self.setWindowTitle("Add Stock")
        self.setMinimumSize(600, 550)
        self.setStyleSheet("""
            QDialog {
                background: #111827;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #374151;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
                background: #1F2937;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #F3F4F6;
            }
            QLineEdit {
                background: #374151;
                border: 1px solid #4B5563;
                border-radius: 6px;
                padding: 10px 12px;
                font-size: 14px;
                color: #F3F4F6;
            }
            QLineEdit:focus {
                border-color: #3B82F6;
            }
            QLineEdit::placeholder {
                color: #6B7280;
            }
            QComboBox {
                background: #374151;
                border: 1px solid #4B5563;
                border-radius: 6px;
                padding: 6px 10px;
                color: #F3F4F6;
                min-width: 120px;
            }
            QComboBox:hover {
                border-color: #4B5563;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background: #374151;
                border: 1px solid #4B5563;
                selection-background-color: #3B82F6;
                color: #F3F4F6;
            }
            QListWidget {
                background: #111827;
                border: 1px solid #374151;
                border-radius: 6px;
                outline: none;
            }
            QListWidget::item {
                padding: 4px;
                border: none;
            }
            QListWidget::item:selected {
                background: transparent;
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
                spacing: 8px;
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
            QLabel {
                color: #F3F4F6;
            }
            QProgressBar {
                border: none;
                border-radius: 3px;
                background: #374151;
                height: 6px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #3B82F6;
                border-radius: 3px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Search section
        search_group = QGroupBox("Search Stocks, ETFs, or Indices")
        search_layout = QVBoxLayout(search_group)
        search_layout.setSpacing(12)

        # Search input with icon
        search_input_layout = QHBoxLayout()
        search_input_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter ticker, company name, or ISIN...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._perform_search)
        search_input_layout.addWidget(self.search_input, stretch=1)

        self.search_btn = QPushButton("Search")
        self.search_btn.setFixedWidth(80)
        self.search_btn.clicked.connect(self._perform_search)
        search_input_layout.addWidget(self.search_btn)

        search_layout.addLayout(search_input_layout)

        # Filter row
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(12)

        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        filter_layout.addWidget(filter_label)

        self.type_combo = QComboBox()
        for label, _ in self.ASSET_TYPES:
            self.type_combo.addItem(label)
        self.type_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.type_combo)

        exchange_label = QLabel("Exchange:")
        exchange_label.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        filter_layout.addWidget(exchange_label)

        self.exchange_combo = QComboBox()
        for label, _ in self.EXCHANGES:
            self.exchange_combo.addItem(label)
        self.exchange_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.exchange_combo)

        filter_layout.addStretch()

        search_layout.addLayout(filter_layout)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.hide()
        search_layout.addWidget(self.progress_bar)

        # Results list
        self.results_list = QListWidget()
        self.results_list.setMinimumHeight(250)
        self.results_list.setSpacing(4)
        self.results_list.itemClicked.connect(self._on_result_clicked)
        self.results_list.itemDoubleClicked.connect(self._on_result_double_clicked)
        search_layout.addWidget(self.results_list)

        # Selection label
        self.selection_label = QLabel("No stock selected")
        self.selection_label.setStyleSheet("color: #9CA3AF; font-style: italic; padding: 4px;")
        search_layout.addWidget(self.selection_label)

        layout.addWidget(search_group)

        # Options section
        options_group = QGroupBox("Options")
        options_layout = QHBoxLayout(options_group)
        options_layout.setSpacing(16)

        # Category selector
        cat_label = QLabel("Add to category:")
        cat_label.setStyleSheet("color: #9CA3AF;")
        options_layout.addWidget(cat_label)

        self.category_combo = QComboBox()
        # Add placeholder to prompt user to select a category
        self.category_combo.addItem("-- Select Category --", None)
        categories = self.category_manager.get_all_categories()
        for category in categories:
            # Filter out "Uncategorized" - stocks must be assigned to a proper category
            if category.name != "Uncategorized":
                self.category_combo.addItem(category.name, category.id)
        self.category_combo.setMinimumWidth(180)
        options_layout.addWidget(self.category_combo)

        options_layout.addStretch()

        self.fetch_data = QCheckBox("Fetch historical data")
        self.fetch_data.setChecked(True)
        options_layout.addWidget(self.fetch_data)

        layout.addWidget(options_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
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

    def set_data_manager(self, manager: DataManager) -> None:
        """Set the data manager for search functionality."""
        self.data_manager = manager

    def _on_search_text_changed(self, text: str) -> None:
        """Handle search text change with debouncing."""
        self._search_timer.stop()

        if len(text) >= 2:
            self._search_timer.start(400)

    def _on_filter_changed(self) -> None:
        """Handle filter change - re-run search if we have results."""
        if self.search_input.text().strip() and self._search_results:
            self._perform_search()

    def _perform_search(self) -> None:
        """Perform the search."""
        query = self.search_input.text().strip()

        if len(query) < 2:
            return

        if not self.data_manager:
            self.results_list.clear()
            item = QListWidgetItem("Search requires API connection")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.results_list.addItem(item)
            return

        self.progress_bar.show()
        self.search_btn.setEnabled(False)
        QApplication.processEvents()

        try:
            # Get filter values
            type_idx = self.type_combo.currentIndex()
            asset_type = self.ASSET_TYPES[type_idx][1] if type_idx > 0 else None

            exchange_idx = self.exchange_combo.currentIndex()
            exchange = self.EXCHANGES[exchange_idx][1] if exchange_idx > 0 else None

            self._search_results = self.data_manager.search_tickers(
                query,
                limit=50,
                asset_type=asset_type,
                exchange=exchange,
            )
            self._display_results()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.results_list.clear()
            item = QListWidgetItem(f"Search error: {str(e)}")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.results_list.addItem(item)
        finally:
            self.progress_bar.hide()
            self.search_btn.setEnabled(True)

    def _display_results(self) -> None:
        """Display search results."""
        self.results_list.clear()
        self._selected_company = None
        self.selection_label.setText("No stock selected")
        self.add_btn.setEnabled(False)

        if not self._search_results:
            item = QListWidgetItem("No results found")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.results_list.addItem(item)
            return

        for company in self._search_results:
            # Build display text
            ticker_ex = f"{company.ticker}.{company.exchange}"
            name = company.name or ""

            # Price info
            price_str = ""
            if company.previous_close:
                currency = company.currency or "USD"
                symbols = {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "JPY": "\u00a5", "HKD": "HK$"}
                sym = symbols.get(currency, currency + " ")
                price_str = f" - {sym}{company.previous_close:,.2f}"

            # Type and country (no emojis - they crash Qt on macOS)
            type_str = f" [{company.asset_type}]" if company.asset_type else ""
            country_str = f" ({company.country})" if company.country else ""

            # Combine into display text
            display = f"{ticker_ex}  {name}{price_str}{type_str}{country_str}"

            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, company)
            self.results_list.addItem(item)

    def _on_result_clicked(self, item: QListWidgetItem) -> None:
        """Handle result click."""
        company = item.data(Qt.UserRole)
        if isinstance(company, CompanyInfo):
            self._selected_company = company
            self.selection_label.setText(
                f"Selected: {company.ticker}.{company.exchange} - {company.name}"
            )
            self.selection_label.setStyleSheet("color: #10B981; font-weight: bold; padding: 4px;")
            self.add_btn.setEnabled(True)

    def _on_result_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle result double-click to add immediately."""
        company = item.data(Qt.UserRole)
        if isinstance(company, CompanyInfo):
            self._selected_company = company
            self._on_add()

    def _on_add(self) -> None:
        """Handle add button click."""
        from loguru import logger

        if not self._selected_company:
            logger.warning("No company selected")
            return

        ticker = self._selected_company.ticker
        exchange = self._selected_company.exchange
        logger.info(f"Adding stock: {ticker}.{exchange}")

        # Add to category - use selected or first available category
        category_id = self.category_combo.currentData()
        logger.info(f"Selected category_id: {category_id}")

        if not category_id and self._require_category:
            # No category selected - require user to choose one
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Category Required",
                "Please select a category for this stock."
            )
            return

        if category_id:
            added = self.category_manager.add_stock_to_category(category_id, ticker, exchange)
            if added:
                logger.info(f"Added {ticker}.{exchange} to category {category_id}")
                # Auto-save
                from pathlib import Path
                save_path = Path.home() / ".investment_tool" / "categories.json"
                self.category_manager.save_to_file(save_path)
                logger.info(f"Saved categories to {save_path}")
                # Emit signal to refresh treemap
                self.stock_added.emit(ticker, exchange)
                logger.info(f"Emitted stock_added signal for {ticker}.{exchange}")
            else:
                # Stock already exists in this category
                category = self.category_manager.get_category(category_id)
                cat_name = category.name if category else str(category_id)
                logger.info(f"{ticker}.{exchange} already exists in category '{cat_name}'")
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self,
                    "Stock Already Added",
                    f"{ticker}.{exchange} is already in category '{cat_name}'."
                )
                return  # Don't close dialog - let user pick different category
        else:
            logger.warning("No category available to add stock")

        # Optionally fetch data
        if self.fetch_data.isChecked() and self.data_manager:
            try:
                self.data_manager.refresh_company_data(ticker, exchange)
            except Exception:
                pass  # Silently fail data fetch

        self.accept()

    def get_result(self) -> tuple:
        """Get the selected stock and options."""
        if self._selected_company:
            return (
                self._selected_company.ticker,
                self._selected_company.exchange,
                self.category_combo.currentData(),
                self.fetch_data.isChecked(),
            )
        return ("", "", None, False)

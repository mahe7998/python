"""Category management dialog."""

from typing import Optional, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLineEdit,
    QLabel,
    QColorDialog,
    QGroupBox,
    QFormLayout,
    QMessageBox,
    QInputDialog,
    QWidget,
    QSplitter,
)

from investment_tool.config.categories import (
    Category,
    StockReference,
    CategoryManager,
    get_category_manager,
)


class CategoryDialog(QDialog):
    """Dialog for managing stock categories."""

    categories_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.category_manager = get_category_manager()
        self._current_category: Optional[Category] = None

        self._setup_ui()
        self._load_categories()

    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        self.setWindowTitle("Manage Categories")
        self.setMinimumSize(700, 500)

        layout = QVBoxLayout(self)

        # Main content with splitter
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, stretch=1)

        # Left panel - Category list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_label = QLabel("Categories")
        left_label.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(left_label)

        self.category_list = QListWidget()
        self.category_list.currentItemChanged.connect(self._on_category_selected)
        left_layout.addWidget(self.category_list)

        # Category list buttons
        cat_btn_layout = QHBoxLayout()

        self.add_cat_btn = QPushButton("Add")
        self.add_cat_btn.clicked.connect(self._on_add_category)
        cat_btn_layout.addWidget(self.add_cat_btn)

        self.remove_cat_btn = QPushButton("Remove")
        self.remove_cat_btn.clicked.connect(self._on_remove_category)
        cat_btn_layout.addWidget(self.remove_cat_btn)

        left_layout.addLayout(cat_btn_layout)

        splitter.addWidget(left_panel)

        # Right panel - Category details
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Category properties
        props_group = QGroupBox("Category Properties")
        props_layout = QFormLayout(props_group)

        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._on_name_changed)
        props_layout.addRow("Name:", self.name_edit)

        color_layout = QHBoxLayout()
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(24, 24)
        self.color_preview.setStyleSheet("border: 1px solid #4B5563; border-radius: 4px;")
        color_layout.addWidget(self.color_preview)

        self.color_btn = QPushButton("Choose Color")
        self.color_btn.clicked.connect(self._on_choose_color)
        color_layout.addWidget(self.color_btn)
        color_layout.addStretch()

        props_layout.addRow("Color:", color_layout)

        self.desc_edit = QLineEdit()
        self.desc_edit.textChanged.connect(self._on_description_changed)
        props_layout.addRow("Description:", self.desc_edit)

        right_layout.addWidget(props_group)

        # Stocks in category
        stocks_group = QGroupBox("Stocks in Category")
        stocks_layout = QVBoxLayout(stocks_group)

        self.stock_list = QListWidget()
        stocks_layout.addWidget(self.stock_list)

        stock_btn_layout = QHBoxLayout()

        self.add_stock_btn = QPushButton("Add Stock")
        self.add_stock_btn.clicked.connect(self._on_add_stock)
        stock_btn_layout.addWidget(self.add_stock_btn)

        self.remove_stock_btn = QPushButton("Remove Stock")
        self.remove_stock_btn.clicked.connect(self._on_remove_stock)
        stock_btn_layout.addWidget(self.remove_stock_btn)

        stocks_layout.addLayout(stock_btn_layout)

        right_layout.addWidget(stocks_group)

        splitter.addWidget(right_panel)

        # Set splitter sizes
        splitter.setSizes([200, 500])

        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_btn = QPushButton("Save All")
        self.save_btn.clicked.connect(self._on_save)
        button_layout.addWidget(self.save_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

        # Initially disable right panel
        self._set_details_enabled(False)

    def _load_categories(self) -> None:
        """Load categories into the list."""
        self.category_list.clear()

        for category in self.category_manager.get_all_categories():
            item = QListWidgetItem(category.name)
            item.setData(Qt.UserRole, category.id)

            # Set color indicator
            color = QColor(category.color)
            item.setForeground(color)

            self.category_list.addItem(item)

    def _on_category_selected(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        """Handle category selection."""
        if current is None:
            self._current_category = None
            self._set_details_enabled(False)
            return

        category_id = current.data(Qt.UserRole)
        self._current_category = self.category_manager.get_category(category_id)

        if self._current_category:
            self._set_details_enabled(True)
            self._update_details()

    def _set_details_enabled(self, enabled: bool) -> None:
        """Enable or disable the details panel."""
        self.name_edit.setEnabled(enabled)
        self.color_btn.setEnabled(enabled)
        self.desc_edit.setEnabled(enabled)
        self.stock_list.setEnabled(enabled)
        self.add_stock_btn.setEnabled(enabled)
        self.remove_stock_btn.setEnabled(enabled)

        if not enabled:
            self.name_edit.clear()
            self.desc_edit.clear()
            self.stock_list.clear()
            self.color_preview.setStyleSheet(
                "border: 1px solid #4B5563; border-radius: 4px; background: transparent;"
            )

    def _update_details(self) -> None:
        """Update the details panel with current category."""
        if not self._current_category:
            return

        # Block signals to prevent triggering change handlers
        self.name_edit.blockSignals(True)
        self.desc_edit.blockSignals(True)

        self.name_edit.setText(self._current_category.name)
        self.desc_edit.setText(self._current_category.description or "")

        self.color_preview.setStyleSheet(
            f"border: 1px solid #4B5563; border-radius: 4px; "
            f"background: {self._current_category.color};"
        )

        self.name_edit.blockSignals(False)
        self.desc_edit.blockSignals(False)

        # Load stocks
        self.stock_list.clear()
        for stock in self._current_category.stocks:
            item = QListWidgetItem(f"{stock.ticker}.{stock.exchange}")
            item.setData(Qt.UserRole, stock)
            self.stock_list.addItem(item)

    def _on_name_changed(self, text: str) -> None:
        """Handle name change."""
        if self._current_category:
            self._current_category.name = text

            # Update list item
            current_item = self.category_list.currentItem()
            if current_item:
                current_item.setText(text)

    def _on_description_changed(self, text: str) -> None:
        """Handle description change."""
        if self._current_category:
            self._current_category.description = text if text else None

    def _on_choose_color(self) -> None:
        """Open color picker."""
        if not self._current_category:
            return

        initial_color = QColor(self._current_category.color)
        color = QColorDialog.getColor(initial_color, self, "Choose Category Color")

        if color.isValid():
            self._current_category.color = color.name()
            self.color_preview.setStyleSheet(
                f"border: 1px solid #4B5563; border-radius: 4px; "
                f"background: {color.name()};"
            )

            # Update list item color
            current_item = self.category_list.currentItem()
            if current_item:
                current_item.setForeground(color)

    def _on_add_category(self) -> None:
        """Add a new category."""
        name, ok = QInputDialog.getText(
            self, "New Category", "Enter category name:"
        )

        if ok and name:
            category = self.category_manager.add_category(
                name=name.strip(),
                color="#6B7280",  # Default gray
            )

            # Add to list and select
            item = QListWidgetItem(category.name)
            item.setData(Qt.UserRole, category.id)
            item.setForeground(QColor(category.color))
            self.category_list.addItem(item)
            self.category_list.setCurrentItem(item)

    def _on_remove_category(self) -> None:
        """Remove the selected category."""
        current_item = self.category_list.currentItem()
        if not current_item:
            return

        category_id = current_item.data(Qt.UserRole)
        category = self.category_manager.get_category(category_id)

        if not category:
            return

        result = QMessageBox.question(
            self, "Delete Category",
            f"Are you sure you want to delete '{category.name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if result == QMessageBox.Yes:
            self.category_manager.delete_category(category_id)
            row = self.category_list.row(current_item)
            self.category_list.takeItem(row)

    def _on_add_stock(self) -> None:
        """Add a stock to the current category."""
        if not self._current_category:
            return

        text, ok = QInputDialog.getText(
            self, "Add Stock",
            "Enter ticker (e.g., AAPL or AAPL.US):"
        )

        if ok and text:
            text = text.strip().upper()

            # Parse ticker and exchange
            if "." in text:
                ticker, exchange = text.rsplit(".", 1)
            else:
                ticker = text
                exchange = "US"

            # Check if already in category
            for stock in self._current_category.stocks:
                if stock.ticker == ticker and stock.exchange == exchange:
                    QMessageBox.information(
                        self, "Already Added",
                        f"{ticker}.{exchange} is already in this category."
                    )
                    return

            # Add stock
            stock_ref = StockReference(ticker=ticker, exchange=exchange)
            self._current_category.stocks.append(stock_ref)

            # Update list
            item = QListWidgetItem(f"{ticker}.{exchange}")
            item.setData(Qt.UserRole, stock_ref)
            self.stock_list.addItem(item)

            # Auto-save
            self._auto_save()

    def _on_remove_stock(self) -> None:
        """Remove a stock from the current category."""
        if not self._current_category:
            return

        current_item = self.stock_list.currentItem()
        if not current_item:
            return

        stock_ref = current_item.data(Qt.UserRole)
        if stock_ref in self._current_category.stocks:
            self._current_category.stocks.remove(stock_ref)

        row = self.stock_list.row(current_item)
        self.stock_list.takeItem(row)

        # Auto-save
        self._auto_save()

    def _auto_save(self) -> None:
        """Auto-save changes and notify."""
        from pathlib import Path
        save_path = Path.home() / ".investment_tool" / "categories.json"
        self.category_manager.save_to_file(save_path)
        self.categories_changed.emit()

    def _on_save(self) -> None:
        """Save all changes."""
        # Update all categories in the manager
        for category in self.category_manager.get_all_categories():
            self.category_manager.update_category(category)

        # Save to file
        from pathlib import Path
        save_path = Path.home() / ".investment_tool" / "categories.json"
        self.category_manager.save_to_file(save_path)

        self.categories_changed.emit()

        QMessageBox.information(
            self, "Saved",
            "Categories have been saved successfully."
        )

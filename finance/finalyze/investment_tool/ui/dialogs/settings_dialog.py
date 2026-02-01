"""Settings dialog for configuring application options."""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QTabWidget,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QGroupBox,
    QFileDialog,
    QMessageBox,
)

from investment_tool.config.settings import AppConfig


class SettingsDialog(QDialog):
    """Dialog for configuring application settings."""

    def __init__(self, config: AppConfig, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        """Setup dialog UI."""
        self.setWindowTitle("Settings")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        tabs.addTab(self._create_api_tab(), "API Keys")
        tabs.addTab(self._create_data_tab(), "Data")
        tabs.addTab(self._create_ui_tab(), "Interface")
        tabs.addTab(self._create_analysis_tab(), "Analysis")

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("secondary", True)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_settings)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    def _create_api_tab(self) -> QWidget:
        """Create API keys configuration tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        eodhd_group = QGroupBox("EODHD (Primary)")
        eodhd_layout = QFormLayout(eodhd_group)

        self.eodhd_key = QLineEdit()
        self.eodhd_key.setEchoMode(QLineEdit.Password)
        self.eodhd_key.setPlaceholderText("Enter your EODHD API key")
        eodhd_layout.addRow("API Key:", self.eodhd_key)

        show_key_btn = QPushButton("Show")
        show_key_btn.setCheckable(True)
        show_key_btn.toggled.connect(
            lambda checked: self.eodhd_key.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        eodhd_layout.addRow("", show_key_btn)

        layout.addWidget(eodhd_group)

        optional_group = QGroupBox("Optional Providers")
        optional_layout = QFormLayout(optional_group)

        self.polygon_key = QLineEdit()
        self.polygon_key.setEchoMode(QLineEdit.Password)
        self.polygon_key.setPlaceholderText("Optional - for US tick data")
        optional_layout.addRow("Polygon.io:", self.polygon_key)

        self.finnhub_key = QLineEdit()
        self.finnhub_key.setEchoMode(QLineEdit.Password)
        self.finnhub_key.setPlaceholderText("Optional - for social sentiment")
        optional_layout.addRow("Finnhub:", self.finnhub_key)

        layout.addWidget(optional_group)
        layout.addStretch()

        return widget

    def _create_data_tab(self) -> QWidget:
        """Create data settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        storage_group = QGroupBox("Storage")
        storage_layout = QFormLayout(storage_group)

        db_layout = QHBoxLayout()
        self.database_path = QLineEdit()
        self.database_path.setReadOnly(True)
        db_layout.addWidget(self.database_path)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_database)
        db_layout.addWidget(browse_btn)
        storage_layout.addRow("Database:", db_layout)

        self.cache_age = QSpinBox()
        self.cache_age.setRange(1, 30)
        self.cache_age.setSuffix(" days")
        storage_layout.addRow("Max Cache Age:", self.cache_age)

        layout.addWidget(storage_group)

        refresh_group = QGroupBox("Auto Refresh")
        refresh_layout = QFormLayout(refresh_group)

        self.refresh_interval = QSpinBox()
        self.refresh_interval.setRange(1, 60)
        self.refresh_interval.setSuffix(" minutes")
        refresh_layout.addRow("Refresh Interval:", self.refresh_interval)

        layout.addWidget(refresh_group)
        layout.addStretch()

        return widget

    def _create_ui_tab(self) -> QWidget:
        """Create UI settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        appearance_group = QGroupBox("Appearance")
        appearance_layout = QFormLayout(appearance_group)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        appearance_layout.addRow("Theme:", self.theme_combo)

        self.chart_type_combo = QComboBox()
        self.chart_type_combo.addItems(["candlestick", "ohlc", "line", "area"])
        appearance_layout.addRow("Default Chart Type:", self.chart_type_combo)

        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(["1D", "1W", "1M", "3M", "6M", "1Y", "YTD"])
        appearance_layout.addRow("Default Timeframe:", self.timeframe_combo)

        layout.addWidget(appearance_group)
        layout.addStretch()

        return widget

    def _create_analysis_tab(self) -> QWidget:
        """Create analysis settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        sentiment_group = QGroupBox("Sentiment Analysis")
        sentiment_layout = QFormLayout(sentiment_group)

        self.use_finbert = QCheckBox("Enable local FinBERT analysis")
        sentiment_layout.addRow("", self.use_finbert)

        layout.addWidget(sentiment_group)

        backtest_group = QGroupBox("Backtesting")
        backtest_layout = QFormLayout(backtest_group)

        self.initial_capital = QSpinBox()
        self.initial_capital.setRange(1000, 10000000)
        self.initial_capital.setSingleStep(10000)
        self.initial_capital.setPrefix("$")
        backtest_layout.addRow("Initial Capital:", self.initial_capital)

        layout.addWidget(backtest_group)
        layout.addStretch()

        return widget

    def _load_settings(self) -> None:
        """Load current settings into the dialog."""
        self.eodhd_key.setText(self.config.api_keys.eodhd or "")
        self.polygon_key.setText(self.config.api_keys.polygon or "")
        self.finnhub_key.setText(self.config.api_keys.finnhub or "")

        self.database_path.setText(str(self.config.data.database_path))
        self.cache_age.setValue(self.config.data.max_cache_age_days)
        self.refresh_interval.setValue(self.config.data.auto_refresh_interval_minutes)

        self.theme_combo.setCurrentText(self.config.ui.theme)
        self.chart_type_combo.setCurrentText(self.config.ui.default_chart_type)
        self.timeframe_combo.setCurrentText(self.config.ui.default_timeframe)

        self.use_finbert.setChecked(self.config.analysis.sentiment.use_finbert)
        self.initial_capital.setValue(int(self.config.backtesting.default_initial_capital))

    def _save_settings(self) -> None:
        """Save settings from dialog."""
        self.config.api_keys.eodhd = self.eodhd_key.text() or None
        self.config.api_keys.polygon = self.polygon_key.text() or None
        self.config.api_keys.finnhub = self.finnhub_key.text() or None

        self.config.data.database_path = Path(self.database_path.text())
        self.config.data.max_cache_age_days = self.cache_age.value()
        self.config.data.auto_refresh_interval_minutes = self.refresh_interval.value()

        self.config.ui.theme = self.theme_combo.currentText()
        self.config.ui.default_chart_type = self.chart_type_combo.currentText()
        self.config.ui.default_timeframe = self.timeframe_combo.currentText()

        self.config.analysis.sentiment.use_finbert = self.use_finbert.isChecked()
        self.config.backtesting.default_initial_capital = float(self.initial_capital.value())

        try:
            config_path = Path.home() / ".investment_tool" / "settings.yaml"
            self.config.save(config_path)
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save settings: {e}"
            )

    def _browse_database(self) -> None:
        """Open file dialog to select database location."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Database Location",
            str(self.config.data.database_path),
            "DuckDB Files (*.duckdb);;All Files (*)",
        )
        if path:
            self.database_path.setText(path)

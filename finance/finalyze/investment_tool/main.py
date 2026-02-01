#!/usr/bin/env python3
"""
Investment Tracking & Analysis Tool

A local-only desktop application for comprehensive investment tracking
and analysis with interactive visualizations, multi-source data integration,
sentiment analysis, and reinforcement learning backtesting capabilities.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from loguru import logger

from investment_tool.config.settings import get_config, set_config, AppConfig
from investment_tool.utils.logging import setup_logging
from investment_tool.ui.main_window import MainWindow


def main() -> int:
    """Main application entry point."""
    config = get_config()

    setup_logging(
        log_file=config.logging.file,
        level=config.logging.level,
        max_size_mb=config.logging.max_size_mb,
        backup_count=config.logging.backup_count,
    )

    logger.info("Starting Investment Tracking & Analysis Tool")
    logger.info(f"Config loaded from: ~/.investment_tool/settings.yaml")
    logger.info(f"Database path: {config.data.database_path}")

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Investment Tool")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("InvestmentTool")

    window = MainWindow(config)
    window.show()

    logger.info("Application window opened")

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

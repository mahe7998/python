"""UI theme and styling definitions."""

from dataclasses import dataclass
from typing import Dict


@dataclass
class ColorPalette:
    """Color palette for the application."""
    primary: str = "#3B82F6"
    primary_hover: str = "#2563EB"
    secondary: str = "#6B7280"
    success: str = "#22C55E"
    warning: str = "#F59E0B"
    error: str = "#EF4444"
    background: str = "#1F2937"
    surface: str = "#374151"
    surface_light: str = "#4B5563"
    text: str = "#F9FAFB"
    text_secondary: str = "#9CA3AF"
    border: str = "#4B5563"
    positive: str = "#22C55E"
    negative: str = "#EF4444"
    neutral: str = "#6B7280"


@dataclass
class LightColorPalette(ColorPalette):
    """Light theme color palette."""
    background: str = "#F9FAFB"
    surface: str = "#FFFFFF"
    surface_light: str = "#F3F4F6"
    text: str = "#1F2937"
    text_secondary: str = "#6B7280"
    border: str = "#E5E7EB"


DARK_THEME = ColorPalette()
LIGHT_THEME = LightColorPalette()


def get_stylesheet(theme: str = "dark") -> str:
    """
    Generate Qt stylesheet for the application.

    Args:
        theme: 'dark' or 'light'

    Returns:
        Qt stylesheet string
    """
    colors = DARK_THEME if theme == "dark" else LIGHT_THEME

    return f"""
        /* Global */
        QWidget {{
            background-color: {colors.background};
            color: {colors.text};
            font-family: "Segoe UI", "SF Pro Display", -apple-system, sans-serif;
            font-size: 13px;
        }}

        /* Main Window */
        QMainWindow {{
            background-color: {colors.background};
        }}

        /* Menu Bar */
        QMenuBar {{
            background-color: {colors.surface};
            border-bottom: 1px solid {colors.border};
            padding: 4px;
        }}

        QMenuBar::item {{
            padding: 6px 12px;
            background: transparent;
            border-radius: 4px;
        }}

        QMenuBar::item:selected {{
            background-color: {colors.surface_light};
        }}

        QMenu {{
            background-color: {colors.surface};
            border: 1px solid {colors.border};
            border-radius: 8px;
            padding: 4px;
        }}

        QMenu::item {{
            padding: 8px 24px;
            border-radius: 4px;
        }}

        QMenu::item:selected {{
            background-color: {colors.primary};
        }}

        /* Tool Bar */
        QToolBar {{
            background-color: {colors.surface};
            border-bottom: 1px solid {colors.border};
            padding: 4px;
            spacing: 4px;
        }}

        QToolButton {{
            background-color: transparent;
            border: none;
            border-radius: 4px;
            padding: 8px;
        }}

        QToolButton:hover {{
            background-color: {colors.surface_light};
        }}

        QToolButton:pressed {{
            background-color: {colors.primary};
        }}

        /* Status Bar */
        QStatusBar {{
            background-color: {colors.surface};
            border-top: 1px solid {colors.border};
            padding: 4px;
        }}

        QStatusBar::item {{
            border: none;
        }}

        /* Push Button */
        QPushButton {{
            background-color: {colors.primary};
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: 500;
        }}

        QPushButton:hover {{
            background-color: {colors.primary_hover};
        }}

        QPushButton:pressed {{
            background-color: {colors.primary};
        }}

        QPushButton:disabled {{
            background-color: {colors.surface_light};
            color: {colors.text_secondary};
        }}

        QPushButton[secondary="true"] {{
            background-color: {colors.surface};
            border: 1px solid {colors.border};
        }}

        QPushButton[secondary="true"]:hover {{
            background-color: {colors.surface_light};
        }}

        /* Line Edit */
        QLineEdit {{
            background-color: {colors.surface};
            border: 1px solid {colors.border};
            border-radius: 6px;
            padding: 8px 12px;
            selection-background-color: {colors.primary};
        }}

        QLineEdit:focus {{
            border-color: {colors.primary};
        }}

        /* Combo Box */
        QComboBox {{
            background-color: {colors.surface};
            border: 1px solid {colors.border};
            border-radius: 6px;
            padding: 8px 12px;
            min-width: 100px;
        }}

        QComboBox:hover {{
            border-color: {colors.primary};
        }}

        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}

        QComboBox QAbstractItemView {{
            background-color: {colors.surface};
            border: 1px solid {colors.border};
            border-radius: 6px;
            selection-background-color: {colors.primary};
        }}

        /* Tab Widget */
        QTabWidget::pane {{
            border: 1px solid {colors.border};
            border-radius: 8px;
            background-color: {colors.surface};
        }}

        QTabBar::tab {{
            background-color: transparent;
            padding: 10px 20px;
            margin-right: 4px;
            border-bottom: 2px solid transparent;
        }}

        QTabBar::tab:selected {{
            border-bottom-color: {colors.primary};
            color: {colors.primary};
        }}

        QTabBar::tab:hover:!selected {{
            background-color: {colors.surface_light};
        }}

        /* Scroll Bar */
        QScrollBar:vertical {{
            background-color: {colors.surface};
            width: 12px;
            border-radius: 6px;
        }}

        QScrollBar::handle:vertical {{
            background-color: {colors.surface_light};
            border-radius: 6px;
            min-height: 30px;
        }}

        QScrollBar::handle:vertical:hover {{
            background-color: {colors.secondary};
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}

        QScrollBar:horizontal {{
            background-color: {colors.surface};
            height: 12px;
            border-radius: 6px;
        }}

        QScrollBar::handle:horizontal {{
            background-color: {colors.surface_light};
            border-radius: 6px;
            min-width: 30px;
        }}

        /* Table View */
        QTableView {{
            background-color: {colors.surface};
            alternate-background-color: {colors.surface_light};
            border: 1px solid {colors.border};
            border-radius: 8px;
            gridline-color: {colors.border};
        }}

        QTableView::item {{
            padding: 8px;
        }}

        QTableView::item:selected {{
            background-color: {colors.primary};
        }}

        QHeaderView::section {{
            background-color: {colors.surface};
            border: none;
            border-bottom: 1px solid {colors.border};
            padding: 10px;
            font-weight: 600;
        }}

        /* Tree View */
        QTreeView {{
            background-color: {colors.surface};
            border: 1px solid {colors.border};
            border-radius: 8px;
        }}

        QTreeView::item {{
            padding: 6px;
        }}

        QTreeView::item:selected {{
            background-color: {colors.primary};
        }}

        /* Splitter */
        QSplitter::handle {{
            background-color: {colors.border};
        }}

        QSplitter::handle:horizontal {{
            width: 2px;
        }}

        QSplitter::handle:vertical {{
            height: 2px;
        }}

        /* Group Box */
        QGroupBox {{
            border: 1px solid {colors.border};
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 12px;
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 4px;
        }}

        /* Label */
        QLabel {{
            background-color: transparent;
        }}

        /* Dock Widget */
        QDockWidget {{
            titlebar-close-icon: none;
            titlebar-normal-icon: none;
        }}

        QDockWidget::title {{
            background-color: {colors.surface};
            padding: 8px;
            border-bottom: 1px solid {colors.border};
        }}

        /* Progress Bar */
        QProgressBar {{
            background-color: {colors.surface};
            border: none;
            border-radius: 4px;
            height: 8px;
            text-align: center;
        }}

        QProgressBar::chunk {{
            background-color: {colors.primary};
            border-radius: 4px;
        }}

        /* Spin Box */
        QSpinBox, QDoubleSpinBox {{
            background-color: {colors.surface};
            border: 1px solid {colors.border};
            border-radius: 6px;
            padding: 8px;
        }}

        /* Date Edit */
        QDateEdit {{
            background-color: {colors.surface};
            border: 1px solid {colors.border};
            border-radius: 6px;
            padding: 8px;
        }}

        /* Check Box */
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {colors.border};
            border-radius: 4px;
            background-color: {colors.surface};
        }}

        QCheckBox::indicator:checked {{
            background-color: {colors.primary};
            border-color: {colors.primary};
        }}

        /* Tooltip */
        QToolTip {{
            background-color: {colors.surface};
            color: {colors.text};
            border: 1px solid {colors.border};
            border-radius: 4px;
            padding: 8px;
        }}
    """


def get_positive_style() -> Dict[str, str]:
    """Get style for positive values."""
    return {
        "color": DARK_THEME.positive,
        "font-weight": "500",
    }


def get_negative_style() -> Dict[str, str]:
    """Get style for negative values."""
    return {
        "color": DARK_THEME.negative,
        "font-weight": "500",
    }


def get_neutral_style() -> Dict[str, str]:
    """Get style for neutral values."""
    return {
        "color": DARK_THEME.text_secondary,
    }


def format_color_style(styles: Dict[str, str]) -> str:
    """Format style dictionary to CSS string."""
    return "; ".join(f"{k}: {v}" for k, v in styles.items())

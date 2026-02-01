"""Sentiment gauge widget with dial and trend chart."""

from datetime import date, timedelta
from typing import Optional, List
import math

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QFont, QPainterPath
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QSizePolicy,
)
import pyqtgraph as pg

from investment_tool.data.manager import DataManager
from investment_tool.data.models import DailySentiment


class GaugeWidget(QWidget):
    """Custom gauge dial widget using QPainter."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._value = 0.0  # -1.0 to 1.0
        self._label = "Neutral"
        self._color = QColor("#6B7280")

        self.setMinimumSize(120, 80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_value(self, value: float, label: str, color: str) -> None:
        """Set the gauge value and label."""
        self._value = max(-1.0, min(1.0, value))
        self._label = label
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:
        """Paint the gauge dial."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()

        # Calculate gauge dimensions
        margin = 10
        gauge_width = min(width - 2 * margin, (height - 30) * 2)
        gauge_height = gauge_width // 2
        center_x = width // 2
        center_y = height - 20

        # Draw arc background
        arc_rect = QRectF(
            center_x - gauge_width // 2,
            center_y - gauge_height,
            gauge_width,
            gauge_width
        )

        # Background arc (gray)
        pen = QPen(QColor("#374151"), 8)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(arc_rect, 180 * 16, 180 * 16)

        # Draw colored segments
        segment_colors = [
            ("#991B1B", -1.0, -0.7),   # Very Bearish
            ("#F87171", -0.7, -0.3),   # Bearish
            ("#6B7280", -0.3, 0.3),    # Neutral
            ("#22C55E", 0.3, 0.7),     # Bullish
            ("#166534", 0.7, 1.0),     # Very Bullish
        ]

        for color, start_val, end_val in segment_colors:
            # Convert value to angle (180 to 0 degrees)
            start_angle = int((1.0 - start_val) / 2.0 * 180) * 16
            span_angle = int((start_val - end_val) / 2.0 * 180) * 16

            pen = QPen(QColor(color), 4)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(arc_rect, start_angle, span_angle)

        # Draw needle
        needle_length = gauge_width // 2 - 15
        # Convert value (-1 to 1) to angle (180 to 0 degrees)
        angle = math.radians((1.0 - self._value) / 2.0 * 180)

        needle_x = center_x + needle_length * math.cos(angle)
        needle_y = center_y - needle_length * math.sin(angle)

        pen = QPen(self._color, 3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(center_x, center_y, int(needle_x), int(needle_y))

        # Draw center circle
        painter.setBrush(QBrush(self._color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center_x - 6, center_y - 6, 12, 12)

        # Draw value text
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(self._color))

        value_text = f"{self._value:+.2f}"
        text_rect = painter.fontMetrics().boundingRect(value_text)
        painter.drawText(
            center_x - text_rect.width() // 2,
            center_y - gauge_height // 2 - 5,
            value_text
        )

        # Draw label text
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QPen(self._color))

        label_rect = painter.fontMetrics().boundingRect(self._label)
        painter.drawText(
            center_x - label_rect.width() // 2,
            center_y - gauge_height // 2 + 15,
            self._label
        )


class SentimentGaugeWidget(QWidget):
    """Widget displaying sentiment gauge and trend chart."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._data_manager: Optional[DataManager] = None
        self._ticker: Optional[str] = None
        self._exchange: Optional[str] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Main group box
        self.group_box = QGroupBox("Sentiment")
        group_layout = QVBoxLayout(self.group_box)
        group_layout.setContentsMargins(8, 8, 8, 8)
        group_layout.setSpacing(4)

        # Top row: gauge and chart
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        # Gauge widget
        self.gauge = GaugeWidget()
        self.gauge.setMinimumSize(140, 90)
        top_row.addWidget(self.gauge, stretch=1)

        # Trend chart
        self.trend_chart = pg.PlotWidget()
        self.trend_chart.setBackground("#1F2937")
        self.trend_chart.setMinimumSize(200, 90)
        self.trend_chart.setMaximumHeight(100)
        self.trend_chart.showGrid(x=False, y=True, alpha=0.3)
        self.trend_chart.getAxis("left").setStyle(tickLength=-5)
        self.trend_chart.getAxis("bottom").setStyle(tickTextOffset=3)
        self.trend_chart.setLabel("left", "")
        self.trend_chart.setLabel("bottom", "")
        self.trend_chart.getPlotItem().setTitle("30-Day Trend", size="8pt", color="#9CA3AF")
        # Add zero line
        self.zero_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen("#6B7280", width=1, style=Qt.DashLine))
        self.trend_chart.addItem(self.zero_line)
        top_row.addWidget(self.trend_chart, stretch=2)

        group_layout.addLayout(top_row)

        # Bottom row: article counts
        self.summary_label = QLabel("No data available")
        self.summary_label.setStyleSheet("color: #9CA3AF; font-size: 10px;")
        self.summary_label.setAlignment(Qt.AlignCenter)
        group_layout.addWidget(self.summary_label)

        layout.addWidget(self.group_box)

    def set_data_manager(self, data_manager: DataManager) -> None:
        """Set the data manager."""
        self._data_manager = data_manager

    def set_ticker(self, ticker: str, exchange: str) -> None:
        """Set the current ticker and update the display."""
        self._ticker = ticker
        self._exchange = exchange
        self.group_box.setTitle(f"Sentiment - {ticker}")

        self._update_display()

    def _update_display(self) -> None:
        """Update the gauge and chart with current data."""
        if not self._data_manager or not self._ticker:
            self._show_no_data()
            return

        try:
            # Get daily sentiment data for last 30 days
            days = 30
            end_date = date.today()
            start_date = end_date - timedelta(days=days)

            # Get news articles (uses smart incremental caching)
            articles = self._data_manager.get_news(
                self._ticker,
                limit=1000,
                from_date=start_date,
                to_date=end_date,
            )

            if not articles:
                self._show_no_data()
                return

            # Get daily sentiment (aggregated from articles)
            daily_sentiments = self._data_manager.get_daily_sentiment(
                self._ticker, days=days
            )

            if not daily_sentiments:
                self._show_no_data()
                return

            # Calculate current sentiment
            from investment_tool.analysis.sentiment import SentimentAggregator
            aggregator = SentimentAggregator()
            current_score = aggregator.get_current_sentiment_score(self._ticker, articles)
            label, color = aggregator.get_sentiment_label(current_score)

            # Update gauge
            self.gauge.set_value(current_score, label, color)

            # Update trend chart
            self._update_trend_chart(daily_sentiments)

            # Update summary
            self._update_summary(articles, daily_sentiments)

        except Exception as e:
            from loguru import logger
            logger.error(f"Failed to update sentiment display: {e}")
            self._show_no_data()

    def _show_no_data(self) -> None:
        """Show no data state."""
        self.gauge.set_value(0.0, "No Data", "#6B7280")
        self.trend_chart.clear()
        self.trend_chart.addItem(self.zero_line)
        self.summary_label.setText("No news articles available")

    def _update_trend_chart(self, daily_sentiments: List[DailySentiment]) -> None:
        """Update the 7-day trend chart."""
        self.trend_chart.clear()
        self.trend_chart.addItem(self.zero_line)

        if not daily_sentiments:
            return

        # Sort by date
        sorted_data = sorted(daily_sentiments, key=lambda x: x.date)

        # Prepare data
        x = list(range(len(sorted_data)))
        y = [ds.avg_polarity for ds in sorted_data]

        # Create color for each point based on value
        colors = []
        for polarity in y:
            if polarity >= 0.3:
                colors.append("#22C55E")  # Green
            elif polarity <= -0.3:
                colors.append("#EF4444")  # Red
            else:
                colors.append("#6B7280")  # Gray

        # Set date labels on x-axis (show every 7th date to avoid crowding)
        date_ticks = []
        for i, ds in enumerate(sorted_data):
            if i % 7 == 0 or i == len(sorted_data) - 1:  # Every 7 days + last day
                date_ticks.append((i, ds.date.strftime("%m/%d")))
        self.trend_chart.getAxis("bottom").setTicks([date_ticks])

        # Plot line
        pen = pg.mkPen("#60A5FA", width=2)
        self.trend_chart.plot(x, y, pen=pen)

        # Plot points with colors
        for i, (xi, yi, color) in enumerate(zip(x, y, colors)):
            scatter = pg.ScatterPlotItem(
                [xi], [yi],
                size=8,
                pen=pg.mkPen(color, width=1),
                brush=pg.mkBrush(color)
            )
            self.trend_chart.addItem(scatter)

        # Set y range
        y_min = min(y) - 0.1
        y_max = max(y) + 0.1
        self.trend_chart.setYRange(max(-1.0, y_min), min(1.0, y_max))

    def _update_summary(
        self,
        articles: list,
        daily_sentiments: List[DailySentiment]
    ) -> None:
        """Update the summary label."""
        from investment_tool.analysis.sentiment import SentimentAggregator
        aggregator = SentimentAggregator()

        total = len(articles)
        positive = 0
        neutral = 0
        negative = 0

        for article in articles:
            polarity = None
            if article.ensemble_polarity is not None:
                polarity = article.ensemble_polarity
            elif article.eodhd_sentiment is not None:
                polarity = article.eodhd_sentiment.polarity

            if polarity is not None:
                if polarity > aggregator.POSITIVE_THRESHOLD:
                    positive += 1
                elif polarity < aggregator.NEGATIVE_THRESHOLD:
                    negative += 1
                else:
                    neutral += 1

        self.summary_label.setText(
            f"{total} articles ({positive} positive, {neutral} neutral, {negative} negative)"
        )

    def clear(self) -> None:
        """Clear the display."""
        self._ticker = None
        self._exchange = None
        self.group_box.setTitle("Sentiment")
        self._show_no_data()

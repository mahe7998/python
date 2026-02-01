"""Sentiment aggregation for news articles."""

from collections import defaultdict
from datetime import date, timedelta
from typing import List, Optional

from investment_tool.data.models import NewsArticle, DailySentiment


class SentimentAggregator:
    """Aggregates sentiment data from news articles."""

    # Thresholds for classifying sentiment
    POSITIVE_THRESHOLD = 0.1
    NEGATIVE_THRESHOLD = -0.1

    def aggregate_daily_sentiment(
        self,
        ticker: str,
        articles: List[NewsArticle],
    ) -> List[DailySentiment]:
        """
        Aggregate news articles into daily sentiment summaries.

        Groups articles by date and calculates:
        - news_count: number of articles
        - avg_polarity: average sentiment polarity
        - positive_ratio: fraction of articles with polarity > 0.1
        - negative_ratio: fraction of articles with polarity < -0.1

        Args:
            ticker: The stock ticker
            articles: List of news articles to aggregate

        Returns:
            List of DailySentiment objects, one per day with articles
        """
        if not articles:
            return []

        # Group articles by date
        by_date: dict[date, List[NewsArticle]] = defaultdict(list)
        for article in articles:
            article_date = article.published_at.date()
            by_date[article_date].append(article)

        # Calculate daily sentiment
        daily_sentiments = []
        for day, day_articles in sorted(by_date.items()):
            sentiment = self._calculate_daily_sentiment(ticker, day, day_articles)
            daily_sentiments.append(sentiment)

        return daily_sentiments

    def _calculate_daily_sentiment(
        self,
        ticker: str,
        day: date,
        articles: List[NewsArticle],
    ) -> DailySentiment:
        """Calculate sentiment metrics for a single day."""
        news_count = len(articles)

        if news_count == 0:
            return DailySentiment(
                ticker=ticker,
                date=day,
                news_count=0,
                avg_polarity=0.0,
                positive_ratio=0.0,
                negative_ratio=0.0,
            )

        # Get polarity values (use EODHD sentiment if available)
        polarities = []
        for article in articles:
            polarity = self._get_polarity(article)
            if polarity is not None:
                polarities.append(polarity)

        if not polarities:
            return DailySentiment(
                ticker=ticker,
                date=day,
                news_count=news_count,
                avg_polarity=0.0,
                positive_ratio=0.0,
                negative_ratio=0.0,
            )

        # Calculate metrics
        avg_polarity = sum(polarities) / len(polarities)
        positive_count = sum(1 for p in polarities if p > self.POSITIVE_THRESHOLD)
        negative_count = sum(1 for p in polarities if p < self.NEGATIVE_THRESHOLD)

        return DailySentiment(
            ticker=ticker,
            date=day,
            news_count=news_count,
            avg_polarity=avg_polarity,
            positive_ratio=positive_count / len(polarities),
            negative_ratio=negative_count / len(polarities),
        )

    def _get_polarity(self, article: NewsArticle) -> Optional[float]:
        """
        Get the best available polarity for an article.

        Prioritizes ensemble_polarity, then EODHD sentiment.
        """
        if article.ensemble_polarity is not None:
            return article.ensemble_polarity
        if article.eodhd_sentiment is not None:
            return article.eodhd_sentiment.polarity
        return None

    def get_sentiment_trend(
        self,
        ticker: str,
        articles: List[NewsArticle],
        days: int = 7,
    ) -> List[DailySentiment]:
        """
        Get sentiment trend for the last N days.

        Args:
            ticker: The stock ticker
            articles: List of news articles
            days: Number of days to include in the trend

        Returns:
            List of DailySentiment objects for the last N days
        """
        daily_sentiments = self.aggregate_daily_sentiment(ticker, articles)

        if not daily_sentiments:
            return []

        # Filter to the last N days
        cutoff_date = date.today() - timedelta(days=days)
        trend = [ds for ds in daily_sentiments if ds.date >= cutoff_date]

        return trend

    def get_current_sentiment_score(
        self,
        ticker: str,
        articles: List[NewsArticle],
    ) -> float:
        """
        Calculate a current sentiment score from recent articles.

        Uses weighted average giving more weight to recent articles.

        Args:
            ticker: The stock ticker
            articles: List of news articles (should be recent)

        Returns:
            Sentiment score between -1.0 and 1.0
        """
        if not articles:
            return 0.0

        # Sort by date (most recent first)
        sorted_articles = sorted(
            articles,
            key=lambda a: a.published_at,
            reverse=True
        )

        # Calculate weighted average with exponential decay
        weighted_sum = 0.0
        weight_sum = 0.0
        today = date.today()

        for article in sorted_articles:
            polarity = self._get_polarity(article)
            if polarity is None:
                continue

            # Calculate weight based on age (exponential decay)
            days_old = (today - article.published_at.date()).days
            weight = 0.9 ** days_old  # 10% decay per day

            weighted_sum += polarity * weight
            weight_sum += weight

        if weight_sum == 0:
            return 0.0

        return weighted_sum / weight_sum

    def get_sentiment_label(self, score: float) -> tuple[str, str]:
        """
        Get a sentiment label and color for a score.

        Args:
            score: Sentiment score between -1.0 and 1.0

        Returns:
            Tuple of (label, color_hex)
        """
        if score >= 0.7:
            return "Very Bullish", "#166534"  # dark green
        elif score >= 0.3:
            return "Bullish", "#22C55E"  # light green
        elif score >= -0.3:
            return "Neutral", "#6B7280"  # gray
        elif score >= -0.7:
            return "Bearish", "#F87171"  # light red
        else:
            return "Very Bearish", "#991B1B"  # dark red

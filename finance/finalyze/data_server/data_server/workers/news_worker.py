"""Background worker for news updates."""

import logging
from datetime import datetime

from data_server.db.database import async_session_factory
from data_server.db import cache
from data_server.api.tracking import get_tracked_tickers_for_news, update_news_timestamp
from data_server.services.eodhd_client import get_eodhd_client
from data_server.ws.manager import manager

logger = logging.getLogger(__name__)


async def update_news():
    """Update news for all tracked stocks."""
    async with async_session_factory() as session:
        # Get tracked tickers for news
        tickers = await get_tracked_tickers_for_news(session)

        if not tickers:
            logger.debug("No tracked stocks for news updates")
            return

        logger.debug(f"Updating news for {len(tickers)} stocks")

        client = await get_eodhd_client()

        for symbol in tickers:
            try:
                # Fetch recent news
                news_data = await client.get_news(symbol=symbol, limit=20)

                if news_data:
                    ticker = symbol.split(".")[0]

                    for article in news_data:
                        # Extract ticker symbols from article
                        article_tickers = [
                            t.split(".")[0] for t in article.get("symbols", [])
                        ]

                        # Prepare data for storage
                        sentiment = article.get("sentiment") or {}
                        news_meta = {
                            "id": None,  # Will be generated
                            "source": article.get("source"),
                            "published_at": article.get("date"),
                            "polarity": sentiment.get("polarity"),
                            "positive": sentiment.get("pos"),
                            "negative": sentiment.get("neg"),
                            "neutral": sentiment.get("neu"),
                        }
                        content_data = {
                            "url": article.get("link"),
                            "title": article.get("title"),
                            "summary": article.get("content"),
                            "full_content": article.get("content"),
                        }

                        # Store in database
                        news_id = await cache.store_news_article(
                            session, news_meta, content_data, article_tickers
                        )
                        content_id = cache.generate_content_id(article.get("link", ""))

                        # Broadcast to subscribers
                        news_update = {
                            "id": news_id,
                            "content_id": content_id,
                            "title": article.get("title"),
                            "source": article.get("source"),
                            "published_at": article.get("date"),
                            "sentiment": sentiment.get("polarity"),
                        }
                        await manager.broadcast_news_update(ticker, news_update)

                    # Update timestamp
                    await update_news_timestamp(session, ticker)
                    logger.debug(f"Updated {len(news_data)} news items for {ticker}")

            except Exception as e:
                logger.error(f"Error updating news for {symbol}: {e}")

        await session.commit()


async def fetch_news_for_ticker(symbol: str, limit: int = 50) -> list[dict]:
    """Fetch and store news for a specific ticker."""
    async with async_session_factory() as session:
        client = await get_eodhd_client()

        try:
            news_data = await client.get_news(symbol=symbol, limit=limit)

            if not news_data:
                return []

            ticker = symbol.split(".")[0]
            stored_news = []

            for article in news_data:
                article_tickers = [
                    t.split(".")[0] for t in article.get("symbols", [])
                ]

                sentiment = article.get("sentiment") or {}
                news_meta = {
                    "id": None,
                    "source": article.get("source"),
                    "published_at": article.get("date"),
                    "polarity": sentiment.get("polarity"),
                    "positive": sentiment.get("pos"),
                    "negative": sentiment.get("neg"),
                    "neutral": sentiment.get("neu"),
                }
                content_data = {
                    "url": article.get("link"),
                    "title": article.get("title"),
                    "summary": article.get("content"),
                    "full_content": article.get("content"),
                }

                news_id = await cache.store_news_article(
                    session, news_meta, content_data, article_tickers
                )

                stored_news.append(
                    {
                        "id": news_id,
                        "content_id": cache.generate_content_id(article.get("link", "")),
                        "title": article.get("title"),
                        "source": article.get("source"),
                        "published_at": article.get("date"),
                        "polarity": sentiment.get("polarity"),
                    }
                )

            await session.commit()
            return stored_news

        except Exception as e:
            logger.error(f"Error fetching news for {symbol}: {e}")
            return []

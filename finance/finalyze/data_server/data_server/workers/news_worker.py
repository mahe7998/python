"""Background worker for news updates."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from data_server.db.database import async_session_factory
from data_server.db import cache
from data_server.api.tracking import get_tracked_tickers_for_news, update_news_timestamp
from data_server.services.eodhd_client import get_eodhd_client
from data_server.ws.manager import manager

logger = logging.getLogger(__name__)


async def fetch_news_for_single_ticker(symbol: str, from_date: str, to_date: str) -> int:
    """Fetch and store news for a single ticker asynchronously.

    Returns the number of articles stored.
    """
    async with async_session_factory() as session:
        client = await get_eodhd_client()
        ticker = symbol.split(".")[0]

        try:
            # Fetch 100 news articles from EODHD
            news_data = await client.get_news(
                symbol=symbol,
                from_date=from_date,
                to_date=to_date,
                limit=100,
                offset=0
            )

            if not news_data:
                logger.debug(f"No news found for {ticker} from {from_date} to {to_date}")
                return 0

            stored_count = 0
            for article in news_data:
                article_tickers = [
                    t.split(".")[0] for t in article.get("symbols", [])
                ]

                sentiment = article.get("sentiment") or {}

                # Extract source
                source = article.get("source") or article.get("site") or None
                if not source and article.get("link"):
                    from urllib.parse import urlparse
                    try:
                        parsed = urlparse(article.get("link", ""))
                        source = parsed.netloc.replace("www.", "")
                    except Exception:
                        pass

                news_meta = {
                    "id": None,
                    "source": source,
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
                content_id = cache.generate_content_id(article.get("link", ""))
                stored_count += 1

                # Broadcast to WebSocket subscribers
                news_update = {
                    "id": news_id,
                    "content_id": content_id,
                    "title": article.get("title"),
                    "source": source,
                    "published_at": article.get("date"),
                    "sentiment": sentiment.get("polarity"),
                }
                await manager.broadcast_news_update(ticker, news_update)

            # Update timestamp
            await update_news_timestamp(session, ticker)
            await session.commit()

            logger.info(f"Stored {stored_count} news articles for {ticker} ({from_date} to {to_date})")
            return stored_count

        except Exception as e:
            logger.error(f"Error fetching news for {symbol}: {e}")
            return 0


async def update_news():
    """Update news for all tracked stocks.

    For each tracked stock:
    1. Check the oldest news date in the database
    2. Fetch 100 news from today (UTC) back to that date (inclusive)
    3. Process asynchronously (don't block on each ticker)
    """
    async with async_session_factory() as session:
        # Get tracked tickers for news
        tickers = await get_tracked_tickers_for_news(session)

        if not tickers:
            logger.debug("No tracked stocks for news updates")
            return

        logger.info(f"Starting news update for {len(tickers)} stocks")

    # Get today's date in UTC
    today_utc = datetime.now(timezone.utc).date()
    to_date = today_utc.strftime("%Y-%m-%d")

    # Default: fetch last 30 days if no news exists
    default_from_date = (today_utc - timedelta(days=30)).strftime("%Y-%m-%d")

    # Create tasks for each ticker
    tasks = []
    for symbol in tickers:
        ticker = symbol.split(".")[0]

        # Get newest (most recent) news date for this ticker
        async with async_session_factory() as session:
            newest_date = await cache.get_newest_news_date_for_ticker(session, ticker)

        if newest_date:
            # Fetch from newest date in DB to today (to get only new articles)
            from_date = newest_date.date().strftime("%Y-%m-%d")
        else:
            # No existing news, fetch last 30 days
            from_date = default_from_date

        # Create async task (fire and forget pattern with tracking)
        task = asyncio.create_task(
            fetch_news_for_single_ticker(symbol, from_date, to_date),
            name=f"news_{ticker}"
        )
        tasks.append(task)

        # Small delay between starting tasks to avoid overwhelming EODHD
        await asyncio.sleep(0.1)

    # Wait for all tasks to complete (with timeout)
    if tasks:
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=300  # 5 minute timeout for all news fetches
            )

            total_articles = sum(r for r in results if isinstance(r, int))
            errors = sum(1 for r in results if isinstance(r, Exception))

            logger.info(f"News update complete: {total_articles} articles from {len(tickers)} stocks, {errors} errors")

        except asyncio.TimeoutError:
            logger.warning("News update timed out after 5 minutes")


async def fetch_news_for_ticker(symbol: str, limit: int = 50) -> list[dict]:
    """Fetch and store news for a specific ticker (on-demand).

    This is used for manual refresh requests.
    """
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

                # Extract source
                source = article.get("source") or article.get("site") or None
                if not source and article.get("link"):
                    from urllib.parse import urlparse
                    try:
                        parsed = urlparse(article.get("link", ""))
                        source = parsed.netloc.replace("www.", "")
                    except Exception:
                        pass

                news_meta = {
                    "id": None,
                    "source": source,
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
                        "source": source,
                        "published_at": article.get("date"),
                        "polarity": sentiment.get("polarity"),
                    }
                )

            await session.commit()
            return stored_news

        except Exception as e:
            logger.error(f"Error fetching news for {symbol}: {e}")
            return []

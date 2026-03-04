"""PostgreSQL database connection and session management."""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from data_server.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

# Create async session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Initialize database and create tables."""
    from data_server.db import models  # noqa: F401
    from sqlalchemy import text

    logger.info("Initializing database...")
    async with engine.begin() as conn:
        # Migrate forex_rates: old schema had (currency) PK, new has (currency, date)
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'forex_rates' AND column_name = 'date'"
        ))
        if result.rowcount == 0:
            # Old table exists without date column — drop and let create_all recreate
            await conn.execute(text("DROP TABLE IF EXISTS forex_rates"))
            logger.info("Migrated forex_rates table to (currency, date) schema")

        # Migrate tracked_stocks: old schema had (ticker) PK, new has (ticker, exchange)
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.key_column_usage "
            "WHERE table_name = 'tracked_stocks' AND constraint_name LIKE '%pkey%'"
        ))
        pk_cols = [row[0] for row in result.fetchall()]
        if pk_cols and 'exchange' not in pk_cols:
            # Backup existing data, drop table, let create_all rebuild with composite PK
            await conn.execute(text(
                "CREATE TABLE _tracked_stocks_backup AS SELECT * FROM tracked_stocks"
            ))
            await conn.execute(text("DROP TABLE tracked_stocks"))
            logger.info("Migrating tracked_stocks to (ticker, exchange) composite PK")

        await conn.run_sync(Base.metadata.create_all)

        # Restore tracked_stocks data from backup if migration happened
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = '_tracked_stocks_backup')"
        ))
        if result.scalar():
            await conn.execute(text("""
                INSERT INTO tracked_stocks (ticker, exchange, track_prices, track_news,
                                            added_at, last_price_update, last_news_update)
                SELECT ticker, COALESCE(exchange, 'US'), track_prices, track_news,
                       added_at, last_price_update, last_news_update
                FROM _tracked_stocks_backup
                ON CONFLICT (ticker, exchange) DO NOTHING
            """))
            await conn.execute(text("DROP TABLE _tracked_stocks_backup"))
            logger.info("Restored tracked_stocks data with composite PK")
        # Migrations for columns added after initial create_all
        await conn.execute(text(
            "ALTER TABLE quarterly_financials ADD COLUMN IF NOT EXISTS data_source VARCHAR(20) DEFAULT 'eodhd'"
        ))
        await conn.execute(text(
            "ALTER TABLE company_highlights ADD COLUMN IF NOT EXISTS asset_type VARCHAR(20)"
        ))
        await conn.execute(text(
            "ALTER TABLE company_highlights ADD COLUMN IF NOT EXISTS etf_data TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE company_highlights ADD COLUMN IF NOT EXISTS eps_estimate_next_year NUMERIC(14, 4)"
        ))
        await conn.execute(text(
            "ALTER TABLE company_highlights ADD COLUMN IF NOT EXISTS most_recent_quarter VARCHAR(20)"
        ))
        await conn.execute(text(
            "ALTER TABLE company_highlights ADD COLUMN IF NOT EXISTS fiscal_year_end VARCHAR(20)"
        ))
        await conn.execute(text(
            "ALTER TABLE live_prices ADD COLUMN IF NOT EXISTS data_source VARCHAR(30)"
        ))
        await conn.execute(text(
            "ALTER TABLE company_highlights ADD COLUMN IF NOT EXISTS earnings_currency VARCHAR(10)"
        ))
    logger.info("Database initialized")


async def close_db():
    """Close database connections."""
    logger.info("Closing database connections...")
    await engine.dispose()
    logger.info("Database connections closed")

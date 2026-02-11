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
        await conn.run_sync(Base.metadata.create_all)
        # Migrations for columns added after initial create_all
        await conn.execute(text(
            "ALTER TABLE quarterly_financials ADD COLUMN IF NOT EXISTS data_source VARCHAR(20) DEFAULT 'eodhd'"
        ))
    logger.info("Database initialized")


async def close_db():
    """Close database connections."""
    logger.info("Closing database connections...")
    await engine.dispose()
    logger.info("Database connections closed")

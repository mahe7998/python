"""Cache operations for reading and storing data."""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from data_server.config import get_settings
from data_server.db.models import (
    DailyPrice,
    IntradayPrice,
    Content,
    News,
    NewsTicker,
    Company,
    QuarterlyFinancial,
    CompanyHighlight,
    SharesHistory,
    CacheMetadata,
)

logger = logging.getLogger(__name__)
settings = get_settings()


def generate_content_id(url: str) -> str:
    """Generate a unique content ID from URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:64]


async def is_cache_valid(
    session: AsyncSession, cache_key: str, max_age_seconds: int
) -> bool:
    """Check if cache entry is still valid.

    Returns True if:
    - expires_at hasn't passed yet, OR
    - last_fetched is within max_age_seconds (allows dynamic TTL override)
    """
    result = await session.execute(
        select(CacheMetadata).where(CacheMetadata.cache_key == cache_key)
    )
    metadata = result.scalar_one_or_none()

    if not metadata:
        return False

    now = datetime.utcnow()

    # Check if within the requested max_age (allows longer TTL for historical data)
    if metadata.last_fetched:
        age = (now - metadata.last_fetched).total_seconds()
        if age < max_age_seconds:
            return True

    # Fall back to stored expires_at
    if metadata.expires_at and now < metadata.expires_at:
        return True

    return False


async def update_cache_metadata(
    session: AsyncSession,
    cache_key: str,
    data_type: str,
    ticker: Optional[str] = None,
    max_age_seconds: int = 3600,
    record_count: int = 0,
):
    """Update or insert cache metadata."""
    now = datetime.utcnow()
    stmt = insert(CacheMetadata).values(
        cache_key=cache_key,
        data_type=data_type,
        ticker=ticker,
        last_fetched=now,
        expires_at=now + timedelta(seconds=max_age_seconds),
        record_count=record_count,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["cache_key"],
        set_={
            "last_fetched": now,
            "expires_at": now + timedelta(seconds=max_age_seconds),
            "record_count": record_count,
        },
    )
    await session.execute(stmt)


# Daily Prices
async def get_daily_prices(
    session: AsyncSession,
    ticker: str,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> list[dict]:
    """Get cached daily prices for a ticker."""
    query = select(DailyPrice).where(DailyPrice.ticker == ticker)

    if from_date:
        query = query.where(DailyPrice.date >= from_date.date())
    if to_date:
        query = query.where(DailyPrice.date <= to_date.date())

    query = query.order_by(DailyPrice.date.asc())
    result = await session.execute(query)
    prices = result.scalars().all()

    return [
        {
            "date": p.date.isoformat(),
            "open": float(p.open) if p.open else None,
            "high": float(p.high) if p.high else None,
            "low": float(p.low) if p.low else None,
            "close": float(p.close) if p.close else None,
            "adjusted_close": float(p.adjusted_close) if p.adjusted_close else None,
            "volume": p.volume,
        }
        for p in prices
    ]


def parse_date_str(date_str: str) -> datetime:
    """Parse date string to datetime object."""
    if isinstance(date_str, datetime):
        return date_str
    return datetime.strptime(date_str, "%Y-%m-%d")


async def store_daily_prices(
    session: AsyncSession, ticker: str, prices: list[dict]
) -> int:
    """Store daily prices in cache."""
    if not prices:
        return 0

    for price in prices:
        date_val = price.get("date")
        if isinstance(date_val, str):
            date_val = parse_date_str(date_val)

        stmt = insert(DailyPrice).values(
            ticker=ticker,
            date=date_val,
            open=price.get("open"),
            high=price.get("high"),
            low=price.get("low"),
            close=price.get("close"),
            adjusted_close=price.get("adjusted_close"),
            volume=price.get("volume"),
            fetched_at=datetime.utcnow(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "date"],
            set_={
                "open": price.get("open"),
                "high": price.get("high"),
                "low": price.get("low"),
                "close": price.get("close"),
                "adjusted_close": price.get("adjusted_close"),
                "volume": price.get("volume"),
                "fetched_at": datetime.utcnow(),
            },
        )
        await session.execute(stmt)

    return len(prices)


# Intraday Prices
async def get_intraday_prices(
    session: AsyncSession,
    ticker: str,
    from_timestamp: Optional[datetime] = None,
    to_timestamp: Optional[datetime] = None,
) -> list[dict]:
    """Get cached intraday prices for a ticker."""
    query = select(IntradayPrice).where(IntradayPrice.ticker == ticker)

    if from_timestamp:
        query = query.where(IntradayPrice.timestamp >= from_timestamp)
    if to_timestamp:
        query = query.where(IntradayPrice.timestamp <= to_timestamp)

    query = query.order_by(IntradayPrice.timestamp.asc())
    result = await session.execute(query)
    prices = result.scalars().all()

    return [
        {
            "timestamp": p.timestamp.isoformat(),
            "open": float(p.open) if p.open else None,
            "high": float(p.high) if p.high else None,
            "low": float(p.low) if p.low else None,
            "close": float(p.close) if p.close else None,
            "volume": p.volume,
        }
        for p in prices
    ]


async def get_intraday_source(
    session: AsyncSession,
    ticker: str,
    from_timestamp: Optional[datetime] = None,
    to_timestamp: Optional[datetime] = None,
) -> Optional[str]:
    """Get the source of intraday data for a ticker (live or eodhd)."""
    query = select(IntradayPrice.source).where(IntradayPrice.ticker == ticker)

    if from_timestamp:
        query = query.where(IntradayPrice.timestamp >= from_timestamp)
    if to_timestamp:
        query = query.where(IntradayPrice.timestamp <= to_timestamp)

    query = query.limit(1)
    result = await session.execute(query)
    source = result.scalar_one_or_none()
    return source


def parse_timestamp(ts) -> datetime:
    """Parse timestamp (Unix int or ISO string) to datetime object."""
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts)
    if isinstance(ts, str):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return ts


async def store_intraday_prices(
    session: AsyncSession, ticker: str, prices: list[dict], source: str = "live"
) -> int:
    """Store intraday prices in cache.

    Args:
        session: Database session
        ticker: Stock ticker (e.g., LULU.US)
        prices: List of price dicts with timestamp, open, high, low, close, volume
        source: Data source - 'live' (price worker) or 'eodhd' (EODHD API)
    """
    if not prices:
        return 0

    for price in prices:
        ts_val = price.get("timestamp")
        if ts_val is not None:
            ts_val = parse_timestamp(ts_val)

        stmt = insert(IntradayPrice).values(
            ticker=ticker,
            timestamp=ts_val,
            open=price.get("open"),
            high=price.get("high"),
            low=price.get("low"),
            close=price.get("close"),
            volume=price.get("volume"),
            source=source,
            fetched_at=datetime.utcnow(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "timestamp"],
            set_={
                "open": price.get("open"),
                "high": price.get("high"),
                "low": price.get("low"),
                "close": price.get("close"),
                "volume": price.get("volume"),
                "source": source,
                "fetched_at": datetime.utcnow(),
            },
        )
        await session.execute(stmt)

    return len(prices)


# News
async def get_news_for_ticker(
    session: AsyncSession,
    ticker: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Get cached news for a ticker with content (EODHD-compatible format).

    Optimized to only select needed columns (excludes full_content for speed).
    """
    # Select only needed columns to avoid loading large full_content field
    query = (
        select(
            News.published_at,
            News.source,
            News.polarity,
            News.positive,
            News.negative,
            News.neutral,
            Content.title,
            Content.summary,
            Content.url,
        )
        .select_from(NewsTicker)
        .join(News, NewsTicker.news_id == News.id)
        .outerjoin(Content, News.content_id == Content.id)
        .where(NewsTicker.ticker == ticker)
        .order_by(News.published_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(query)
    rows = result.all()

    news_list = []
    for row in rows:
        # Return EODHD-compatible format for client compatibility
        news_list.append(
            {
                "title": row.title or "",
                "content": row.summary or "",
                "link": row.url or "",
                "date": row.published_at.isoformat() if row.published_at else None,
                "source": row.source,
                "sentiment": {
                    "polarity": float(row.polarity) if row.polarity else 0,
                    "pos": float(row.positive) if row.positive else 0,
                    "neg": float(row.negative) if row.negative else 0,
                    "neu": float(row.neutral) if row.neutral else 0,
                },
            }
        )

    return news_list


async def get_newest_news_date_for_ticker(
    session: AsyncSession, ticker: str
) -> Optional[datetime]:
    """Get the newest (most recent) news date for a ticker in the database."""
    query = (
        select(func.max(News.published_at))
        .select_from(NewsTicker)
        .join(News, NewsTicker.news_id == News.id)
        .where(NewsTicker.ticker == ticker)
    )
    result = await session.execute(query)
    newest_date = result.scalar_one_or_none()
    return newest_date


async def store_news_article(
    session: AsyncSession,
    news_data: dict,
    content_data: dict,
    tickers: list[str],
) -> str:
    """Store a news article with its content and ticker associations."""
    # Generate content ID from URL
    content_id = generate_content_id(content_data.get("url", ""))

    # Insert or update content
    content_stmt = insert(Content).values(
        id=content_id,
        content_type="news",
        url=content_data.get("url"),
        title=content_data.get("title"),
        summary=content_data.get("summary"),
        full_content=content_data.get("full_content"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    content_stmt = content_stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "title": content_data.get("title"),
            "summary": content_data.get("summary"),
            "full_content": content_data.get("full_content"),
            "updated_at": datetime.utcnow(),
        },
    )
    await session.execute(content_stmt)

    # Generate news ID
    news_id = news_data.get("id") or generate_content_id(
        f"{content_data.get('url', '')}_{news_data.get('published_at', '')}"
    )

    # Parse published_at and ensure it's timezone-naive
    published_at = news_data.get("published_at")
    if published_at:
        if isinstance(published_at, str):
            try:
                published_at = datetime.fromisoformat(published_at.replace(" ", "T").replace("Z", "+00:00"))
            except ValueError:
                published_at = None
        # Remove timezone info if present (convert to naive UTC)
        if published_at and hasattr(published_at, 'tzinfo') and published_at.tzinfo is not None:
            published_at = published_at.replace(tzinfo=None)

    # Insert or update news metadata
    news_stmt = insert(News).values(
        id=news_id,
        content_id=content_id,
        source=news_data.get("source"),
        published_at=published_at,
        polarity=news_data.get("polarity"),
        positive=news_data.get("positive"),
        negative=news_data.get("negative"),
        neutral=news_data.get("neutral"),
        fetched_at=datetime.utcnow(),
    )
    news_stmt = news_stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "polarity": news_data.get("polarity"),
            "positive": news_data.get("positive"),
            "negative": news_data.get("negative"),
            "neutral": news_data.get("neutral"),
            "fetched_at": datetime.utcnow(),
        },
    )
    await session.execute(news_stmt)

    # Delete existing ticker associations and insert new ones
    await session.execute(delete(NewsTicker).where(NewsTicker.news_id == news_id))
    for ticker in tickers:
        ticker_stmt = insert(NewsTicker).values(
            news_id=news_id,
            ticker=ticker,
            relevance=1.0,
        )
        ticker_stmt = ticker_stmt.on_conflict_do_nothing()
        await session.execute(ticker_stmt)

    return news_id


# Content
async def get_content(session: AsyncSession, content_id: str) -> Optional[dict]:
    """Get full content by ID."""
    result = await session.execute(
        select(Content).where(Content.id == content_id)
    )
    content = result.scalar_one_or_none()

    if not content:
        return None

    return {
        "id": content.id,
        "content_type": content.content_type,
        "url": content.url,
        "title": content.title,
        "summary": content.summary,
        "full_content": content.full_content,
        "created_at": content.created_at.isoformat() if content.created_at else None,
        "updated_at": content.updated_at.isoformat() if content.updated_at else None,
    }


async def get_content_batch(
    session: AsyncSession, content_ids: list[str]
) -> list[dict]:
    """Get multiple content items by IDs."""
    result = await session.execute(
        select(Content).where(Content.id.in_(content_ids))
    )
    contents = result.scalars().all()

    return [
        {
            "id": c.id,
            "content_type": c.content_type,
            "url": c.url,
            "title": c.title,
            "summary": c.summary,
            "full_content": c.full_content,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in contents
    ]


# Company
async def get_company(session: AsyncSession, ticker: str) -> Optional[dict]:
    """Get cached company information."""
    result = await session.execute(
        select(Company).where(Company.ticker == ticker)
    )
    company = result.scalar_one_or_none()

    if not company:
        return None

    return {
        "ticker": company.ticker,
        "name": company.name,
        "exchange": company.exchange,
        "sector": company.sector,
        "industry": company.industry,
        "market_cap": company.market_cap,
        "shares_outstanding": company.shares_outstanding,
        "pe_ratio": float(company.pe_ratio) if company.pe_ratio else None,
        "eps": float(company.eps) if company.eps else None,
        "fetched_at": company.fetched_at.isoformat() if company.fetched_at else None,
    }


async def store_company(session: AsyncSession, company_data: dict) -> None:
    """Store company information in cache."""
    stmt = insert(Company).values(
        ticker=company_data.get("ticker"),
        name=company_data.get("name"),
        exchange=company_data.get("exchange"),
        sector=company_data.get("sector"),
        industry=company_data.get("industry"),
        market_cap=company_data.get("market_cap"),
        shares_outstanding=company_data.get("shares_outstanding"),
        pe_ratio=company_data.get("pe_ratio"),
        eps=company_data.get("eps"),
        fetched_at=datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={
            "name": company_data.get("name"),
            "exchange": company_data.get("exchange"),
            "sector": company_data.get("sector"),
            "industry": company_data.get("industry"),
            "market_cap": company_data.get("market_cap"),
            "shares_outstanding": company_data.get("shares_outstanding"),
            "pe_ratio": company_data.get("pe_ratio"),
            "eps": company_data.get("eps"),
            "fetched_at": datetime.utcnow(),
        },
    )
    await session.execute(stmt)


# Quarterly Financials
def _safe_num(value) -> Optional[float]:
    """Safely convert a value to float, returning None for invalid values."""
    if value is None or value == "" or value == "None":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _date_to_quarter(report_date) -> tuple:
    """Convert report date to (quarter_str, year)."""
    month = report_date.month
    if month <= 3:
        return "Q1", report_date.year
    elif month <= 6:
        return "Q2", report_date.year
    elif month <= 9:
        return "Q3", report_date.year
    else:
        return "Q4", report_date.year


async def store_quarterly_financials(
    session: AsyncSession, ticker: str, eodhd_data: dict,
    data_source: str = "eodhd",
) -> int:
    """Parse EODHD fundamentals and store quarterly financial rows.

    Reads from Financials.Income_Statement.quarterly,
    Financials.Balance_Sheet.quarterly, and Financials.Cash_Flow.quarterly.
    Skips rows where data_source='yfinance' (user-overridden).
    """
    financials = eodhd_data.get("Financials", {})
    income_q = financials.get("Income_Statement", {}).get("quarterly", {})
    balance_q = financials.get("Balance_Sheet", {}).get("quarterly", {})
    cashflow_q = financials.get("Cash_Flow", {}).get("quarterly", {})

    all_dates = set(income_q.keys()) | set(balance_q.keys()) | set(cashflow_q.keys())

    # Find which report_dates already have data_source='yfinance' — skip those
    if all_dates:
        parsed_dates = []
        for dk in all_dates:
            try:
                parsed_dates.append(datetime.strptime(dk, "%Y-%m-%d").date())
            except ValueError:
                pass
        if parsed_dates:
            result = await session.execute(
                select(QuarterlyFinancial.report_date)
                .where(
                    QuarterlyFinancial.ticker == ticker,
                    QuarterlyFinancial.data_source == "yfinance",
                    QuarterlyFinancial.report_date.in_(parsed_dates),
                )
            )
            yf_dates = {r[0] for r in result.all()}
        else:
            yf_dates = set()
    else:
        yf_dates = set()

    count = 0
    for date_key in all_dates:
        try:
            report_date = datetime.strptime(date_key, "%Y-%m-%d").date()
        except ValueError:
            continue

        if report_date in yf_dates:
            continue  # Don't overwrite user-overridden yfinance data

        income = income_q.get(date_key, {})
        balance = balance_q.get(date_key, {})
        cashflow = cashflow_q.get(date_key, {})
        quarter, year = _date_to_quarter(report_date)

        values = {
            "ticker": ticker,
            "report_date": report_date,
            "quarter": quarter,
            "year": year,
            "total_revenue": _safe_num(income.get("totalRevenue")),
            "gross_profit": _safe_num(income.get("grossProfit")),
            "operating_income": _safe_num(income.get("operatingIncome")),
            "net_income": _safe_num(income.get("netIncome")),
            "ebit": _safe_num(income.get("ebit")),
            "cost_of_revenue": _safe_num(income.get("costOfRevenue")),
            "research_development": _safe_num(income.get("researchDevelopment")),
            "selling_general_admin": _safe_num(income.get("sellingGeneralAdministrative")),
            "interest_expense": _safe_num(income.get("interestExpense")),
            "tax_provision": _safe_num(income.get("taxProvision") or income.get("incomeTaxExpense")),
            "cash": _safe_num(balance.get("cash")),
            "short_term_investments": _safe_num(balance.get("shortTermInvestments")),
            "total_assets": _safe_num(balance.get("totalAssets")),
            "total_current_assets": _safe_num(balance.get("totalCurrentAssets")),
            "total_liabilities": _safe_num(balance.get("totalLiab")),
            "total_current_liabilities": _safe_num(balance.get("totalCurrentLiabilities")),
            "stockholders_equity": _safe_num(balance.get("totalStockholderEquity")),
            "long_term_debt": _safe_num(balance.get("longTermDebt")),
            "retained_earnings": _safe_num(balance.get("retainedEarnings")),
            "operating_cash_flow": _safe_num(cashflow.get("totalCashFromOperatingActivities")),
            "capital_expenditure": _safe_num(cashflow.get("capitalExpenditures")),
            "free_cash_flow": _safe_num(cashflow.get("freeCashFlow")),
            "dividends_paid": _safe_num(cashflow.get("dividendsPaid")),
            "data_source": data_source,
            "updated_at": datetime.utcnow(),
        }

        stmt = insert(QuarterlyFinancial).values(**values)
        update_vals = {k: v for k, v in values.items() if k not in ("ticker", "report_date")}
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "report_date"],
            set_=update_vals,
        )
        await session.execute(stmt)
        count += 1

    return count


async def get_quarterly_financials(
    session: AsyncSession, ticker: str
) -> list[dict]:
    """Get quarterly financials for a ticker, ordered by report_date desc."""
    result = await session.execute(
        select(QuarterlyFinancial)
        .where(QuarterlyFinancial.ticker == ticker)
        .order_by(QuarterlyFinancial.report_date.desc())
    )
    rows = result.scalars().all()

    return [
        {
            "report_date": r.report_date.isoformat(),
            "quarter": r.quarter,
            "year": r.year,
            "total_revenue": float(r.total_revenue) if r.total_revenue is not None else None,
            "gross_profit": float(r.gross_profit) if r.gross_profit is not None else None,
            "operating_income": float(r.operating_income) if r.operating_income is not None else None,
            "net_income": float(r.net_income) if r.net_income is not None else None,
            "ebit": float(r.ebit) if r.ebit is not None else None,
            "cost_of_revenue": float(r.cost_of_revenue) if r.cost_of_revenue is not None else None,
            "research_development": float(r.research_development) if r.research_development is not None else None,
            "selling_general_admin": float(r.selling_general_admin) if r.selling_general_admin is not None else None,
            "interest_expense": float(r.interest_expense) if r.interest_expense is not None else None,
            "tax_provision": float(r.tax_provision) if r.tax_provision is not None else None,
            "cash": float(r.cash) if r.cash is not None else None,
            "short_term_investments": float(r.short_term_investments) if r.short_term_investments is not None else None,
            "total_assets": float(r.total_assets) if r.total_assets is not None else None,
            "total_current_assets": float(r.total_current_assets) if r.total_current_assets is not None else None,
            "total_liabilities": float(r.total_liabilities) if r.total_liabilities is not None else None,
            "total_current_liabilities": float(r.total_current_liabilities) if r.total_current_liabilities is not None else None,
            "stockholders_equity": float(r.stockholders_equity) if r.stockholders_equity is not None else None,
            "long_term_debt": float(r.long_term_debt) if r.long_term_debt is not None else None,
            "retained_earnings": float(r.retained_earnings) if r.retained_earnings is not None else None,
            "operating_cash_flow": float(r.operating_cash_flow) if r.operating_cash_flow is not None else None,
            "capital_expenditure": float(r.capital_expenditure) if r.capital_expenditure is not None else None,
            "free_cash_flow": float(r.free_cash_flow) if r.free_cash_flow is not None else None,
            "dividends_paid": float(r.dividends_paid) if r.dividends_paid is not None else None,
            "data_source": r.data_source or "eodhd",
        }
        for r in rows
    ]


async def override_quarterly_financials(
    session: AsyncSession, ticker: str, overrides: list[dict]
) -> int:
    """Override quarterly financial rows with yfinance data.

    Each override dict should contain report_date plus financial fields.
    Sets data_source='yfinance' on each overridden row.
    """
    count = 0
    for item in overrides:
        report_date = item.get("report_date")
        if isinstance(report_date, str):
            report_date = datetime.strptime(report_date, "%Y-%m-%d").date()
        if not report_date:
            continue

        quarter, year = _date_to_quarter(report_date)

        values = {
            "ticker": ticker,
            "report_date": report_date,
            "quarter": quarter,
            "year": year,
            "total_revenue": _safe_num(item.get("total_revenue")),
            "gross_profit": _safe_num(item.get("gross_profit")),
            "operating_income": _safe_num(item.get("operating_income")),
            "net_income": _safe_num(item.get("net_income")),
            "ebit": _safe_num(item.get("ebit")),
            "cost_of_revenue": _safe_num(item.get("cost_of_revenue")),
            "research_development": _safe_num(item.get("research_development")),
            "selling_general_admin": _safe_num(item.get("selling_general_admin")),
            "interest_expense": _safe_num(item.get("interest_expense")),
            "tax_provision": _safe_num(item.get("tax_provision")),
            "cash": _safe_num(item.get("cash")),
            "short_term_investments": _safe_num(item.get("short_term_investments")),
            "total_assets": _safe_num(item.get("total_assets")),
            "total_current_assets": _safe_num(item.get("total_current_assets")),
            "total_liabilities": _safe_num(item.get("total_liabilities")),
            "total_current_liabilities": _safe_num(item.get("total_current_liabilities")),
            "stockholders_equity": _safe_num(item.get("stockholders_equity")),
            "long_term_debt": _safe_num(item.get("long_term_debt")),
            "retained_earnings": _safe_num(item.get("retained_earnings")),
            "operating_cash_flow": _safe_num(item.get("operating_cash_flow")),
            "capital_expenditure": _safe_num(item.get("capital_expenditure")),
            "free_cash_flow": _safe_num(item.get("free_cash_flow")),
            "dividends_paid": _safe_num(item.get("dividends_paid")),
            "data_source": "yfinance",
            "updated_at": datetime.utcnow(),
        }

        stmt = insert(QuarterlyFinancial).values(**values)
        update_vals = {k: v for k, v in values.items() if k not in ("ticker", "report_date")}
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "report_date"],
            set_=update_vals,
        )
        await session.execute(stmt)
        count += 1

    return count


# Company Highlights
async def store_company_highlights(
    session: AsyncSession, ticker: str, eodhd_data: dict
) -> None:
    """Parse EODHD fundamentals and store company highlights."""
    general = eodhd_data.get("General", {})
    highlights = eodhd_data.get("Highlights", {})
    valuation = eodhd_data.get("Valuation", {})
    shares_stats = eodhd_data.get("SharesStats", {})
    technicals = eodhd_data.get("Technicals", {})

    values = {
        "ticker": ticker,
        "name": general.get("Name"),
        "sector": general.get("Sector"),
        "industry": general.get("Industry"),
        "exchange": general.get("Exchange"),
        "currency": general.get("CurrencyCode"),
        "description": general.get("Description"),
        "pe_ratio": _safe_num(highlights.get("PERatio")),
        "forward_pe": _safe_num(highlights.get("ForwardPE")),
        "peg_ratio": _safe_num(valuation.get("PEGRatio")),
        "pb_ratio": _safe_num(valuation.get("PriceBookMRQ")),
        "ps_ratio": _safe_num(valuation.get("PriceSalesTTM")),
        "ev_revenue": _safe_num(valuation.get("EnterpriseValueRevenue")),
        "ev_ebitda": _safe_num(valuation.get("EnterpriseValueEbitda")),
        "enterprise_value": _safe_num(valuation.get("EnterpriseValue")),
        "profit_margin": _safe_num(highlights.get("ProfitMargin")),
        "operating_margin": _safe_num(highlights.get("OperatingMarginTTM")),
        "roe": _safe_num(highlights.get("ReturnOnEquityTTM")),
        "roa": _safe_num(highlights.get("ReturnOnAssetsTTM")),
        "gross_profit_ttm": _safe_num(highlights.get("GrossProfitTTM")),
        "ebitda": _safe_num(highlights.get("EBITDA")),
        "revenue_ttm": _safe_num(highlights.get("RevenueTTM")),
        "revenue_per_share": _safe_num(highlights.get("RevenuePerShareTTM")),
        "eps": _safe_num(highlights.get("EarningsShare")),
        "diluted_eps_ttm": _safe_num(highlights.get("DilutedEpsTTM")),
        "quarterly_revenue_growth_yoy": _safe_num(highlights.get("QuarterlyRevenueGrowthYOY")),
        "quarterly_earnings_growth_yoy": _safe_num(highlights.get("QuarterlyEarningsGrowthYOY")),
        "eps_estimate_current_year": _safe_num(highlights.get("EPSEstimateCurrentYear")),
        "wall_street_target_price": _safe_num(highlights.get("WallStreetTargetPrice")),
        "dividend_yield": _safe_num(highlights.get("DividendYield")),
        "dividend_share": _safe_num(highlights.get("DividendShare")),
        "shares_outstanding": _safe_num(shares_stats.get("SharesOutstanding")),
        "shares_float": _safe_num(shares_stats.get("SharesFloat")),
        "percent_insiders": _safe_num(shares_stats.get("PercentInsiders")),
        "percent_institutions": _safe_num(shares_stats.get("PercentInstitutions")),
        "shares_short": _safe_num(shares_stats.get("SharesShort")),
        "short_ratio": _safe_num(shares_stats.get("ShortRatio")),
        "beta": _safe_num(technicals.get("Beta")),
        "week_52_high": _safe_num(technicals.get("52WeekHigh")),
        "week_52_low": _safe_num(technicals.get("52WeekLow")),
        "day_50_ma": _safe_num(technicals.get("50DayMA")),
        "day_200_ma": _safe_num(technicals.get("200DayMA")),
        "market_cap": _safe_num(highlights.get("MarketCapitalization")),
        "updated_at": datetime.utcnow(),
    }

    stmt = insert(CompanyHighlight).values(**values)
    update_vals = {k: v for k, v in values.items() if k != "ticker"}
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_=update_vals,
    )
    await session.execute(stmt)


async def get_company_highlights(
    session: AsyncSession, ticker: str
) -> Optional[dict]:
    """Get company highlights for a ticker."""
    result = await session.execute(
        select(CompanyHighlight).where(CompanyHighlight.ticker == ticker)
    )
    h = result.scalar_one_or_none()

    if not h:
        return None

    def _f(val):
        """Convert Decimal to float."""
        return float(val) if val is not None else None

    return {
        "name": h.name,
        "sector": h.sector,
        "industry": h.industry,
        "exchange": h.exchange,
        "currency": h.currency,
        "description": h.description,
        "pe_ratio": _f(h.pe_ratio),
        "forward_pe": _f(h.forward_pe),
        "peg_ratio": _f(h.peg_ratio),
        "pb_ratio": _f(h.pb_ratio),
        "ps_ratio": _f(h.ps_ratio),
        "ev_revenue": _f(h.ev_revenue),
        "ev_ebitda": _f(h.ev_ebitda),
        "enterprise_value": h.enterprise_value,
        "profit_margin": _f(h.profit_margin),
        "operating_margin": _f(h.operating_margin),
        "roe": _f(h.roe),
        "roa": _f(h.roa),
        "gross_profit_ttm": h.gross_profit_ttm,
        "ebitda": h.ebitda,
        "revenue_ttm": h.revenue_ttm,
        "revenue_per_share": _f(h.revenue_per_share),
        "eps": _f(h.eps),
        "diluted_eps_ttm": _f(h.diluted_eps_ttm),
        "quarterly_revenue_growth_yoy": _f(h.quarterly_revenue_growth_yoy),
        "quarterly_earnings_growth_yoy": _f(h.quarterly_earnings_growth_yoy),
        "eps_estimate_current_year": _f(h.eps_estimate_current_year),
        "wall_street_target_price": _f(h.wall_street_target_price),
        "dividend_yield": _f(h.dividend_yield),
        "dividend_share": _f(h.dividend_share),
        "shares_outstanding": h.shares_outstanding,
        "shares_float": h.shares_float,
        "percent_insiders": _f(h.percent_insiders),
        "percent_institutions": _f(h.percent_institutions),
        "shares_short": h.shares_short,
        "short_ratio": _f(h.short_ratio),
        "beta": _f(h.beta),
        "week_52_high": _f(h.week_52_high),
        "week_52_low": _f(h.week_52_low),
        "day_50_ma": _f(h.day_50_ma),
        "day_200_ma": _f(h.day_200_ma),
        "market_cap": h.market_cap,
    }


# Shares History
async def store_shares_history(
    session: AsyncSession, ticker: str, entries: list[dict]
) -> int:
    """Upsert shares history entries. PK: (ticker, report_date, source)."""
    if not entries:
        return 0

    count = 0
    for entry in entries:
        report_date = entry.get("report_date")
        if isinstance(report_date, str):
            report_date = datetime.strptime(report_date, "%Y-%m-%d").date()

        filed_date = entry.get("filed_date")
        if isinstance(filed_date, str):
            filed_date = datetime.strptime(filed_date, "%Y-%m-%d").date()

        source = entry.get("source", "unknown")
        shares = entry.get("shares_outstanding")
        if not shares or not report_date:
            continue

        values = {
            "ticker": ticker,
            "report_date": report_date,
            "source": source,
            "shares_outstanding": int(shares),
            "filing_type": entry.get("filing_type"),
            "filed_date": filed_date,
            "fiscal_year": entry.get("fiscal_year"),
            "fiscal_period": entry.get("fiscal_period"),
            "updated_at": datetime.utcnow(),
        }

        stmt = insert(SharesHistory).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "report_date", "source"],
            set_={
                "shares_outstanding": int(shares),
                "filing_type": entry.get("filing_type"),
                "filed_date": filed_date,
                "fiscal_year": entry.get("fiscal_year"),
                "fiscal_period": entry.get("fiscal_period"),
                "updated_at": datetime.utcnow(),
            },
        )
        await session.execute(stmt)
        count += 1

    return count


async def get_shares_history(
    session: AsyncSession, ticker: str, source: Optional[str] = None
) -> list[dict]:
    """Get shares history for a ticker, ordered by report_date asc."""
    query = select(SharesHistory).where(SharesHistory.ticker == ticker)
    if source:
        query = query.where(SharesHistory.source == source)
    query = query.order_by(SharesHistory.report_date.asc())

    result = await session.execute(query)
    rows = result.scalars().all()

    return [
        {
            "report_date": r.report_date.isoformat(),
            "shares_outstanding": r.shares_outstanding,
            "source": r.source,
            "filing_type": r.filing_type,
            "filed_date": r.filed_date.isoformat() if r.filed_date else None,
            "fiscal_year": r.fiscal_year,
            "fiscal_period": r.fiscal_period,
        }
        for r in rows
    ]


async def get_latest_shares_outstanding(
    session: AsyncSession, ticker: str
) -> Optional[int]:
    """Get the most recent shares outstanding, preferring SEC EDGAR > yfinance > EODHD."""
    # Priority order for sources
    for source in ("sec_edgar", "yfinance", "eodhd"):
        query = (
            select(SharesHistory.shares_outstanding)
            .where(SharesHistory.ticker == ticker, SharesHistory.source == source)
            .order_by(SharesHistory.report_date.desc())
            .limit(1)
        )
        result = await session.execute(query)
        shares = result.scalar_one_or_none()
        if shares:
            return shares

    return None

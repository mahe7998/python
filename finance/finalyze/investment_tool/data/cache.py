"""DuckDB caching layer for market data."""

from datetime import date, datetime
from pathlib import Path
from typing import Optional, List, Tuple
import json

import duckdb
import pandas as pd

from investment_tool.data.models import (
    CompanyInfo,
    NewsArticle,
    SentimentData,
    Fundamentals,
    PeriodType,
    Watchlist,
    WatchlistItem,
    BacktestRun,
    BacktestResult,
    Trade,
    TradeType,
    CacheMetadata,
)


class CacheManager:
    """Manages DuckDB database for caching market data."""

    SCHEMA_VERSION = 1

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[duckdb.DuckDBPyConnection] = None
        self._initialize_database()

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        """Get database connection, creating if needed."""
        if self._conn is None:
            self._conn = duckdb.connect(str(self.database_path))
        return self._conn

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _initialize_database(self) -> None:
        """Initialize database schema."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        """)

        result = self.conn.execute("SELECT version FROM schema_version").fetchone()
        current_version = result[0] if result else 0

        if current_version < self.SCHEMA_VERSION:
            self._create_schema()
            self.conn.execute("DELETE FROM schema_version")
            self.conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                [self.SCHEMA_VERSION]
            )

        # Migrations that run on every startup to ensure tables exist
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_days (
                exchange VARCHAR,
                date DATE,
                PRIMARY KEY (exchange, date)
            )
        """)

    def _create_schema(self) -> None:
        """Create all database tables."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                ticker VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                exchange VARCHAR NOT NULL,
                sector VARCHAR,
                industry VARCHAR,
                market_cap DOUBLE,
                country VARCHAR,
                currency VARCHAR,
                pe_ratio DOUBLE,
                eps DOUBLE,
                last_updated TIMESTAMP
            )
        """)

        # Add pe_ratio and eps columns if they don't exist (for existing databases)
        try:
            self.conn.execute("ALTER TABLE companies ADD COLUMN pe_ratio DOUBLE")
        except Exception:
            pass  # Column already exists
        try:
            self.conn.execute("ALTER TABLE companies ADD COLUMN eps DOUBLE")
        except Exception:
            pass  # Column already exists

        # Create trading_days table if it doesn't exist (for existing databases)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_days (
                exchange VARCHAR,
                date DATE,
                PRIMARY KEY (exchange, date)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name VARCHAR NOT NULL,
                description VARCHAR,
                color VARCHAR
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS company_categories (
                ticker VARCHAR,
                category_id INTEGER,
                PRIMARY KEY (ticker, category_id)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_prices (
                ticker VARCHAR,
                date DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                adjusted_close DOUBLE,
                volume BIGINT,
                PRIMARY KEY (ticker, date)
            )
        """)

        # Trading days table - derived from daily_prices, stores known market open days
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_days (
                exchange VARCHAR,
                date DATE,
                PRIMARY KEY (exchange, date)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS intraday_prices (
                ticker VARCHAR,
                timestamp TIMESTAMP,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                PRIMARY KEY (ticker, timestamp)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS fundamentals (
                ticker VARCHAR,
                report_date DATE,
                period_type VARCHAR,
                revenue DOUBLE,
                net_income DOUBLE,
                eps DOUBLE,
                pe_ratio DOUBLE,
                pb_ratio DOUBLE,
                dividend_yield DOUBLE,
                debt_to_equity DOUBLE,
                roe DOUBLE,
                roa DOUBLE,
                free_cash_flow DOUBLE,
                raw_data JSON,
                PRIMARY KEY (ticker, report_date, period_type)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id VARCHAR PRIMARY KEY,
                ticker VARCHAR,
                published_at TIMESTAMP,
                title VARCHAR,
                summary TEXT,
                source VARCHAR,
                url VARCHAR,
                eodhd_polarity DOUBLE,
                eodhd_positive DOUBLE,
                eodhd_negative DOUBLE,
                eodhd_neutral DOUBLE,
                finbert_polarity DOUBLE,
                finbert_positive DOUBLE,
                finbert_negative DOUBLE,
                ensemble_polarity DOUBLE
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_sentiment (
                ticker VARCHAR,
                date DATE,
                news_count INTEGER,
                avg_polarity DOUBLE,
                positive_ratio DOUBLE,
                negative_ratio DOUBLE,
                social_mentions INTEGER,
                social_positive INTEGER,
                social_negative INTEGER,
                PRIMARY KEY (ticker, date)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlists (
                id INTEGER PRIMARY KEY,
                name VARCHAR NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS watchlist_id_seq
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist_items (
                watchlist_id INTEGER,
                ticker VARCHAR,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes VARCHAR,
                PRIMARY KEY (watchlist_id, ticker)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id VARCHAR PRIMARY KEY,
                name VARCHAR,
                strategy_name VARCHAR,
                start_date DATE,
                end_date DATE,
                initial_capital DOUBLE,
                parameters JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                run_id VARCHAR,
                ticker VARCHAR,
                total_return DOUBLE,
                annualized_return DOUBLE,
                sharpe_ratio DOUBLE,
                sortino_ratio DOUBLE,
                max_drawdown DOUBLE,
                win_rate DOUBLE,
                profit_factor DOUBLE,
                total_trades INTEGER,
                metrics JSON,
                PRIMARY KEY (run_id, ticker)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS backtest_trades (
                id INTEGER PRIMARY KEY,
                run_id VARCHAR,
                ticker VARCHAR,
                entry_date TIMESTAMP,
                exit_date TIMESTAMP,
                entry_price DOUBLE,
                exit_price DOUBLE,
                position_size DOUBLE,
                pnl DOUBLE,
                pnl_percent DOUBLE,
                trade_type VARCHAR
            )
        """)

        self.conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS trade_id_seq
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_metadata (
                key VARCHAR PRIMARY KEY,
                provider VARCHAR,
                ticker VARCHAR,
                data_type VARCHAR,
                start_date DATE,
                end_date DATE,
                last_fetched TIMESTAMP,
                record_count INTEGER
            )
        """)

    # ---- Company Methods ----

    def store_company(self, company: CompanyInfo) -> None:
        """Store or update company information."""
        self.conn.execute("""
            INSERT OR REPLACE INTO companies
            (ticker, name, exchange, sector, industry, market_cap, country, currency, pe_ratio, eps, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            company.ticker,
            company.name,
            company.exchange,
            company.sector,
            company.industry,
            company.market_cap,
            company.country,
            company.currency,
            company.pe_ratio,
            company.eps,
            company.last_updated or datetime.now(),
        ])

    def get_company(self, ticker: str) -> Optional[CompanyInfo]:
        """Get company information by ticker."""
        result = self.conn.execute(
            "SELECT ticker, name, exchange, sector, industry, market_cap, country, currency, pe_ratio, eps, last_updated FROM companies WHERE ticker = ?", [ticker]
        ).fetchone()

        if result is None:
            return None

        return CompanyInfo(
            ticker=result[0],
            name=result[1],
            exchange=result[2],
            sector=result[3],
            industry=result[4],
            market_cap=result[5],
            country=result[6],
            currency=result[7],
            pe_ratio=result[8],
            eps=result[9],
            last_updated=result[10],
        )

    def get_all_companies(self) -> List[CompanyInfo]:
        """Get all companies."""
        results = self.conn.execute(
            "SELECT ticker, name, exchange, sector, industry, market_cap, country, currency, pe_ratio, eps, last_updated FROM companies"
        ).fetchall()
        return [
            CompanyInfo(
                ticker=r[0],
                name=r[1],
                exchange=r[2],
                sector=r[3],
                industry=r[4],
                market_cap=r[5],
                country=r[6],
                currency=r[7],
                pe_ratio=r[8],
                eps=r[9],
                last_updated=r[10],
            )
            for r in results
        ]

    # ---- Daily Prices Methods ----

    def store_daily_prices(
        self, df: pd.DataFrame, ticker: str, exchange: str
    ) -> None:
        """Store daily price data from DataFrame."""
        if df.empty:
            return

        df = df.copy()
        df["ticker"] = ticker

        if "adjusted_close" not in df.columns:
            df["adjusted_close"] = df["close"]

        columns = ["ticker", "date", "open", "high", "low", "close", "adjusted_close", "volume"]
        df = df[columns]

        self.conn.execute("""
            INSERT OR REPLACE INTO daily_prices
            SELECT * FROM df
        """)

        # Also update trading_days table with these dates
        self.conn.execute("""
            INSERT OR IGNORE INTO trading_days (exchange, date)
            SELECT ?, date FROM df
        """, [exchange])

        self._update_cache_metadata(
            key=f"daily:{ticker}:{exchange}",
            provider="eodhd",
            ticker=ticker,
            data_type="daily_price",
            start_date=df["date"].min(),
            end_date=df["date"].max(),
            record_count=len(df),
        )

    def get_daily_prices(
        self,
        ticker: str,
        exchange: str,
        start: date,
        end: date,
    ) -> Optional[pd.DataFrame]:
        """Get daily prices for a ticker within date range."""
        df = self.conn.execute("""
            SELECT date, open, high, low, close, adjusted_close, volume
            FROM daily_prices
            WHERE ticker = ? AND date >= ? AND date <= ?
            ORDER BY date
        """, [ticker, start, end]).fetchdf()

        if df.empty:
            return None

        df["date"] = pd.to_datetime(df["date"]).dt.date
        df.set_index("date", inplace=True)
        return df

    def get_cached_date_range(
        self, ticker: str, exchange: str
    ) -> Optional[Tuple[date, date]]:
        """Get the date range of cached data for a ticker."""
        result = self.conn.execute("""
            SELECT MIN(date), MAX(date)
            FROM daily_prices
            WHERE ticker = ?
        """, [ticker]).fetchone()

        if result[0] is None:
            return None

        return (result[0], result[1])

    # ---- Intraday Prices Methods ----

    def store_intraday_prices(
        self, df: pd.DataFrame, ticker: str
    ) -> None:
        """Store intraday price data from DataFrame."""
        if df.empty:
            return

        df = df.copy()
        df["ticker"] = ticker

        columns = ["ticker", "timestamp", "open", "high", "low", "close", "volume"]
        df = df[columns]

        self.conn.execute("""
            INSERT OR REPLACE INTO intraday_prices
            SELECT * FROM df
        """)

    def get_intraday_prices(
        self,
        ticker: str,
        start: datetime,
        end: datetime,
    ) -> Optional[pd.DataFrame]:
        """Get intraday prices for a ticker within datetime range."""
        df = self.conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM intraday_prices
            WHERE ticker = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp
        """, [ticker, start, end]).fetchdf()

        if df.empty:
            return None

        df.set_index("timestamp", inplace=True)
        return df

    # ---- Trading Days Methods ----

    def update_trading_days_from_prices(self, exchange: str = "US") -> None:
        """Update trading_days table from existing daily_prices data.

        Extracts all unique dates from daily_prices and assigns to the given exchange.
        Since daily_prices doesn't store exchange suffix, we assume US as default.
        """
        self.conn.execute("""
            INSERT OR IGNORE INTO trading_days (exchange, date)
            SELECT DISTINCT ?, date
            FROM daily_prices
        """, [exchange])

    def get_trading_days(
        self,
        exchange: str,
        start: date,
        end: date,
    ) -> List[date]:
        """Get list of trading days for an exchange within a date range."""
        result = self.conn.execute("""
            SELECT date FROM trading_days
            WHERE exchange = ? AND date >= ? AND date <= ?
            ORDER BY date
        """, [exchange, start, end]).fetchall()
        return [row[0] for row in result]

    def get_nearest_trading_day(
        self,
        exchange: str,
        target_date: date,
        direction: str = "before",
    ) -> Optional[date]:
        """Find the nearest trading day to a target date.

        Args:
            direction: 'before' for the trading day on or before target,
                      'after' for the trading day on or after target
        """
        if direction == "before":
            result = self.conn.execute("""
                SELECT date FROM trading_days
                WHERE exchange = ? AND date <= ?
                ORDER BY date DESC
                LIMIT 1
            """, [exchange, target_date]).fetchone()
        else:
            result = self.conn.execute("""
                SELECT date FROM trading_days
                WHERE exchange = ? AND date >= ?
                ORDER BY date ASC
                LIMIT 1
            """, [exchange, target_date]).fetchone()

        return result[0] if result else None

    def get_trading_day_count(self, exchange: str) -> int:
        """Get total count of trading days for an exchange."""
        result = self.conn.execute("""
            SELECT COUNT(*) FROM trading_days WHERE exchange = ?
        """, [exchange]).fetchone()
        return result[0] if result else 0

    # ---- News Methods ----

    def store_news(self, articles: List[NewsArticle]) -> None:
        """Store news articles."""
        for article in articles:
            eodhd = article.eodhd_sentiment
            finbert = article.finbert_sentiment

            self.conn.execute("""
                INSERT OR REPLACE INTO news
                (id, ticker, published_at, title, summary, source, url,
                 eodhd_polarity, eodhd_positive, eodhd_negative, eodhd_neutral,
                 finbert_polarity, finbert_positive, finbert_negative,
                 ensemble_polarity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                article.id,
                article.ticker,
                article.published_at,
                article.title,
                article.summary,
                article.source,
                article.url,
                eodhd.polarity if eodhd else None,
                eodhd.positive if eodhd else None,
                eodhd.negative if eodhd else None,
                eodhd.neutral if eodhd else None,
                finbert.polarity if finbert else None,
                finbert.positive if finbert else None,
                finbert.negative if finbert else None,
                article.ensemble_polarity,
            ])

    def get_news(
        self,
        ticker: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[NewsArticle]:
        """Get news articles with optional filters."""
        query = "SELECT * FROM news WHERE 1=1"
        params = []

        if ticker:
            query += " AND ticker = ?"
            params.append(ticker)

        if start:
            query += " AND published_at >= ?"
            params.append(start)

        if end:
            query += " AND published_at <= ?"
            params.append(end)

        query += " ORDER BY published_at DESC LIMIT ?"
        params.append(limit)

        results = self.conn.execute(query, params).fetchall()

        articles = []
        for r in results:
            eodhd_sentiment = None
            if r[7] is not None:
                eodhd_sentiment = SentimentData(
                    polarity=r[7],
                    positive=r[8],
                    negative=r[9],
                    neutral=r[10],
                    source="eodhd",
                )

            finbert_sentiment = None
            if r[11] is not None:
                finbert_sentiment = SentimentData(
                    polarity=r[11],
                    positive=r[12],
                    negative=r[13],
                    source="finbert",
                )

            articles.append(NewsArticle(
                id=r[0],
                ticker=r[1],
                published_at=r[2],
                title=r[3],
                summary=r[4],
                source=r[5],
                url=r[6],
                eodhd_sentiment=eodhd_sentiment,
                finbert_sentiment=finbert_sentiment,
                ensemble_polarity=r[14],
            ))

        return articles

    # ---- Fundamentals Methods ----

    def store_fundamentals(self, fundamentals: Fundamentals) -> None:
        """Store fundamental data."""
        self.conn.execute("""
            INSERT OR REPLACE INTO fundamentals
            (ticker, report_date, period_type, revenue, net_income, eps,
             pe_ratio, pb_ratio, dividend_yield, debt_to_equity,
             roe, roa, free_cash_flow, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            fundamentals.ticker,
            fundamentals.report_date,
            fundamentals.period_type.value,
            fundamentals.revenue,
            fundamentals.net_income,
            fundamentals.eps,
            fundamentals.pe_ratio,
            fundamentals.pb_ratio,
            fundamentals.dividend_yield,
            fundamentals.debt_to_equity,
            fundamentals.roe,
            fundamentals.roa,
            fundamentals.free_cash_flow,
            json.dumps(fundamentals.raw_data) if fundamentals.raw_data else None,
        ])

    def get_fundamentals(
        self, ticker: str, period_type: Optional[PeriodType] = None
    ) -> List[Fundamentals]:
        """Get fundamental data for a ticker."""
        query = "SELECT * FROM fundamentals WHERE ticker = ?"
        params = [ticker]

        if period_type:
            query += " AND period_type = ?"
            params.append(period_type.value)

        query += " ORDER BY report_date DESC"
        results = self.conn.execute(query, params).fetchall()

        return [
            Fundamentals(
                ticker=r[0],
                report_date=r[1],
                period_type=PeriodType(r[2]),
                revenue=r[3],
                net_income=r[4],
                eps=r[5],
                pe_ratio=r[6],
                pb_ratio=r[7],
                dividend_yield=r[8],
                debt_to_equity=r[9],
                roe=r[10],
                roa=r[11],
                free_cash_flow=r[12],
                raw_data=json.loads(r[13]) if r[13] else None,
            )
            for r in results
        ]

    # ---- Watchlist Methods ----

    def create_watchlist(self, name: str) -> Watchlist:
        """Create a new watchlist."""
        watchlist_id = self.conn.execute(
            "SELECT nextval('watchlist_id_seq')"
        ).fetchone()[0]

        now = datetime.now()
        self.conn.execute("""
            INSERT INTO watchlists (id, name, created_at)
            VALUES (?, ?, ?)
        """, [watchlist_id, name, now])

        return Watchlist(id=watchlist_id, name=name, created_at=now)

    def get_watchlists(self) -> List[Watchlist]:
        """Get all watchlists."""
        results = self.conn.execute(
            "SELECT id, name, created_at FROM watchlists ORDER BY created_at"
        ).fetchall()

        return [
            Watchlist(id=r[0], name=r[1], created_at=r[2])
            for r in results
        ]

    def delete_watchlist(self, watchlist_id: int) -> None:
        """Delete a watchlist and its items."""
        self.conn.execute(
            "DELETE FROM watchlist_items WHERE watchlist_id = ?", [watchlist_id]
        )
        self.conn.execute(
            "DELETE FROM watchlists WHERE id = ?", [watchlist_id]
        )

    def add_to_watchlist(
        self, watchlist_id: int, ticker: str, notes: Optional[str] = None
    ) -> None:
        """Add a stock to a watchlist."""
        self.conn.execute("""
            INSERT OR REPLACE INTO watchlist_items (watchlist_id, ticker, added_at, notes)
            VALUES (?, ?, ?, ?)
        """, [watchlist_id, ticker, datetime.now(), notes])

    def remove_from_watchlist(self, watchlist_id: int, ticker: str) -> None:
        """Remove a stock from a watchlist."""
        self.conn.execute("""
            DELETE FROM watchlist_items
            WHERE watchlist_id = ? AND ticker = ?
        """, [watchlist_id, ticker])

    def get_watchlist_items(self, watchlist_id: int) -> List[WatchlistItem]:
        """Get all items in a watchlist."""
        results = self.conn.execute("""
            SELECT watchlist_id, ticker, added_at, notes
            FROM watchlist_items
            WHERE watchlist_id = ?
            ORDER BY added_at
        """, [watchlist_id]).fetchall()

        return [
            WatchlistItem(
                watchlist_id=r[0],
                ticker=r[1],
                added_at=r[2],
                notes=r[3],
            )
            for r in results
        ]

    # ---- Backtest Methods ----

    def store_backtest_run(self, run: BacktestRun) -> None:
        """Store a backtest run configuration."""
        self.conn.execute("""
            INSERT OR REPLACE INTO backtest_runs
            (id, name, strategy_name, start_date, end_date, initial_capital, parameters, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            run.id,
            run.name,
            run.strategy_name,
            run.start_date,
            run.end_date,
            run.initial_capital,
            json.dumps(run.parameters),
            run.created_at,
        ])

    def store_backtest_result(self, result: BacktestResult) -> None:
        """Store backtest results."""
        self.conn.execute("""
            INSERT OR REPLACE INTO backtest_results
            (run_id, ticker, total_return, annualized_return, sharpe_ratio,
             sortino_ratio, max_drawdown, win_rate, profit_factor, total_trades, metrics)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            result.run_id,
            result.ticker,
            result.total_return,
            result.annualized_return,
            result.sharpe_ratio,
            result.sortino_ratio,
            result.max_drawdown,
            result.win_rate,
            result.profit_factor,
            result.total_trades,
            json.dumps(result.metrics),
        ])

    def store_trades(self, trades: List[Trade]) -> None:
        """Store backtest trades."""
        for trade in trades:
            trade_id = self.conn.execute(
                "SELECT nextval('trade_id_seq')"
            ).fetchone()[0]

            self.conn.execute("""
                INSERT INTO backtest_trades
                (id, run_id, ticker, entry_date, exit_date, entry_price, exit_price,
                 position_size, pnl, pnl_percent, trade_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                trade_id,
                trade.run_id,
                trade.ticker,
                trade.entry_date,
                trade.exit_date,
                trade.entry_price,
                trade.exit_price,
                trade.position_size,
                trade.pnl,
                trade.pnl_percent,
                trade.trade_type.value,
            ])

    def get_backtest_runs(self) -> List[BacktestRun]:
        """Get all backtest runs."""
        results = self.conn.execute("""
            SELECT id, name, strategy_name, start_date, end_date,
                   initial_capital, parameters, created_at
            FROM backtest_runs
            ORDER BY created_at DESC
        """).fetchall()

        return [
            BacktestRun(
                id=r[0],
                name=r[1],
                strategy_name=r[2],
                start_date=r[3],
                end_date=r[4],
                initial_capital=r[5],
                parameters=json.loads(r[6]) if r[6] else {},
                created_at=r[7],
            )
            for r in results
        ]

    def get_backtest_results(self, run_id: str) -> List[BacktestResult]:
        """Get results for a backtest run."""
        results = self.conn.execute("""
            SELECT run_id, ticker, total_return, annualized_return, sharpe_ratio,
                   sortino_ratio, max_drawdown, win_rate, profit_factor, total_trades, metrics
            FROM backtest_results
            WHERE run_id = ?
        """, [run_id]).fetchall()

        return [
            BacktestResult(
                run_id=r[0],
                ticker=r[1],
                total_return=r[2],
                annualized_return=r[3],
                sharpe_ratio=r[4],
                sortino_ratio=r[5],
                max_drawdown=r[6],
                win_rate=r[7],
                profit_factor=r[8],
                total_trades=r[9],
                metrics=json.loads(r[10]) if r[10] else {},
            )
            for r in results
        ]

    def get_backtest_trades(self, run_id: str) -> List[Trade]:
        """Get trades for a backtest run."""
        results = self.conn.execute("""
            SELECT id, run_id, ticker, entry_date, exit_date, entry_price,
                   exit_price, position_size, pnl, pnl_percent, trade_type
            FROM backtest_trades
            WHERE run_id = ?
            ORDER BY entry_date
        """, [run_id]).fetchall()

        return [
            Trade(
                id=r[0],
                run_id=r[1],
                ticker=r[2],
                entry_date=r[3],
                exit_date=r[4],
                entry_price=r[5],
                exit_price=r[6],
                position_size=r[7],
                pnl=r[8],
                pnl_percent=r[9],
                trade_type=TradeType(r[10]),
            )
            for r in results
        ]

    # ---- Cache Metadata Methods ----

    def _update_cache_metadata(
        self,
        key: str,
        provider: str,
        ticker: str,
        data_type: str,
        start_date: date,
        end_date: date,
        record_count: int,
    ) -> None:
        """Update cache metadata."""
        self.conn.execute("""
            INSERT OR REPLACE INTO cache_metadata
            (key, provider, ticker, data_type, start_date, end_date, last_fetched, record_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [key, provider, ticker, data_type, start_date, end_date, datetime.now(), record_count])

    def get_cache_metadata(self, key: str) -> Optional[CacheMetadata]:
        """Get cache metadata by key."""
        result = self.conn.execute(
            "SELECT * FROM cache_metadata WHERE key = ?", [key]
        ).fetchone()

        if result is None:
            return None

        return CacheMetadata(
            key=result[0],
            provider=result[1],
            ticker=result[2],
            data_type=result[3],
            start_date=result[4],
            end_date=result[5],
            last_fetched=result[6],
            record_count=result[7],
        )

    def get_cache_size(self) -> int:
        """Get total cache size in bytes."""
        if self.database_path.exists():
            return self.database_path.stat().st_size
        return 0

    def clear_old_cache(self, days: int = 7) -> int:
        """Clear cache entries older than specified days. Returns count of deleted entries."""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)

        count = self.conn.execute("""
            SELECT COUNT(*) FROM cache_metadata WHERE last_fetched < ?
        """, [cutoff]).fetchone()[0]

        self.conn.execute("""
            DELETE FROM cache_metadata WHERE last_fetched < ?
        """, [cutoff])

        return count

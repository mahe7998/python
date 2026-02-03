# Investment Tracking & Analysis Tool - Project Plan

## Project Overview

Build a local-only (non-web) Python desktop application for comprehensive investment tracking and analysis. The tool should provide interactive market visualization, multi-source data integration, sentiment analysis, and reinforcement learning backtesting capabilities.

**Target User**: Individual investor/trader who wants professional-grade analysis tools with full data ownership.

**Key Principles**:
- Local-first: All data stored locally, works offline with cached data
- Extensible: Easy to add/replace data providers
- Interactive: Fast, responsive UI with real-time updates
- Professional: Institutional-quality visualizations and analysis

---

## Technology Stack

### Core Framework
```
GUI:            PySide6 (Qt6) - LGPL license, official Qt binding
Visualization:  pyqtgraph (real-time), matplotlib (static), mplfinance (candlesticks)
Database:       DuckDB (columnar, fast analytics)
```

### Data & Analysis
```
Data Provider:  EODHD (primary, $30/mo plan) - extensible architecture
ML/DL:          PyTorch, stable-baselines3, FinRL
NLP:            transformers (FinBERT), faster-whisper
Analysis:       pandas, numpy, statsmodels, arch, PyPortfolioOpt
```

### Project Structure
```
investment_tool/
├── main.py                     # Application entry point
├── config/
│   ├── __init__.py
│   ├── settings.py             # App settings, API keys, paths
│   └── categories.py           # Stock categories/sectors definitions
├── data/
│   ├── __init__.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py             # Abstract base provider
│   │   ├── eodhd.py            # EODHD implementation
│   │   ├── polygon.py          # Polygon.io (future)
│   │   ├── akshare.py          # China A-shares (future)
│   │   └── finnhub.py          # Finnhub for social sentiment
│   ├── cache.py                # DuckDB caching layer
│   ├── manager.py              # Data manager (orchestrates providers)
│   └── models.py               # Data models (dataclasses/pydantic)
├── analysis/
│   ├── __init__.py
│   ├── sentiment/
│   │   ├── __init__.py
│   │   ├── aggregator.py       # Multi-source sentiment aggregation
│   │   ├── finbert.py          # Local FinBERT analysis
│   │   └── signals.py          # Sentiment-based signals
│   ├── technical/
│   │   ├── __init__.py
│   │   ├── indicators.py       # Technical indicators
│   │   └── patterns.py         # Chart patterns
│   ├── fundamental/
│   │   ├── __init__.py
│   │   └── metrics.py          # Fundamental analysis
│   └── portfolio/
│       ├── __init__.py
│       ├── optimization.py     # Portfolio optimization
│       └── risk.py             # Risk metrics
├── backtesting/
│   ├── __init__.py
│   ├── engine.py               # Backtesting engine
│   ├── environments/
│   │   ├── __init__.py
│   │   └── trading_env.py      # Gymnasium environment
│   ├── agents/
│   │   ├── __init__.py
│   │   └── rl_agents.py        # RL agent wrappers
│   └── strategies/
│       ├── __init__.py
│       └── base_strategies.py  # Strategy definitions
├── ui/
│   ├── __init__.py
│   ├── main_window.py          # Main application window
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── market_treemap.py   # Interactive market treemap
│   │   ├── sector_view.py      # Sector breakdown view
│   │   ├── stock_chart.py      # Individual stock chart
│   │   ├── comparison_chart.py # Multi-stock comparison
│   │   ├── news_feed.py        # News with sentiment
│   │   ├── sentiment_gauge.py  # Sentiment visualization
│   │   ├── watchlist.py        # Watchlist management
│   │   ├── screener.py         # Stock screener
│   │   └── backtest_dashboard.py # Backtesting interface
│   ├── dialogs/
│   │   ├── __init__.py
│   │   ├── settings_dialog.py  # Settings configuration
│   │   ├── add_stock_dialog.py # Add stock to watchlist
│   │   └── category_dialog.py  # Manage categories
│   └── styles/
│       ├── __init__.py
│       └── theme.py            # Dark/light theme, colors
├── utils/
│   ├── __init__.py
│   ├── logging.py              # Logging configuration
│   ├── threading.py            # Thread workers for data fetching
│   └── helpers.py              # Utility functions
├── resources/
│   ├── icons/                  # UI icons
│   └── default_categories.json # Default stock categories
├── tests/
│   ├── __init__.py
│   ├── test_providers.py
│   ├── test_analysis.py
│   └── test_ui.py
├── requirements.txt
├── setup.py
└── README.md
```

---

## Database Schema (DuckDB)

```sql
-- Companies and categories
CREATE TABLE companies (
    ticker VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    exchange VARCHAR NOT NULL,      -- US, XETRA, TSE, HK, SHG, etc.
    sector VARCHAR,
    industry VARCHAR,
    market_cap DOUBLE,
    country VARCHAR,
    currency VARCHAR,
    last_updated TIMESTAMP
);

CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,          -- AI, Defense, Finance, etc.
    description VARCHAR,
    color VARCHAR                   -- Hex color for visualization
);

CREATE TABLE company_categories (
    ticker VARCHAR REFERENCES companies(ticker),
    category_id INTEGER REFERENCES categories(id),
    PRIMARY KEY (ticker, category_id)
);

-- Price data
CREATE TABLE daily_prices (
    ticker VARCHAR,
    date DATE,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    adjusted_close DOUBLE,
    volume BIGINT,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE intraday_prices (
    ticker VARCHAR,
    timestamp TIMESTAMP,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume BIGINT,
    PRIMARY KEY (ticker, timestamp)
);

-- Fundamentals
CREATE TABLE fundamentals (
    ticker VARCHAR,
    report_date DATE,
    period_type VARCHAR,            -- Q1, Q2, Q3, Q4, FY
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
    raw_data JSON,                  -- Full JSON from provider
    PRIMARY KEY (ticker, report_date, period_type)
);

-- News and sentiment
CREATE TABLE news (
    id VARCHAR PRIMARY KEY,
    ticker VARCHAR,
    published_at TIMESTAMP,
    title VARCHAR,
    summary TEXT,
    source VARCHAR,
    url VARCHAR,
    -- EODHD sentiment
    eodhd_polarity DOUBLE,
    eodhd_positive DOUBLE,
    eodhd_negative DOUBLE,
    eodhd_neutral DOUBLE,
    -- FinBERT sentiment (local)
    finbert_polarity DOUBLE,
    finbert_positive DOUBLE,
    finbert_negative DOUBLE,
    -- Ensemble
    ensemble_polarity DOUBLE
);

CREATE TABLE daily_sentiment (
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
);

-- Watchlists
CREATE TABLE watchlists (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE watchlist_items (
    watchlist_id INTEGER REFERENCES watchlists(id),
    ticker VARCHAR REFERENCES companies(ticker),
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes VARCHAR,
    PRIMARY KEY (watchlist_id, ticker)
);

-- Backtesting
CREATE TABLE backtest_runs (
    id VARCHAR PRIMARY KEY,
    name VARCHAR,
    strategy_name VARCHAR,
    start_date DATE,
    end_date DATE,
    initial_capital DOUBLE,
    parameters JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE backtest_results (
    run_id VARCHAR REFERENCES backtest_runs(id),
    ticker VARCHAR,
    total_return DOUBLE,
    annualized_return DOUBLE,
    sharpe_ratio DOUBLE,
    sortino_ratio DOUBLE,
    max_drawdown DOUBLE,
    win_rate DOUBLE,
    profit_factor DOUBLE,
    total_trades INTEGER,
    metrics JSON,                   -- Additional metrics
    PRIMARY KEY (run_id, ticker)
);

CREATE TABLE backtest_trades (
    id INTEGER PRIMARY KEY,
    run_id VARCHAR REFERENCES backtest_runs(id),
    ticker VARCHAR,
    entry_date TIMESTAMP,
    exit_date TIMESTAMP,
    entry_price DOUBLE,
    exit_price DOUBLE,
    position_size DOUBLE,
    pnl DOUBLE,
    pnl_percent DOUBLE,
    trade_type VARCHAR              -- LONG, SHORT
);

-- Cache metadata
CREATE TABLE cache_metadata (
    key VARCHAR PRIMARY KEY,
    provider VARCHAR,
    ticker VARCHAR,
    data_type VARCHAR,              -- daily_price, intraday, fundamentals, news
    start_date DATE,
    end_date DATE,
    last_fetched TIMESTAMP,
    record_count INTEGER
);
```

---

## UI Components Specification

### 1. Main Window Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Menu Bar: File | View | Data | Analysis | Backtest | Settings | Help   │
├─────────────────────────────────────────────────────────────────────────┤
│  Toolbar: [Refresh] [Add Stock] [Categories] [Screener] [Settings]      │
├───────────────────────────────────┬─────────────────────────────────────┤
│                                   │                                     │
│       MARKET TREEMAP              │         DETAIL PANEL               │
│    (Main interactive view)        │    (Context-sensitive)             │
│                                   │                                     │
│   ┌─────────┬──────┬────────┐    │   ┌─────────────────────────────┐  │
│   │  NVDA   │ MSFT │  GOOGL │    │   │  Stock Chart (candlestick)  │  │
│   │  +2.3%  │+1.1% │  -0.5% │    │   │  with indicators            │  │
│   ├─────────┼──────┴────────┤    │   └─────────────────────────────┘  │
│   │  AMD    │     AAPL      │    │   ┌─────────────────────────────┐  │
│   │  +4.2%  │     +0.8%     │    │   │  Key Metrics / Fundamentals │  │
│   ├─────────┴───────────────┤    │   └─────────────────────────────┘  │
│   │         TSLA            │    │   ┌─────────────────────────────┐  │
│   │         -1.2%           │    │   │  Sentiment Gauge            │  │
│   └─────────────────────────┘    │   └─────────────────────────────┘  │
│                                   │                                     │
├───────────────────────────────────┴─────────────────────────────────────┤
│  BOTTOM PANEL (Tabbed: News Feed | Watchlist | Screener | Backtest)     │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │ 🟢 +0.83 | NVDA announces new AI chip partnership         | 2h ago ││
│  │ 🔴 -0.45 | AMD faces supply chain concerns                | 3h ago ││
│  │ 🟡 +0.12 | Tech sector sees mixed trading                 | 4h ago ││
│  └─────────────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────────────┤
│  Status Bar: Last Update: 14:32:05 | EODHD: Connected | Cache: 1.2GB    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2. Market Treemap Widget

**Purpose**: Bird's eye view of entire market or category, with box sizes proportional to market cap and colors indicating performance.

**Features**:
- Hierarchical: Sector → Industry → Stock
- Click to drill down (Sector view → Stock view)
- Right-click context menu: Add to watchlist, View details, Compare
- Hover shows tooltip with key metrics
- Color scale: Red (down) → White (flat) → Green (up)
- Time period selector: 1D, 1W, 1M, 3M, YTD, 1Y
- Filter by category/watchlist

**Interactions**:
- Single click: Select stock, show in detail panel
- Double click: Open dedicated stock window
- Ctrl+click: Add to comparison
- Scroll wheel: Zoom in/out
- Drag: Pan view

### 3. Sector View Widget

**Purpose**: Compare performance across sectors/categories with drill-down capability.

**Features**:
- Bar chart showing sector performance
- Expandable to show top stocks in each sector
- Sortable by: Performance, Market Cap, Volume, Sentiment
- Mini-sparklines for each sector showing trend

### 4. Stock Chart Widget

**Purpose**: Detailed price chart with technical analysis tools.

**Features**:
- Chart types: Candlestick, OHLC, Line, Area
- Timeframes: 1m, 5m, 15m, 1h, 4h, 1D, 1W, 1M
- Indicators (overlay): SMA, EMA, Bollinger Bands, VWAP
- Indicators (separate pane): RSI, MACD, Volume, OBV, ATR
- Drawing tools: Trendlines, Fibonacci, Rectangles
- Volume profile
- Compare with other stocks/indices
- Crosshair with price/time display

**Interactions**:
- Scroll to zoom time axis
- Drag to pan
- Click+drag to draw
- Right-click for indicator menu

### 5. News Feed Widget

**Purpose**: Real-time news with sentiment visualization.

**Features**:
- Color-coded sentiment indicator (red/yellow/green dot)
- Polarity score displayed
- Filter by: Stock, Category, Sentiment threshold
- Click to expand full article
- Mark as read/unread
- Tag articles for later
- Sentiment trend chart (mini)

### 6. Sentiment Gauge Widget

**Purpose**: Visual representation of current sentiment for selected stock/category.

**Features**:
- Dial gauge showing overall sentiment (-1 to +1)
- Breakdown: News vs Social sentiment
- Historical sentiment chart (7-day trend)
- Sentiment momentum indicator
- Word cloud of recent keywords

### 7. Comparison Chart Widget

**Purpose**: Compare multiple stocks side-by-side.

**Features**:
- Normalized price chart (rebased to 100)
- Performance table with metrics
- Correlation matrix
- Relative strength chart
- Add/remove stocks easily

### 8. Watchlist Widget

**Purpose**: Manage custom watchlists with quick metrics.

**Features**:
- Multiple watchlists (tabs)
- Sortable columns: Ticker, Price, Change%, Volume, Sentiment
- Mini sparkline for each stock
- Drag-drop reordering
- Quick actions: Remove, View chart, Compare
- Import/export watchlists

### 9. Stock Screener Widget

**Purpose**: Find stocks based on criteria.

**Features**:
- Filter criteria:
  - Price range
  - Market cap range
  - Performance (1D, 1W, 1M, etc.)
  - Volume
  - Sector/Industry
  - Country/Exchange
  - Sentiment score
  - Technical indicators (RSI, above/below MA, etc.)
  - Fundamental ratios (P/E, P/B, etc.)
- Save/load screening profiles
- Results table with sortable columns
- Export results

### 10. Backtest Dashboard Widget

**Purpose**: Configure, run, and analyze backtests.

**Features**:
- Strategy selection (dropdown)
- Parameter configuration
- Date range picker
- Stock/universe selection
- Run progress indicator
- Results:
  - Equity curve chart
  - Performance metrics table
  - Trade list
  - Drawdown chart
  - Monthly returns heatmap
- Compare multiple backtest runs
- Save/load configurations

---

## Data Provider Architecture

### Abstract Base Provider

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, List, Dict, Any
import pandas as pd

@dataclass
class PriceBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: Optional[float] = None

@dataclass
class NewsArticle:
    id: str
    ticker: str
    title: str
    summary: str
    published_at: datetime
    source: str
    url: str
    sentiment: Optional[Dict[str, float]] = None

@dataclass
class CompanyInfo:
    ticker: str
    name: str
    exchange: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    country: Optional[str] = None
    currency: Optional[str] = None

class DataProviderBase(ABC):
    """Abstract base class for all data providers"""
    
    def __init__(self, api_key: str, cache: 'CacheManager'):
        self.api_key = api_key
        self.cache = cache
        self.name = self.__class__.__name__
    
    @abstractmethod
    def get_daily_prices(
        self, 
        ticker: str, 
        exchange: str,
        start: date, 
        end: date
    ) -> pd.DataFrame:
        """Fetch daily OHLCV data"""
        pass
    
    @abstractmethod
    def get_intraday_prices(
        self,
        ticker: str,
        exchange: str,
        interval: str,  # 1m, 5m, 15m, 1h
        start: datetime,
        end: datetime
    ) -> pd.DataFrame:
        """Fetch intraday OHLCV data"""
        pass
    
    @abstractmethod
    def get_company_info(self, ticker: str, exchange: str) -> CompanyInfo:
        """Fetch company metadata"""
        pass
    
    @abstractmethod
    def get_fundamentals(self, ticker: str, exchange: str) -> Dict[str, Any]:
        """Fetch fundamental data"""
        pass
    
    @abstractmethod
    def get_news(
        self,
        ticker: str,
        limit: int = 50
    ) -> List[NewsArticle]:
        """Fetch news with sentiment"""
        pass
    
    @abstractmethod
    def get_bulk_prices(
        self,
        exchange: str,
        date: Optional[date] = None
    ) -> pd.DataFrame:
        """Bulk download all prices for an exchange"""
        pass
    
    @abstractmethod
    def search_tickers(self, query: str) -> List[CompanyInfo]:
        """Search for tickers by name or symbol"""
        pass
    
    def format_symbol(self, ticker: str, exchange: str) -> str:
        """Format symbol for this provider's API"""
        return f"{ticker}.{exchange}"
    
    def is_available(self) -> bool:
        """Check if provider is available/configured"""
        return bool(self.api_key)
```

### Provider Priority System

```python
class DataManager:
    """Orchestrates multiple data providers with fallback"""
    
    def __init__(self, cache: CacheManager, config: Config):
        self.cache = cache
        self.providers: Dict[str, DataProviderBase] = {}
        self.provider_priority = []
        self._setup_providers(config)
    
    def _setup_providers(self, config: Config):
        # Primary: EODHD
        if config.eodhd_api_key:
            self.providers['eodhd'] = EODHDProvider(
                config.eodhd_api_key, self.cache
            )
            self.provider_priority.append('eodhd')
        
        # Optional: Polygon for US tick data
        if config.polygon_api_key:
            self.providers['polygon'] = PolygonProvider(
                config.polygon_api_key, self.cache
            )
        
        # Optional: AKShare for China
        if config.enable_akshare:
            self.providers['akshare'] = AKShareProvider(self.cache)
        
        # Optional: Finnhub for social sentiment
        if config.finnhub_api_key:
            self.providers['finnhub'] = FinnhubProvider(
                config.finnhub_api_key, self.cache
            )
    
    def get_daily_prices(
        self, 
        ticker: str, 
        exchange: str,
        start: date,
        end: date,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Get daily prices with smart caching and provider fallback.
        
        1. Check cache for existing data
        2. Fetch only missing date ranges
        3. Try providers in priority order
        4. Cache new data
        """
        cache_key = f"daily:{ticker}:{exchange}"
        
        if use_cache:
            cached = self.cache.get_daily_prices(ticker, exchange, start, end)
            if cached is not None and len(cached) > 0:
                # Check if we have all needed dates
                missing_ranges = self._find_missing_ranges(
                    cached, start, end
                )
                if not missing_ranges:
                    return cached
                # Fetch only missing ranges
                for range_start, range_end in missing_ranges:
                    new_data = self._fetch_from_providers(
                        'get_daily_prices',
                        ticker=ticker,
                        exchange=exchange,
                        start=range_start,
                        end=range_end
                    )
                    if new_data is not None:
                        self.cache.store_daily_prices(new_data, ticker, exchange)
                        cached = pd.concat([cached, new_data]).drop_duplicates()
                return cached.sort_index()
        
        # No cache, fetch all
        data = self._fetch_from_providers(
            'get_daily_prices',
            ticker=ticker,
            exchange=exchange,
            start=start,
            end=end
        )
        if data is not None and use_cache:
            self.cache.store_daily_prices(data, ticker, exchange)
        return data
    
    def _fetch_from_providers(
        self, 
        method: str, 
        **kwargs
    ) -> Optional[pd.DataFrame]:
        """Try providers in priority order until one succeeds"""
        for provider_name in self.provider_priority:
            provider = self.providers.get(provider_name)
            if provider and provider.is_available():
                try:
                    func = getattr(provider, method)
                    return func(**kwargs)
                except Exception as e:
                    logger.warning(
                        f"Provider {provider_name} failed for {method}: {e}"
                    )
                    continue
        return None
```

---

## Default Stock Categories

```json
{
  "categories": [
    {
      "id": 1,
      "name": "AI & Machine Learning",
      "color": "#8B5CF6",
      "stocks": [
        {"ticker": "NVDA", "exchange": "US"},
        {"ticker": "AMD", "exchange": "US"},
        {"ticker": "GOOGL", "exchange": "US"},
        {"ticker": "MSFT", "exchange": "US"},
        {"ticker": "META", "exchange": "US"},
        {"ticker": "AMZN", "exchange": "US"},
        {"ticker": "PLTR", "exchange": "US"},
        {"ticker": "AI", "exchange": "US"},
        {"ticker": "PATH", "exchange": "US"},
        {"ticker": "SNOW", "exchange": "US"}
      ]
    },
    {
      "id": 2,
      "name": "Semiconductors",
      "color": "#06B6D4",
      "stocks": [
        {"ticker": "NVDA", "exchange": "US"},
        {"ticker": "AMD", "exchange": "US"},
        {"ticker": "INTC", "exchange": "US"},
        {"ticker": "AVGO", "exchange": "US"},
        {"ticker": "QCOM", "exchange": "US"},
        {"ticker": "TSM", "exchange": "US"},
        {"ticker": "ASML", "exchange": "US"},
        {"ticker": "LRCX", "exchange": "US"},
        {"ticker": "AMAT", "exchange": "US"},
        {"ticker": "MU", "exchange": "US"}
      ]
    },
    {
      "id": 3,
      "name": "Defense & Aerospace",
      "color": "#EF4444",
      "stocks": [
        {"ticker": "LMT", "exchange": "US"},
        {"ticker": "RTX", "exchange": "US"},
        {"ticker": "NOC", "exchange": "US"},
        {"ticker": "GD", "exchange": "US"},
        {"ticker": "BA", "exchange": "US"},
        {"ticker": "LHX", "exchange": "US"},
        {"ticker": "HII", "exchange": "US"},
        {"ticker": "TDG", "exchange": "US"}
      ]
    },
    {
      "id": 4,
      "name": "Finance & Banks",
      "color": "#10B981",
      "stocks": [
        {"ticker": "JPM", "exchange": "US"},
        {"ticker": "BAC", "exchange": "US"},
        {"ticker": "WFC", "exchange": "US"},
        {"ticker": "GS", "exchange": "US"},
        {"ticker": "MS", "exchange": "US"},
        {"ticker": "C", "exchange": "US"},
        {"ticker": "BLK", "exchange": "US"},
        {"ticker": "SCHW", "exchange": "US"}
      ]
    },
    {
      "id": 5,
      "name": "Electric Vehicles",
      "color": "#F59E0B",
      "stocks": [
        {"ticker": "TSLA", "exchange": "US"},
        {"ticker": "RIVN", "exchange": "US"},
        {"ticker": "LCID", "exchange": "US"},
        {"ticker": "NIO", "exchange": "US"},
        {"ticker": "XPEV", "exchange": "US"},
        {"ticker": "LI", "exchange": "US"},
        {"ticker": "F", "exchange": "US"},
        {"ticker": "GM", "exchange": "US"}
      ]
    },
    {
      "id": 6,
      "name": "Healthcare & Biotech",
      "color": "#EC4899",
      "stocks": [
        {"ticker": "JNJ", "exchange": "US"},
        {"ticker": "UNH", "exchange": "US"},
        {"ticker": "PFE", "exchange": "US"},
        {"ticker": "ABBV", "exchange": "US"},
        {"ticker": "MRK", "exchange": "US"},
        {"ticker": "LLY", "exchange": "US"},
        {"ticker": "TMO", "exchange": "US"},
        {"ticker": "ABT", "exchange": "US"}
      ]
    },
    {
      "id": 7,
      "name": "Energy & Oil",
      "color": "#6366F1",
      "stocks": [
        {"ticker": "XOM", "exchange": "US"},
        {"ticker": "CVX", "exchange": "US"},
        {"ticker": "COP", "exchange": "US"},
        {"ticker": "SLB", "exchange": "US"},
        {"ticker": "EOG", "exchange": "US"},
        {"ticker": "PXD", "exchange": "US"},
        {"ticker": "OXY", "exchange": "US"}
      ]
    },
    {
      "id": 8,
      "name": "China Tech",
      "color": "#DC2626",
      "stocks": [
        {"ticker": "BABA", "exchange": "US"},
        {"ticker": "9988", "exchange": "HK"},
        {"ticker": "JD", "exchange": "US"},
        {"ticker": "PDD", "exchange": "US"},
        {"ticker": "BIDU", "exchange": "US"},
        {"ticker": "NTES", "exchange": "US"},
        {"ticker": "TME", "exchange": "US"}
      ]
    },
    {
      "id": 9,
      "name": "European Leaders",
      "color": "#0EA5E9",
      "stocks": [
        {"ticker": "ASML", "exchange": "AS"},
        {"ticker": "SAP", "exchange": "XETRA"},
        {"ticker": "NVO", "exchange": "US"},
        {"ticker": "MC", "exchange": "PA"},
        {"ticker": "OR", "exchange": "PA"},
        {"ticker": "SIE", "exchange": "XETRA"}
      ]
    },
    {
      "id": 10,
      "name": "Consumer & Retail",
      "color": "#84CC16",
      "stocks": [
        {"ticker": "AMZN", "exchange": "US"},
        {"ticker": "WMT", "exchange": "US"},
        {"ticker": "COST", "exchange": "US"},
        {"ticker": "HD", "exchange": "US"},
        {"ticker": "TGT", "exchange": "US"},
        {"ticker": "NKE", "exchange": "US"},
        {"ticker": "SBUX", "exchange": "US"},
        {"ticker": "MCD", "exchange": "US"}
      ]
    }
  ]
}
```

---

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
**Goal**: Core infrastructure and basic data flow

1. **Project Setup**
   - Create project structure
   - Setup virtual environment
   - Install dependencies
   - Configure logging

2. **Database Layer**
   - Implement DuckDB schema
   - Create CacheManager class
   - Implement cache read/write operations

3. **EODHD Provider**
   - Implement EODHDProvider class
   - Daily prices endpoint
   - Company info endpoint
   - Basic error handling and rate limiting

4. **Data Manager**
   - Implement DataManager with single provider
   - Smart caching logic
   - Missing data range detection

5. **Basic UI Shell**
   - Main window with menu bar
   - Status bar with connection status
   - Settings dialog for API key configuration

**Deliverable**: Can fetch and cache daily prices for any stock

### Phase 2: Core Visualizations (Week 3-4)
**Goal**: Main interactive visualizations working

1. **Market Treemap**
   - Squarify algorithm for treemap layout
   - Color mapping based on performance
   - Click-to-select interaction
   - Hover tooltips

2. **Stock Chart**
   - Candlestick chart with pyqtgraph
   - Volume bars
   - Basic indicators: SMA, EMA
   - Time period selector

3. **Watchlist Widget**
   - Create/delete watchlists
   - Add/remove stocks
   - Sortable table view
   - Persistence in database

4. **Category Management**
   - Load default categories
   - Category editor dialog
   - Filter treemap by category

**Deliverable**: Visual market overview with drill-down to stock charts

### Phase 3: News & Sentiment (Week 5)
**Goal**: Integrated news feed with sentiment analysis

1. **EODHD News Integration**
   - Fetch news with built-in sentiment
   - Store in database
   - Incremental updates

2. **News Feed Widget**
   - Scrollable news list
   - Sentiment color coding
   - Filter by stock/category
   - Click to open in browser

3. **Local FinBERT Analysis**
   - Setup FinBERT model
   - Analyze headlines locally
   - Ensemble scoring (EODHD + FinBERT)

4. **Sentiment Gauge Widget**
   - Visual dial gauge
   - Daily sentiment trend chart

**Deliverable**: News feed with enhanced sentiment analysis

### Phase 4: Advanced Features (Week 6-7)
**Goal**: Comparison tools, screener, additional data

1. **Comparison Chart Widget**
   - Multi-stock normalized chart
   - Performance metrics table
   - Correlation display

2. **Stock Screener**
   - Filter criteria UI
   - Query builder
   - Results display
   - Save/load profiles

3. **Fundamentals Display**
   - Fetch EODHD fundamentals
   - Key metrics display
   - Historical financials chart

4. **Intraday Data**
   - Intraday price fetching
   - Intraday chart option
   - Real-time updates (polling)

**Deliverable**: Full-featured analysis platform

### Phase 5: Backtesting Framework (Week 8-9)
**Goal**: RL-ready backtesting engine

1. **Trading Environment**
   - Gymnasium-compatible environment
   - State vector: prices + indicators + sentiment
   - Action space: buy/sell/hold
   - Reward function options

2. **Basic Strategies**
   - Moving average crossover
   - RSI-based strategy
   - Sentiment-based strategy

3. **Backtest Engine**
   - Run backtests
   - Calculate metrics
   - Store results in database

4. **Backtest Dashboard**
   - Strategy selector
   - Parameter configuration
   - Results visualization
   - Trade list

**Deliverable**: Working backtesting with example strategies

### Phase 6: RL Integration (Week 10-11)
**Goal**: Train and deploy RL agents

1. **RL Agent Wrappers**
   - PPO agent wrapper
   - A2C agent wrapper
   - DQN agent wrapper

2. **Training Pipeline**
   - Training configuration
   - Progress monitoring
   - Model checkpointing

3. **Agent Evaluation**
   - Backtest trained agents
   - Compare with baseline strategies

4. **Integration**
   - Use trained models for signals
   - Display in UI

**Deliverable**: Complete RL backtesting system

### Phase 7: Polish & Extensions (Week 12+)
**Goal**: Production-ready application

1. **Additional Providers**
   - Polygon.io integration
   - AKShare for China
   - Finnhub for social sentiment

2. **Performance Optimization**
   - Background data updates
   - Lazy loading
   - Memory optimization

3. **Export Features**
   - Export charts as images
   - Export data as CSV
   - Report generation

4. **Testing & Documentation**
   - Unit tests
   - Integration tests
   - User documentation

---

## Key Interactions & Workflows

### Workflow 1: Morning Market Review
1. Launch app → Treemap shows overnight changes
2. Color indicates: Green (up), Red (down)
3. Box size = market cap
4. Click "AI" category filter → See only AI stocks
5. Click NVDA → Right panel shows chart + metrics
6. Check sentiment gauge → Quick read on market mood
7. Scan news feed for overnight developments

### Workflow 2: Stock Deep Dive
1. Double-click stock in treemap → Opens dedicated window
2. See candlestick chart with volume
3. Add indicators: RSI, MACD, Bollinger
4. Switch to fundamentals tab → See P/E, revenue growth
5. Check news history → Understand recent moves
6. Compare with competitors → Add AMD, INTC to comparison

### Workflow 3: Run Backtest
1. Click Backtest tab
2. Select strategy: "SMA Crossover"
3. Configure: Fast MA = 10, Slow MA = 50
4. Select stocks: AI category
5. Date range: 2023-01-01 to 2025-01-01
6. Click "Run Backtest"
7. View equity curve, metrics, trade list
8. Save configuration for later

### Workflow 4: Find Opportunities (Screener)
1. Open Screener
2. Add filters:
   - Market cap > $10B
   - RSI < 30 (oversold)
   - Sentiment > 0.5 (positive news)
   - 1-week performance < -5% (recent dip)
3. Run screen
4. Review results
5. Add promising stocks to watchlist

---

## Configuration File (settings.yaml)

```yaml
# API Keys (can also use environment variables)
api_keys:
  eodhd: "${EODHD_API_KEY}"
  polygon: "${POLYGON_API_KEY}"  # Optional
  finnhub: "${FINNHUB_API_KEY}"  # Optional

# Data settings
data:
  cache_dir: "~/.investment_tool/cache"
  database_path: "~/.investment_tool/data.duckdb"
  max_cache_age_days: 7
  auto_refresh_interval_minutes: 15

# Provider priorities
providers:
  price_data:
    - eodhd
    - polygon
  fundamentals:
    - eodhd
  news:
    - eodhd
  social_sentiment:
    - finnhub
    - eodhd

# UI settings
ui:
  theme: "dark"  # dark or light
  default_chart_type: "candlestick"
  default_timeframe: "1D"
  treemap_color_scale:
    min_color: "#EF4444"  # Red for negative
    mid_color: "#FFFFFF"  # White for flat
    max_color: "#22C55E"  # Green for positive
    min_value: -5  # Percentage
    max_value: 5

# Analysis settings
analysis:
  sentiment:
    use_finbert: true
    finbert_model: "ProsusAI/finbert"
    ensemble_weights:
      eodhd: 0.4
      finbert: 0.6
  
  indicators:
    default_sma_periods: [20, 50, 200]
    default_ema_periods: [12, 26]
    rsi_period: 14
    macd_fast: 12
    macd_slow: 26
    macd_signal: 9

# Backtesting settings
backtesting:
  default_initial_capital: 100000
  commission_per_trade: 0.001  # 0.1%
  slippage: 0.0005  # 0.05%

# Logging
logging:
  level: "INFO"
  file: "~/.investment_tool/logs/app.log"
  max_size_mb: 10
  backup_count: 5
```

---

## Requirements.txt

```
# Core GUI
PySide6>=6.6.0
pyqtgraph>=0.13.0

# Data & Analysis
pandas>=2.0.0
numpy>=1.24.0
duckdb>=0.9.0
pydantic>=2.0.0
pyyaml>=6.0

# Visualization
matplotlib>=3.7.0
mplfinance>=0.12.0
squarify>=0.4.3

# HTTP & API
requests>=2.31.0
aiohttp>=3.9.0
websockets>=12.0

# Financial Analysis
statsmodels>=0.14.0
arch>=6.0.0
PyPortfolioOpt>=1.5.0
empyrical>=0.5.5
ta>=0.11.0

# Machine Learning
torch>=2.0.0
transformers>=4.35.0
stable-baselines3>=2.2.0
gymnasium>=0.29.0

# NLP & Transcription
faster-whisper>=1.0.0

# Utilities
python-dotenv>=1.0.0
loguru>=0.7.0
tqdm>=4.66.0

# Development
pytest>=7.4.0
pytest-qt>=4.2.0
black>=23.0.0
isort>=5.12.0
mypy>=1.7.0
```

---

## Getting Started Commands

```bash
# Create project directory
mkdir investment_tool
cd investment_tool

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Create directory structure
mkdir -p config data/providers analysis/sentiment analysis/technical analysis/fundamental analysis/portfolio backtesting/environments backtesting/agents backtesting/strategies ui/widgets ui/dialogs ui/styles utils resources/icons tests

# Create __init__.py files
find . -type d -name "*.py" -prune -o -type d -print | while read dir; do
    touch "$dir/__init__.py" 2>/dev/null
done

# Set up environment variables
echo "EODHD_API_KEY=your_api_key_here" > .env

# Run the application (once implemented)
python main.py
```

---

## Notes for Claude CLI

When implementing this project:

1. **Start with Phase 1** - Get the foundation solid before adding features
2. **Test each component** - Create simple test scripts as you build
3. **Use type hints** - Makes the code self-documenting
4. **Follow the provider pattern** - All data sources go through providers
5. **Cache aggressively** - Minimize API calls
6. **Keep UI responsive** - Use background threads for data fetching
7. **Commit frequently** - After each working feature

The treemap visualization is the core differentiator - spend time making it smooth and interactive. Use pyqtgraph's ScatterPlotItem or custom QGraphicsItems for performance.

For the RL backtesting, start with simple strategies before jumping to neural networks. The gym environment design is critical - get that right first.

---

## Implementation Progress (Updated Feb 3, 2026)

### Completed Features

#### Phase 1: Foundation ✅
- Project structure created with all directories
- DuckDB database schema implemented
- EODHD provider fully functional
- DataManager with caching and provider fallback
- Basic UI shell with menu bar and status bar
- Settings dialog for API key configuration

#### Phase 2: Core Visualizations ✅
- **Market Treemap**: Fully interactive with:
  - Color-coded performance (red/green)
  - Box size by market cap
  - Click to select, right-click context menu
  - Period selector: 1D, 1W, 1M, 3M, 6M, YTD, 1Y, 2Y, 5Y
  - Filter by category or market cap tier
  - "Add to Watchlist" context menu option

- **Stock Chart**: Candlestick chart with:
  - Chart type selector (Candlestick/Line)
  - **Measure Tool**: Drag to draw rectangle showing:
    - Price range (high/low)
    - Price difference ($) and percentage
    - Time span (days or hours)
    - 30% alpha fill with color matching change direction
  - Period synced with treemap selector
  - Indicators button (placeholder)

- **Watchlist Widget**: Fully functional with:
  - Multiple watchlists (tabs)
  - Columns: Ticker | Open | Price | Change | Change % | P/E | Volume
  - **Period-aware data fetching**:
    - 1D: Intraday data for current price, prev day close for change
    - 1W+: Daily data with live price, change from period open to current
  - Add stocks via search dialog or treemap context menu
  - Remove via context menu
  - Sortable columns

- **Category Management**: Working with 10 default categories

#### Key Metrics Panel ✅
Reorganized into **3-column layout**:

| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Price | 52W High | Market Cap |
| Change | 52W Low | P/E Ratio |
| | Avg Volume | |

- **Avg Volume**: Calculated based on selected period (not fixed 52W)
- **52W High/Low**: Always uses 52-week data
- Updates when stock selected and when period changes

#### Phase 3: News & Sentiment ✅
- **News Feed Widget**:
  - Scrollable list with sentiment color coding
  - Shows title, source, date, and sentiment polarity
  - Loads news from data server cache (cache-only, no direct API calls)
  - Refreshes when stock selection changes

- **Sentiment Analysis Widget**:
  - Shows positive/negative/neutral percentages
  - Visual sentiment gauge with polarity score
  - Aggregates from news articles for selected stock

### Data Server Architecture ✅

A separate caching proxy server sits between the app and EODHD API:

```
investment_tool → data_server (FastAPI) → EODHD API
                     ↓
              PostgreSQL cache
```

#### Data Server Features
- **Transparent caching**: All EODHD calls cached in PostgreSQL
- **Background workers**: Proactive updates for tracked stocks
- **WebSocket push**: Real-time notifications (price/news updates)
- **Server status endpoint**: Tracks EODHD API call statistics

#### News Caching System (Feb 3, 2026)
- **Background worker** fetches news for all tracked stocks:
  - Runs on startup and every 15 minutes
  - For each stock, fetches from newest date in DB to today
  - Fetches 100 articles per stock, processes asynchronously
- **App reads from cache only**: No direct EODHD calls for news
- Efficient incremental updates (only fetches new articles)

#### Intraday Caching (Feb 3, 2026)
- **Dynamic TTL** based on data age:
  - Historical intraday: 24-hour cache (won't change)
  - Today's intraday: 60-second cache (may still update)
- **is_cache_valid()** now checks both `expires_at` and `last_fetched` against `max_age_seconds`
- No duplicate EODHD calls when switching stocks in 1D mode

### Key Implementation Details

#### Period Synchronization
All views sync to treemap's period selector:
```
treemap.period_changed → main_window._on_treemap_period_changed()
  → stock_chart.set_period(period)
  → watchlist_widget.set_period(period)
  → Refresh all data
```

#### Initialization Order (Important!)
In `_initialize_data()`:
1. `set_data_manager()` FIRST
2. `set_cache()` SECOND (triggers refresh which needs data_manager)
3. `set_period()` then `refresh_all()`

#### Watchlist Data Modes
- **1D mode**: Uses intraday data, change = current price - prev day close
- **1W+ modes**:
  - Fetches period's daily data
  - Open = period's first day open price
  - Price = today's live price (real-time)
  - Change = current price - period open (true period performance)

#### Server Status Bar
Status bar shows: `Data Server: Connected | EODHD Calls: X`
- EODHD call count comes from data server (not local counting)
- Tracks actual external API usage, not local data server requests

#### Percentage Formatting (Important!)
- `format_percent(value)` expects decimal (0.05 = 5%)
- Do NOT multiply by 100 before calling - it does this internally

### Files Modified (Session Feb 3, 2026)

1. **data_server/data_server/api/routes.py**
   - Added `/server-status` endpoint with EODHD call stats
   - News endpoint returns cache-only data
   - Dynamic TTL for intraday caching (24h historical, 60s today)

2. **data_server/data_server/services/eodhd_client.py**
   - Added `_eodhd_call_count` counter
   - Added `get_eodhd_stats()` function

3. **data_server/data_server/workers/news_worker.py**
   - Rewritten for async news fetching
   - Fetches from newest date in DB to today (not oldest)
   - Uses `asyncio.gather` for parallel processing

4. **data_server/data_server/db/cache.py**
   - Added `get_newest_news_date_for_ticker()` using `func.max()`
   - Fixed `is_cache_valid()` to check `last_fetched` vs `max_age_seconds`

5. **investment_tool/ui/widgets/watchlist.py**
   - Fixed 1W+ periods: uses live price, change from period open
   - Added `get_live_price()` call for current value

6. **investment_tool/ui/main_window.py**
   - Status bar fetches EODHD stats from data server
   - Updated status format: "Data Server: Connected | EODHD Calls: X"

7. **investment_tool/data/providers/eodhd.py**
   - Added `get_server_status()` method

8. **investment_tool/data/manager.py**
   - Added `get_server_status()` to expose server status

### Remaining Phases

#### Phase 4-7: Not Started
- Comparison Chart
- Stock Screener
- Fundamentals Display
- Backtesting Framework
- RL Integration

### Running the Application

#### Step 1: Start the Data Server (Docker) - MUST BE RUNNING FIRST
```bash
cd /Users/jmahe/projects/python/finance/finalyze/data_server
docker compose up -d
```
Verify it's running:
```bash
docker compose ps                      # Should show data-server as "running"
docker compose logs -f data-server     # Should show "Uvicorn running on http://0.0.0.0:8000"
```

#### Step 2: Start the Investment Tool App
**IMPORTANT**: Must run from `finalyze/` directory, NOT from `investment_tool/`
```bash
cd /Users/jmahe/projects/python/finance/finalyze
source investment_tool/.venv/bin/activate
python -m investment_tool.main
```

#### Stop Data Server
```bash
cd /Users/jmahe/projects/python/finance/finalyze/data_server
docker compose down
```

### Database Locations
- Config: `~/.investment_tool/settings.yaml`
- Database: `~/.investment_tool/data.duckdb`
- Logs: `~/.investment_tool/logs/app.log`

### GitHub Repository
https://github.com/mahe7998/python.git

### Known Issues
- PXD ticker returns "Data not found" (delisted stock)
- Intraday data may be None on weekends/after hours (falls back to daily)
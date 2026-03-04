# Investment Tracking & Analysis Tool - Project Context

## Overview
A desktop application for tracking and analyzing stock investments, built with Python and PySide6 (Qt6). The app provides real-time market data visualization, watchlist management, quarterly financials with yfinance cross-validation, ETF-specific views, news feed with sentiment analysis, and technical analysis tools.

## Tech Stack
- **UI Framework**: PySide6 (Qt6)
- **Charting**: pyqtgraph
- **Data Server**: FastAPI + PostgreSQL + SQLAlchemy async (caching proxy, runs in Docker)
- **Data Providers**: EODHD API (primary), yfinance (fallback/validation), SEC EDGAR (shares outstanding)
- **Package Manager**: uv
- **Key Design Principle**: Frontend NEVER calls EODHD/yfinance directly — all requests go through data server for caching

## Running the Application

### Step 1: Start the Data Server (Docker) - MUST BE RUNNING FIRST
```bash
cd /Users/jmahe/projects/python/finance/finalyze/data_server
docker compose up -d
```
Verify it's running:
```bash
docker compose ps                      # Should show data-server as "running"
docker compose logs -f data-server     # Should show "Uvicorn running on http://0.0.0.0:8000"
```

### Step 2: Start the Investment Tool App
```bash
cd /Users/jmahe/projects/python/finance/finalyze
investment_tool/.venv/bin/python -m investment_tool.main
```

### Stop Data Server
```bash
cd /Users/jmahe/projects/python/finance/finalyze/data_server
docker compose down
```

## Architecture

```
┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────┐
│  investment_tool    │      │    data_server      │      │   EODHD     │
│  (PySide6 App)      │─────▶│  (FastAPI + Docker) │─────▶│    API      │
│                     │      │         │           │      └─────────────┘
│  - UI widgets       │      │         ▼           │      ┌─────────────┐
│  - Analysis         │      │    PostgreSQL       │      │  yfinance   │
│                     │      │         │           │─────▶│  (fallback) │
└─────────────────────┘      │         ▼           │      └─────────────┘
                             │   Background        │      ┌─────────────┐
                             │   Workers           │─────▶│ SEC EDGAR   │
                             └─────────────────────┘      └─────────────┘
```

### Data Flow
1. App requests data from `DataManager` using **batch endpoints** (never per-stock loops)
2. DataManager routes through `EODHDProvider` to data server (port 8000)
3. Data server checks PostgreSQL cache
4. If not cached, fetches from EODHD API (with yfinance/SEC fallbacks)
5. Response cached in PostgreSQL
6. LivePrice table kept in sync with daily closes via scheduled worker (21:45 UTC) and startup DB refresh

### Performance Architecture
- **Startup (<1s)**: Only loads treemap prices + watchlist data using batch endpoints
- **Lazy loading**: News, financials, fundamentals fetched on-demand when a stock is selected
- **Batch endpoints**: `/live-prices` (all cached prices), `/batch/daily-changes` (period changes), `/batch/highlights` (company data for treemap/watchlist)
- **No external API calls at startup**: LivePrice synced from daily_prices DB table

## Project Structure

```
finalyze/
├── investment_tool/                  # Desktop app (PySide6)
│   ├── main.py                       # Entry point
│   ├── mcp_server.py                 # MCP server integration
│   ├── config/
│   │   ├── settings.py               # AppConfig (API keys, data, UI settings)
│   │   └── categories.py             # Stock categories with color coding
│   ├── data/
│   │   ├── manager.py                # DataManager - main data interface
│   │   ├── models.py                 # Data models (PriceBar, CompanyInfo, etc.)
│   │   ├── storage.py                # UserDataStore (watchlists, categories)
│   │   └── providers/
│   │       ├── base.py               # Abstract DataProviderBase
│   │       └── eodhd.py              # EODHD provider (calls data server)
│   ├── analysis/
│   │   └── sentiment/aggregator.py   # Daily sentiment aggregation
│   ├── ui/
│   │   ├── main_window.py            # Main window (treemap, chart, metrics, tabs)
│   │   ├── control_server.py         # HTTP control server (port 18765)
│   │   ├── styles/theme.py           # Dark theme stylesheet
│   │   ├── widgets/
│   │   │   ├── market_treemap.py     # Interactive market treemap (left panel)
│   │   │   ├── stock_chart.py        # Candlestick chart + volume + measure tool
│   │   │   ├── watchlist.py          # Multi-watchlist with auto-refresh
│   │   │   ├── quarterly_financials.py # Quarterly bar charts + earnings date
│   │   │   ├── fundamentals_overview.py # Balance sheet, income, cash flow
│   │   │   ├── etf_overview.py       # ETF holdings, performance, allocations
│   │   │   ├── news_feed.py          # News articles with sentiment + search
│   │   │   └── sentiment_gauge.py    # Sentiment dial + trend chart
│   │   └── dialogs/
│   │       ├── add_stock_dialog.py   # Stock search and add
│   │       ├── category_dialog.py    # Category management
│   │       ├── discrepancy_dialog.py # EODHD vs yfinance data review
│   │       └── settings_dialog.py    # App settings
│   └── utils/
│       ├── helpers.py                # Formatting, date ranges, market hours
│       ├── exchange_hours.py         # Exchange trading session hours
│       ├── logging.py                # Logging setup
│       └── threading.py              # Threading/async utilities
│
└── data_server/                      # Caching proxy (Docker)
    ├── docker-compose.yml            # Docker config (port 8000)
    ├── test_cache.py                 # API endpoint tests
    └── data_server/
        ├── main.py                   # FastAPI entry
        ├── config.py                 # Server configuration
        ├── api/
        │   ├── routes.py             # REST endpoints (20+)
        │   └── tracking.py           # Stock tracking + 5Y prefetch
        ├── db/
        │   ├── models.py             # SQLAlchemy ORM models
        │   ├── database.py           # Async session factory + migrations
        │   └── cache.py              # PostgreSQL cache operations
        ├── services/
        │   ├── eodhd_client.py       # EODHD API client
        │   ├── yfinance_client.py    # yfinance fallback (financials, earnings, search)
        │   └── sec_edgar.py          # SEC EDGAR (shares outstanding)
        ├── workers/
        │   ├── scheduler.py          # APScheduler (prices 15s, news 15min)
        │   ├── price_worker.py       # Live price + intraday bar aggregation
        │   └── news_worker.py        # News fetcher (EODHD + yfinance fallback)
        └── ws/
            ├── manager.py            # WebSocket connection manager
            └── handlers.py           # WebSocket event handlers
```

## Key Features

### UI Components
| Component | Location | Description |
|-----------|----------|-------------|
| Market Treemap | Left panel | Stocks sized by market cap, colored by change % |
| Stock Chart | Right panel | Candlestick/line chart with measure tool, volume hover |
| Key Metrics | Right panel | Price, Change, Prev Close, Day OHLC, 52W High/Low, Market Cap, P/E, Avg Volume |
| Watchlist | Bottom tab | Multi-tab with auto-refresh (60s), tab reorder/rename, period-aware, batch-only data fetching |
| Quarterly Financials | Bottom tab | Grouped bar charts, metric selector, earnings date, yfinance cross-validation |
| Fundamentals Overview | Bottom tab | Balance sheet, income statement, cash flow grids |
| ETF Overview | Bottom tab (ETFs) | Fund info, performance, top 10 holdings, sector/geographic allocation charts |
| News Feed | Bottom tab | Sentiment-colored news with search/date filters, floating summary |
| Sentiment Gauge | Right panel | Polarity dial + daily trend chart |

### Period Selector
All views sync to treemap's period: 1D, 1W, 1M, 3M, 6M, YTD, 1Y, 2Y, 5Y
- **1D mode**: Intraday data, change = current - prev day close, shows Day OHLC + Prev Close
- **1W+ modes**: Daily data, change = current - period open
- **Loading feedback**: Metrics show "•••", chart clears, wait cursor during period switch

### ETF Detection
- Asset type detected from EODHD `General.Type` field
- ETFs show: Chart | ETF Overview (instead of Chart | Financials | Fundamentals)
- ETF data: holdings, sector weights, geographic allocation, performance stored as JSON

### Data Quality
- **yfinance cross-validation**: Quarterly financials compared between EODHD and yfinance; discrepancies >5% trigger review dialog
- **Data source tracking**: Each quarterly record tagged as `eodhd` or `yfinance`; overridden records skip future comparisons
- **Dynamic market cap**: Always computed as `shares_outstanding × current_price` (never stale fundamentals)
- **Consistent pricing**: All periods use intraday data for current price (same source)
- **Volume**: Watchlist uses daily EOD volume (intraday volume unreliable from EODHD)

### Data Server
| Feature | Description |
|---------|-------------|
| News caching | Background worker fetches every 15 min |
| Intraday caching | Dynamic TTL (24h historical, 60s today) |
| Historical prefetch | Auto-fetches 5Y daily data when stock added to tracking |
| Earnings calendar | EODHD + yfinance fallback for next/last earnings |
| Live prices | `/live-prices` batch endpoint, 15s refresh via background worker |
| Batch daily changes | `/batch/daily-changes` — period price changes for multiple symbols |
| Batch highlights | `/batch/highlights` — company data (P/E, market cap, sector) for multiple symbols in one DB query |
| LivePrice sync | Scheduled worker (21:45 UTC) syncs LivePrice with daily closes after market close; startup refreshes from DB (no API calls) |
| Server status | `/server-status` returns EODHD API call count |
| FX conversion | `/forex/rates/{currency}` with server-side market cap conversion |

## Important Implementation Notes

### Stock Split Handling
```python
# Use adjusted_close for historical start price to account for splits
start_price = prices[0].get("adjusted_close") or prices[0].get("close")
end_price = prices[-1].get("close")  # Current price (not adjusted)
```

### Intraday Data Interval
```python
# ALWAYS use 1m interval - EODHD 5m data has NULL gaps for many stocks
intraday = data_manager.get_intraday_prices(ticker, exchange, "1m", ...)
```

### Percentage Formatting
```python
# format_percent() expects decimal (0.05 = 5%)
format_percent(0.05)  # Returns "+5.00%"
# Do NOT multiply by 100 before calling
```

### Market Cap
```python
# NEVER use company.market_cap (stale from fundamentals)
# Always compute dynamically:
market_cap = shares_outstanding * current_price_usd
```

### Watchlist Data (Batch-Only)
```python
# Watchlist uses ONLY batch calls — zero per-stock API requests
all_live = data_manager.get_all_live_prices()       # 1 call for all prices
all_highlights = data_manager.get_batch_highlights(symbols)  # 1 call for P/E, market cap
batch_changes = data_manager.get_batch_daily_changes(symbols, start, end)  # 1 call for period changes
# Volume comes from live prices (no separate fetch)
```

### QThread Safety
```python
# Always wait for previous QThread worker before starting a new one
# QThread destroyed while running causes SIGABRT crash on macOS
if worker and worker.isRunning():
    worker.wait(5000)
```

### Period Change UI Feedback
```python
# Use QTimer.singleShot(200ms) to defer heavy work after combo box repaints
# macOS Cocoa combo needs ~200ms to fully render before blocking the UI thread
QTimer.singleShot(200, lambda: self._do_period_update(period))
```

## File Locations
- App config: `~/.investment_tool/settings.yaml`
- App logs: `~/.investment_tool/logs/app.log`
- Data server logs: `docker compose logs data-server`
- PostgreSQL data: Docker volume `data_server_postgres_data`

## Performance Optimizations (Completed)
- **Sub-second startup**: Treemap + watchlists load in <1s using batch endpoints (down from ~90s with per-stock API calls)
- **Batch-only watchlist**: Uses `get_all_live_prices()` + `get_batch_highlights()` + `get_batch_daily_changes()` — zero per-stock calls
- **Batch treemap**: Single `get_batch_highlights()` call replaces N×`get_company_info()` + N×`get_fundamentals()` loops
- **Lazy loading**: News, financials, fundamentals only fetched when a stock is selected (not at startup)
- **No direct EODHD/yfinance calls**: Frontend routes everything through data server; `.env` loading fixed to always find `DATA_SERVER_URL`
- **LivePrice never stale**: Synced with daily_prices DB on startup (no API calls) and via scheduled worker after market close

## Known Issues
- PXD ticker returns "Data not found" (delisted stock)
- Intraday data may be None on weekends/after hours (falls back to daily)
- EODHD 5m interval data has NULL gaps for many stocks — use 1m interval instead
- macOS Cocoa combo box needs 200ms QTimer delay for repaint before heavy work

## Remaining Work (Not Started)
- Comparison Chart widget
- Stock Screener
- Backtesting Framework
- RL Integration

## References
- Full project plan: `Investment Tracking & Analysis Tool - Project Plan.md`
- GitHub: https://github.com/mahe7998/python.git

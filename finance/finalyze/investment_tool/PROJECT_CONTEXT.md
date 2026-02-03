# Investment Tracking & Analysis Tool - Project Context

## Overview
A desktop application for tracking and analyzing stock investments, built with Python and PySide6 (Qt6). The app provides real-time market data visualization, watchlist management, and technical analysis tools.

## Tech Stack
- **UI Framework**: PySide6 (Qt6)
- **Charting**: pyqtgraph
- **Local Database**: DuckDB (client-side cache)
- **Data Server**: FastAPI + PostgreSQL (caching proxy)
- **Data Provider**: EODHD API (via data server)
- **Package Manager**: uv

## Running the Application

### Step 1: Start the Data Server (Docker)
```bash
cd /Users/jmahe/projects/python/finance/finalyze/data_server
docker compose up -d
```
Verify it's running: `docker compose logs -f data-server`
Wait for: `INFO: Uvicorn running on http://0.0.0.0:8765`

### Step 2: Start the Investment Tool App (Terminal)
```bash
cd /Users/jmahe/projects/python/finance/finalyze
source ~/.zshrc  # IMPORTANT: Always source this first
source investment_tool/.venv/bin/activate
python -m investment_tool.main
```

### Quick Restart (App Only)
If data server Docker container is already running:
```bash
cd /Users/jmahe/projects/python/finance/finalyze/investment_tool
source .venv/bin/activate
python -m investment_tool.main
```

### Stop Data Server
```bash
cd /Users/jmahe/projects/python/finance/finalyze/data_server
docker compose down
```

## Project Structure
```
investment_tool/
├── main.py                 # Application entry point
├── config/
│   ├── settings.py         # App configuration (AppConfig)
│   └── categories.py       # Stock category management
├── data/
│   ├── manager.py          # DataManager - main data interface
│   ├── cache.py            # DuckDB cache (CacheManager)
│   ├── models.py           # Data models (Company, Watchlist, etc.)
│   └── providers/
│       ├── base.py         # Provider interface
│       └── eodhd.py        # EODHD API implementation
├── ui/
│   ├── main_window.py      # Main application window
│   ├── widgets/
│   │   ├── market_treemap.py  # Treemap visualization (left panel)
│   │   ├── stock_chart.py     # Price chart with candlesticks
│   │   └── watchlist.py       # Watchlist management (bottom tabs)
│   ├── dialogs/
│   │   ├── add_stock_dialog.py
│   │   ├── settings_dialog.py
│   │   └── category_dialog.py
│   └── styles/
│       └── theme.py        # UI styling
├── utils/
│   └── helpers.py          # Utility functions (format_percent, get_date_range, etc.)
├── analysis/               # Placeholder for future analysis modules
├── backtesting/            # Placeholder for backtesting
└── tests/
```

## Key Features

### 1. Market Treemap (Left Panel)
- Visual representation of stocks by market cap
- Color-coded by price change percentage
- Period selector: 1D, 1W, 1M, 3M, 6M, YTD, 1Y, 2Y, 5Y
- Filter by category or market cap
- Right-click context menu to add to watchlist

### 2. Stock Chart (Right Panel)
- Candlestick and line chart types
- **Measure Tool**: Drag to draw rectangle showing:
  - Price range (high/low)
  - Price difference and percentage
  - Time span (days/hours)
  - 30% alpha fill
- Period controlled by treemap selector
- Technical indicators support

### 3. Key Metrics Panel (3-column layout)
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Price | 52W High | Market Cap |
| Change | 52W Low | P/E Ratio |
| | Avg Volume | |

- **Avg Volume**: Calculated based on selected period (not 52W)
- **52W High/Low**: Always uses 52-week data

### 4. Watchlist (Bottom Tab)
Columns: Ticker | Open | Price | Change | Change % | P/E | Volume

- **Period-aware data fetching**:
  - 1D: Uses intraday data for current price, previous day's close for change calculation
  - 1W+: Uses daily data with live price, change calculated from period open to current price
- P/E ratio fetched from company info
- Add stocks via search dialog or treemap context menu

### 5. News Feed (Bottom Tab)
- Scrollable list with sentiment color coding (green/red/yellow)
- Shows title, source, date, and polarity score
- **Cache-only reads**: Data fetched by data server background worker
- Refreshes when stock selection changes

### 6. Sentiment Analysis Widget
- Positive/negative/neutral percentage bars
- Overall polarity gauge
- Aggregates sentiment from news articles

## Data Server Architecture

The app uses a separate data server as a caching proxy for EODHD API:

```
investment_tool (PySide6) → data_server (FastAPI) → EODHD API
                                  ↓
                           PostgreSQL cache
```

### Key Features
- **Transparent caching**: All EODHD calls cached in PostgreSQL
- **Background workers**: Proactive news/price updates for tracked stocks
- **Server status endpoint**: `/server-status` returns EODHD API call count
- **WebSocket support**: Real-time push notifications

### News System
- **Background worker** runs on startup and every 15 minutes
- Fetches news from newest date in DB to today (incremental)
- App reads from cache only (no direct EODHD calls for news)

### Intraday Caching
- **Dynamic TTL**: 24h for historical data, 60s for today's data
- Prevents duplicate EODHD calls when switching stocks in 1D mode

### Status Bar
Shows: `Data Server: Connected | EODHD Calls: X`
- EODHD call count from data server (actual external API usage)

## Important Implementation Details

### Period Synchronization
All views sync to the treemap's period selector:
- `main_window._on_treemap_period_changed()` updates:
  - `stock_chart.set_period(period)`
  - `watchlist_widget.set_period(period)`
  - Refreshes all data

### Data Flow
1. `DataManager` is the main interface for all data
2. Checks `CacheManager` (DuckDB) first
3. Falls back to EODHD API if not cached
4. Caches API responses for future use

### Intraday vs Daily Data
- `is_intraday_period(period)` returns True only for "1D"
- `get_last_trading_day_hours(exchange)` returns market open/close times
- For 1D: Change % = (current_price - prev_day_close) / prev_day_close

### Percentage Formatting
- `format_percent(value)` expects decimal (0.05 = 5%)
- Do NOT multiply by 100 before calling format_percent

## Database Location
- Config: `~/.investment_tool/settings.yaml`
- Database: `~/.investment_tool/data.duckdb`
- Logs: `~/.investment_tool/logs/app.log`

## Recent Changes (Session Feb 3, 2026)
1. **News Feed Widget**: Displays news with sentiment color coding
2. **Sentiment Analysis Widget**: Shows polarity gauge and percentages
3. **News caching system**: Background worker fetches news proactively
4. **Server status endpoint**: Tracks EODHD API call count
5. **Watchlist 1W+ fix**: Uses live price, change from period open
6. **Intraday caching fix**: Dynamic TTL (24h historical, 60s today)
7. **is_cache_valid fix**: Now checks both expires_at and last_fetched

## Previous Changes (Session Feb 1, 2026)
1. Added interactive Measure tool to stock chart
2. Made watchlist period-aware with correct change % calculation
3. Added Open and P/E columns to watchlist
4. Added 52W High/Low to Key Metrics
5. Changed Avg Volume to use selected period
6. Reorganized Key Metrics into 3-column layout
7. Fixed initialization order (data_manager before cache)

## Known Issues
- PXD ticker returns "Data not found" (delisted stock)
- Intraday data may be None on weekends/after hours (falls back to daily)

## Full Project Plan
For detailed specifications, database schema, UI wireframes, implementation phases, and future roadmap, see:
`/Users/jmahe/projects/python/finance/finalyze/Investment Tracking & Analysis Tool - Project Plan.md`

## GitHub Repository
https://github.com/mahe7998/python.git

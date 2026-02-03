# Investment Tracking & Analysis Tool - Project Context

## Overview
A desktop application for tracking and analyzing stock investments, built with Python and PySide6 (Qt6). The app provides real-time market data visualization, watchlist management, news feed with sentiment analysis, and technical analysis tools.

## Tech Stack
- **UI Framework**: PySide6 (Qt6)
- **Charting**: pyqtgraph
- **Local Database**: DuckDB (client-side cache)
- **Data Server**: FastAPI + PostgreSQL (caching proxy, runs in Docker)
- **Data Provider**: EODHD API (via data server)
- **Package Manager**: uv

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
**IMPORTANT**: Must run from `finalyze/` directory, NOT from `investment_tool/`
```bash
cd /Users/jmahe/projects/python/finance/finalyze
source investment_tool/.venv/bin/activate
python -m investment_tool.main
```

### Stop Data Server
```bash
cd /Users/jmahe/projects/python/finance/finalyze/data_server
docker compose down
```

### Test Data Server Cache
```bash
cd /Users/jmahe/projects/python/finance/finalyze/data_server
source .venv/bin/activate
python test_cache.py http://localhost:8000
```

## Architecture

```
┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────┐
│  investment_tool    │      │    data_server      │      │   EODHD     │
│  (PySide6 App)      │─────▶│  (FastAPI + Docker) │─────▶│    API      │
│                     │      │         │           │      └─────────────┘
│  - UI widgets       │      │         ▼           │
│  - DuckDB cache     │      │    PostgreSQL       │
└─────────────────────┘      └─────────────────────┘
```

### Data Flow
1. App requests data from `DataManager`
2. DataManager checks local DuckDB cache
3. If not cached, requests from data server (port 8000)
4. Data server checks PostgreSQL cache
5. If not cached, fetches from EODHD API
6. Response cached at both levels

## Project Structure

```
finalyze/
├── investment_tool/           # Desktop app (PySide6)
│   ├── main.py                # Entry point
│   ├── config/settings.py     # App configuration
│   ├── data/
│   │   ├── manager.py         # DataManager - main data interface
│   │   ├── cache.py           # DuckDB cache
│   │   └── providers/eodhd.py # EODHD provider (calls data server)
│   ├── ui/
│   │   ├── main_window.py     # Main window
│   │   └── widgets/
│   │       ├── market_treemap.py  # Left panel - stock treemap
│   │       ├── stock_chart.py     # Right panel - price chart
│   │       ├── watchlist.py       # Bottom tab - watchlist
│   │       ├── news_feed.py       # Bottom tab - news
│   │       └── sentiment_widget.py # Sentiment analysis
│   └── utils/helpers.py       # format_percent, get_date_range, etc.
│
└── data_server/               # Caching proxy (Docker)
    ├── docker-compose.yml     # Docker config (port 8000)
    ├── test_cache.py          # API endpoint tests
    └── data_server/
        ├── main.py            # FastAPI entry
        ├── api/routes.py      # REST endpoints
        ├── db/cache.py        # PostgreSQL cache operations
        ├── workers/
        │   ├── news_worker.py   # Background news fetcher
        │   └── price_worker.py  # Background price fetcher
        └── services/eodhd_client.py  # EODHD API client
```

## Key Features (Completed)

### UI Components
| Component | Location | Description |
|-----------|----------|-------------|
| Market Treemap | Left panel | Stocks sized by market cap, colored by change % |
| Stock Chart | Right panel | Candlestick/line chart with measure tool |
| Key Metrics | Right panel | Price, Change, 52W High/Low, Market Cap, P/E, Avg Volume |
| Watchlist | Bottom tab | Period-aware with live prices |
| News Feed | Bottom tab | Sentiment-colored news from cache |
| Sentiment | Bottom tab | Polarity gauge and percentages |

### Period Selector
All views sync to treemap's period: 1D, 1W, 1M, 3M, 6M, YTD, 1Y, 2Y, 5Y
- **1D mode**: Intraday data, change = current - prev day close
- **1W+ modes**: Daily data, live price, change = current - period open

### Data Server Features
- **News caching**: Background worker fetches every 15 min, app reads cache only
- **Intraday caching**: Dynamic TTL (24h historical, 60s today)
- **Server status**: `/server-status` returns EODHD API call count
- **Status bar**: Shows "Data Server: Connected | EODHD Calls: X"

## Important Implementation Notes

### Percentage Formatting
```python
# format_percent() expects decimal (0.05 = 5%)
format_percent(0.05)  # Returns "+5.00%"
# Do NOT multiply by 100 before calling
```

### Cache Validity Check
```python
# is_cache_valid() checks BOTH expires_at AND last_fetched vs max_age_seconds
# This allows dynamic TTL override for historical vs current data
```

### Watchlist Data Modes
```python
if period == "1D":
    # Intraday data, change from prev day close
    change = current_price - prev_day_close
else:
    # Daily data, live price, change from period open
    change = live_price - period_open_price
```

## File Locations
- App config: `~/.investment_tool/settings.yaml`
- Local DB: `~/.investment_tool/data.duckdb`
- App logs: `~/.investment_tool/logs/app.log`
- Data server logs: `docker compose logs data-server`

## Known Issues
- PXD ticker returns "Data not found" (delisted stock)
- Intraday data may be None on weekends/after hours (falls back to daily)

## Remaining Work (Not Started)
- Comparison Chart widget
- Stock Screener
- Fundamentals Display
- Backtesting Framework
- RL Integration

## References
- Full project plan: `Investment Tracking & Analysis Tool - Project Plan.md`
- GitHub: https://github.com/mahe7998/python.git

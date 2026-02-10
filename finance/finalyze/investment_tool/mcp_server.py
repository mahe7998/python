"""MCP server for the Investment Tool.

Exposes tools for UI control (via embedded HTTP control API) and
data queries (via data server). Uses stdio transport.

Usage:
    uv run python mcp_server.py

Environment variables:
    DATA_SERVER_URL: Data server URL (default: http://localhost:8000)
    CONTROL_API_URL: Qt app control API URL (default: http://localhost:18765)
"""

import json
import os
import sys
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

# Redirect logging to stderr (stdout is used for MCP JSON-RPC)
import logging

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("investment-mcp")

mcp = FastMCP("investment-tool")

DATA_SERVER_URL = os.getenv("DATA_SERVER_URL", "http://localhost:8000").rstrip("/")
CONTROL_API_URL = os.getenv("CONTROL_API_URL", "http://localhost:18765").rstrip("/")


def _control_get(path: str, timeout: int = 10) -> dict:
    """Make a GET request to the Qt control API."""
    resp = requests.get(f"{CONTROL_API_URL}{path}", timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _control_post(path: str, data: dict, timeout: int = 20) -> dict:
    """Make a POST request to the Qt control API."""
    resp = requests.post(f"{CONTROL_API_URL}{path}", json=data, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _data_get(path: str, params: dict | None = None, timeout: int = 30) -> Any:
    """Make a GET request to the data server API."""
    api_key = os.getenv("EODHD_API_KEY", "demo")
    if params is None:
        params = {}
    params.setdefault("api_token", api_key)
    params.setdefault("fmt", "json")
    resp = requests.get(f"{DATA_SERVER_URL}/api/{path}", params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# --- UI Control Tools ---


@mcp.tool()
def get_ui_state() -> str:
    """Get the current UI state of the investment tool.

    Returns the currently selected stock ticker, exchange, chart period, and filter.
    """
    try:
        state = _control_get("/state")
        return json.dumps(state, indent=2)
    except requests.ConnectionError:
        return "Error: Investment tool UI is not running. Start it first with: cd investment_tool && uv run python main.py"
    except Exception as e:
        return f"Error getting UI state: {e}"


@mcp.tool()
def select_stock(ticker: str, exchange: str = "US") -> str:
    """Select a stock in the investment tool UI.

    This changes the displayed chart, metrics, news, and financials to the specified stock.

    Args:
        ticker: Stock ticker symbol (e.g. NVDA, AAPL, MSFT)
        exchange: Exchange code (default: US)
    """
    try:
        result = _control_post("/select-stock", {"ticker": ticker, "exchange": exchange})
        return json.dumps(result, indent=2)
    except requests.ConnectionError:
        return "Error: Investment tool UI is not running."
    except Exception as e:
        return f"Error selecting stock: {e}"


@mcp.tool()
def set_period(period: str) -> str:
    """Change the chart time period in the investment tool UI.

    Args:
        period: Time period. Must be one of: 1D, 1W, 1M, 3M, 6M, 1Y, 5Y
    """
    valid = ("1D", "1W", "1M", "3M", "6M", "1Y", "5Y")
    if period not in valid:
        return f"Invalid period '{period}'. Must be one of: {', '.join(valid)}"

    try:
        result = _control_post("/set-period", {"period": period})
        return json.dumps(result, indent=2)
    except requests.ConnectionError:
        return "Error: Investment tool UI is not running."
    except Exception as e:
        return f"Error setting period: {e}"


# --- Data Query Tools ---


@mcp.tool()
def search_stocks(query: str, limit: int = 20) -> str:
    """Search for stocks by ticker symbol or company name.

    Args:
        query: Search query (ticker, company name, or ISIN)
        limit: Maximum number of results (default: 20)
    """
    try:
        import urllib.parse

        encoded = urllib.parse.quote(query)
        results = _data_get(f"search/{encoded}", {"limit": limit})
        if not results:
            return f"No results found for '{query}'"

        lines = []
        for r in results[:limit]:
            code = r.get("Code", "")
            name = r.get("Name", "")
            exch = r.get("Exchange", "")
            typ = r.get("Type", "")
            lines.append(f"{code}.{exch} - {name} ({typ})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error searching stocks: {e}"


@mcp.tool()
def get_fundamentals(ticker: str, exchange: str = "US") -> str:
    """Get company fundamentals including market cap, P/E ratio, earnings, and more.

    Args:
        ticker: Stock ticker symbol (e.g. NVDA, AAPL)
        exchange: Exchange code (default: US)
    """
    try:
        data = _data_get(f"fundamentals/{ticker}.{exchange}")
        if not data:
            return f"No fundamentals found for {ticker}.{exchange}"

        # Extract highlights if available (data server format)
        if "highlights" in data:
            h = data["highlights"]
            lines = [
                f"Company: {h.get('name', ticker)}",
                f"Sector: {h.get('sector', 'N/A')}",
                f"Industry: {h.get('industry', 'N/A')}",
                f"Market Cap: {h.get('market_cap', 'N/A')}",
                f"P/E Ratio: {h.get('pe_ratio', 'N/A')}",
                f"EPS: {h.get('eps', 'N/A')}",
                f"Dividend Yield: {h.get('dividend_yield', 'N/A')}",
                f"Currency: {h.get('currency', 'N/A')}",
            ]

            # Include quarterly financials if available
            if "quarterly_financials" in data:
                qf = data["quarterly_financials"]
                if qf:
                    lines.append("\nLatest Quarterly Financials:")
                    latest = list(qf.values())[0] if isinstance(qf, dict) else qf[0]
                    if isinstance(latest, dict):
                        for k, v in list(latest.items())[:10]:
                            lines.append(f"  {k}: {v}")

            return "\n".join(lines)
        elif "General" in data:
            # Direct EODHD format
            g = data.get("General", {})
            h = data.get("Highlights", {})
            lines = [
                f"Company: {g.get('Name', ticker)}",
                f"Sector: {g.get('Sector', 'N/A')}",
                f"Industry: {g.get('Industry', 'N/A')}",
                f"Market Cap: {h.get('MarketCapitalization', 'N/A')}",
                f"P/E Ratio: {h.get('PERatio', 'N/A')}",
                f"EPS: {h.get('EarningsShare', 'N/A')}",
                f"Dividend Yield: {h.get('DividendYield', 'N/A')}",
            ]
            return "\n".join(lines)
        else:
            return json.dumps(data, indent=2)
    except Exception as e:
        return f"Error getting fundamentals: {e}"


@mcp.tool()
def get_daily_prices(ticker: str, exchange: str = "US", days: int = 30) -> str:
    """Get historical daily prices for a stock.

    Returns date, open, high, low, close, adjusted_close, and volume.

    Args:
        ticker: Stock ticker symbol (e.g. NVDA, AAPL)
        exchange: Exchange code (default: US)
        days: Number of days of history (default: 30)
    """
    try:
        from datetime import date, timedelta

        end = date.today()
        start = end - timedelta(days=days)

        data = _data_get(
            f"eod/{ticker}.{exchange}",
            {"from": start.isoformat(), "to": end.isoformat()},
        )
        if not data:
            return f"No price data found for {ticker}.{exchange}"

        lines = [f"Daily prices for {ticker}.{exchange} (last {days} days):"]
        lines.append("Date        | Open    | High    | Low     | Close   | Volume")
        lines.append("-" * 70)

        for row in data[-20:]:  # Last 20 entries to keep output manageable
            d = row.get("date", "")
            o = row.get("open", 0)
            h = row.get("high", 0)
            lo = row.get("low", 0)
            c = row.get("close", 0)
            v = row.get("volume", 0)
            lines.append(f"{d} | {o:>7.2f} | {h:>7.2f} | {lo:>7.2f} | {c:>7.2f} | {v:>10,.0f}")

        if len(data) > 20:
            lines.append(f"... showing last 20 of {len(data)} records")

        return "\n".join(lines)
    except Exception as e:
        return f"Error getting daily prices: {e}"


@mcp.tool()
def get_news(ticker: str, limit: int = 10) -> str:
    """Get recent news articles for a stock with sentiment data.

    Args:
        ticker: Stock ticker symbol (e.g. NVDA, AAPL)
        limit: Maximum number of articles (default: 10)
    """
    try:
        data = _data_get("news", {"s": ticker, "limit": limit})
        if not data:
            return f"No news found for {ticker}"

        lines = [f"Recent news for {ticker}:"]
        for article in data[:limit]:
            title = article.get("title", "No title")
            source = article.get("source", "Unknown")
            pub_date = article.get("date", "")[:10]
            sentiment = article.get("sentiment", {})
            polarity = sentiment.get("polarity", "N/A") if sentiment else "N/A"
            link = article.get("link", "")

            lines.append(f"\n[{pub_date}] {title}")
            lines.append(f"  Source: {source} | Sentiment: {polarity}")
            if link:
                lines.append(f"  URL: {link}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error getting news: {e}"


@mcp.tool()
def get_live_price(ticker: str, exchange: str = "US") -> str:
    """Get the real-time or delayed quote for a stock.

    Returns current price, change, volume, and other real-time data.

    Args:
        ticker: Stock ticker symbol (e.g. NVDA, AAPL)
        exchange: Exchange code (default: US)
    """
    try:
        data = _data_get(f"real-time/{ticker}.{exchange}")
        if not data:
            return f"No live price available for {ticker}.{exchange}"

        price = data.get("close", "N/A")
        change = data.get("change", 0)
        change_p = data.get("change_p", 0)
        volume = data.get("volume", 0)
        prev_close = data.get("previousClose", "N/A")
        high = data.get("high", "N/A")
        low = data.get("low", "N/A")
        open_price = data.get("open", "N/A")

        sign = "+" if change >= 0 else ""
        lines = [
            f"{ticker}.{exchange} Live Quote:",
            f"  Price: ${price}",
            f"  Change: {sign}{change} ({sign}{change_p}%)",
            f"  Open: ${open_price}",
            f"  High: ${high}",
            f"  Low: ${low}",
            f"  Volume: {volume:,.0f}" if isinstance(volume, (int, float)) else f"  Volume: {volume}",
            f"  Previous Close: ${prev_close}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Error getting live price: {e}"


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

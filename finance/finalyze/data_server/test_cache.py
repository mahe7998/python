#!/usr/bin/env python3
"""Test script for data server caching.

Tests all API endpoints used by the investment_tool app.

Usage:
    # First start the data server (Docker)
    cd /Users/jmahe/projects/python/finance/finalyze/data_server
    docker compose up -d

    # Then run this test script
    source .venv/bin/activate
    python test_cache.py http://localhost:8000

Default URL: http://localhost:8000
"""

import os
import sys
import time
import requests
from datetime import date, datetime, timedelta


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def format_time(ms: float) -> str:
    """Format time with color based on speed."""
    if ms < 50:
        return f"{Colors.GREEN}{ms:.1f}ms{Colors.RESET}"
    elif ms < 500:
        return f"{Colors.YELLOW}{ms:.1f}ms{Colors.RESET}"
    else:
        return f"{Colors.RED}{ms:.1f}ms{Colors.RESET}"


def test_endpoint(name: str, method: str, url: str, params: dict = None, expected_min_records: int = 0) -> dict:
    """Test an endpoint and report timing."""
    # Build full URL with params for display
    if params:
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        display_url = f"{url}?{param_str}"
    else:
        display_url = url

    print(f"\n{Colors.BOLD}{Colors.CYAN}[TEST]{Colors.RESET} {name}")
    print(f"  {Colors.BLUE}Request:{Colors.RESET} {method} {display_url}")

    start = time.time()
    try:
        if method == "GET":
            response = requests.get(url, params=params, timeout=60)
        elif method == "POST":
            response = requests.post(url, json=params, timeout=60)
        else:
            raise ValueError(f"Unknown method: {method}")

        elapsed = (time.time() - start) * 1000

        if response.status_code == 200:
            data = response.json()
            record_count = len(data) if isinstance(data, list) else 1

            status = f"{Colors.GREEN}OK{Colors.RESET}"
            time_str = format_time(elapsed)

            print(f"  {Colors.BLUE}Status:{Colors.RESET} {status} ({response.status_code})")
            print(f"  {Colors.BLUE}Records:{Colors.RESET} {record_count}")
            print(f"  {Colors.BLUE}Time:{Colors.RESET} {time_str}")

            if expected_min_records > 0 and record_count < expected_min_records:
                print(f"  {Colors.YELLOW}Warning: Expected at least {expected_min_records} records{Colors.RESET}")

            return {"success": True, "time_ms": elapsed, "records": record_count, "name": name}
        else:
            status = f"{Colors.RED}FAILED{Colors.RESET}"
            print(f"  {Colors.BLUE}Status:{Colors.RESET} {status} ({response.status_code})")
            print(f"  {Colors.BLUE}Error:{Colors.RESET} {response.text[:200]}")
            print(f"  {Colors.BLUE}Time:{Colors.RESET} {format_time(elapsed)}")
            return {"success": False, "time_ms": elapsed, "error": response.text[:200], "name": name}

    except Exception as e:
        elapsed = (time.time() - start) * 1000
        print(f"  {Colors.BLUE}Status:{Colors.RESET} {Colors.RED}ERROR{Colors.RESET}")
        print(f"  {Colors.BLUE}Error:{Colors.RESET} {e}")
        print(f"  {Colors.BLUE}Time:{Colors.RESET} {format_time(elapsed)}")
        return {"success": False, "time_ms": elapsed, "error": str(e), "name": name}


def main():
    # Get base URL from args or environment
    base_url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("DATA_SERVER_URL", "http://localhost:8000")
    base_url = base_url.rstrip("/")

    # If URL doesn't end with /api, add it
    if not base_url.endswith("/api"):
        api_url = f"{base_url}/api"
    else:
        api_url = base_url

    print(f"{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}Data Server Cache Test{Colors.RESET}")
    print(f"{'='*70}")
    print(f"Server URL: {api_url}")
    print(f"EODHD API Key: {'Set' if os.getenv('EODHD_API_KEY') else 'Not set'}")
    print(f"{'='*70}")

    # Test data
    ticker = "AAPL"
    symbol = f"{ticker}.US"
    today = date.today()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    year_ago = today - timedelta(days=365)

    results = []

    # ============================================================
    # 1. DAILY PRICES (EOD)
    # ============================================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}1. DAILY PRICES (EOD){Colors.RESET}")
    print(f"{'='*70}")

    results.append(test_endpoint(
        "EOD - 1 week (AAPL)",
        "GET",
        f"{api_url}/eod/{symbol}",
        {"from": week_ago.isoformat(), "to": today.isoformat()},
        expected_min_records=3
    ))

    results.append(test_endpoint(
        "EOD - 1 week (AAPL) CACHE TEST",
        "GET",
        f"{api_url}/eod/{symbol}",
        {"from": week_ago.isoformat(), "to": today.isoformat()},
        expected_min_records=3
    ))

    results.append(test_endpoint(
        "EOD - 1 month (AAPL)",
        "GET",
        f"{api_url}/eod/{symbol}",
        {"from": month_ago.isoformat(), "to": today.isoformat()},
        expected_min_records=15
    ))

    results.append(test_endpoint(
        "EOD - 1 year (AAPL)",
        "GET",
        f"{api_url}/eod/{symbol}",
        {"from": year_ago.isoformat(), "to": today.isoformat()},
        expected_min_records=200
    ))

    # Test multiple tickers
    for test_ticker in ["MSFT", "GOOGL", "NVDA", "AMZN", "META"]:
        test_symbol = f"{test_ticker}.US"
        results.append(test_endpoint(
            f"EOD - 1 month ({test_ticker})",
            "GET",
            f"{api_url}/eod/{test_symbol}",
            {"from": month_ago.isoformat(), "to": today.isoformat()},
            expected_min_records=15
        ))

    # ============================================================
    # 2. INTRADAY PRICES
    # ============================================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}2. INTRADAY PRICES{Colors.RESET}")
    print(f"{'='*70}")

    # Get timestamps for last trading day
    now = datetime.now()
    # Go back to find a weekday
    trading_day = now
    while trading_day.weekday() >= 5:  # Saturday=5, Sunday=6
        trading_day -= timedelta(days=1)

    day_start = trading_day.replace(hour=9, minute=30, second=0, microsecond=0)
    day_end = trading_day.replace(hour=16, minute=0, second=0, microsecond=0)
    from_ts = int(day_start.timestamp())
    to_ts = int(day_end.timestamp())

    results.append(test_endpoint(
        "Intraday - 1m interval (AAPL)",
        "GET",
        f"{api_url}/intraday/{symbol}",
        {"interval": "1m", "from": from_ts, "to": to_ts}
    ))

    results.append(test_endpoint(
        "Intraday - 5m interval (AAPL)",
        "GET",
        f"{api_url}/intraday/{symbol}",
        {"interval": "5m", "from": from_ts, "to": to_ts}
    ))

    results.append(test_endpoint(
        "Intraday - 1h interval (AAPL)",
        "GET",
        f"{api_url}/intraday/{symbol}",
        {"interval": "1h", "from": from_ts, "to": to_ts}
    ))

    # ============================================================
    # 3. REAL-TIME QUOTES
    # ============================================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}3. REAL-TIME QUOTES{Colors.RESET}")
    print(f"{'='*70}")

    results.append(test_endpoint(
        "Real-time Quote (AAPL)",
        "GET",
        f"{api_url}/real-time/{symbol}"
    ))

    results.append(test_endpoint(
        "Real-time Quote (MSFT)",
        "GET",
        f"{api_url}/real-time/MSFT.US"
    ))

    # ============================================================
    # 4. FUNDAMENTALS / COMPANY INFO
    # ============================================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}4. FUNDAMENTALS / COMPANY INFO{Colors.RESET}")
    print(f"{'='*70}")

    results.append(test_endpoint(
        "Fundamentals (AAPL)",
        "GET",
        f"{api_url}/fundamentals/{symbol}"
    ))

    results.append(test_endpoint(
        "Fundamentals (AAPL) CACHE TEST",
        "GET",
        f"{api_url}/fundamentals/{symbol}"
    ))

    results.append(test_endpoint(
        "Fundamentals (NVDA)",
        "GET",
        f"{api_url}/fundamentals/NVDA.US"
    ))

    # ============================================================
    # 5. NEWS
    # ============================================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}5. NEWS{Colors.RESET}")
    print(f"{'='*70}")

    results.append(test_endpoint(
        "News - 50 articles (AAPL)",
        "GET",
        f"{api_url}/news",
        {"s": symbol, "limit": 50},
        expected_min_records=10
    ))

    results.append(test_endpoint(
        "News - 50 articles (AAPL) CACHE TEST",
        "GET",
        f"{api_url}/news",
        {"s": symbol, "limit": 50},
        expected_min_records=10
    ))

    results.append(test_endpoint(
        "News - 100 articles (NVDA)",
        "GET",
        f"{api_url}/news",
        {"s": "NVDA.US", "limit": 100},
        expected_min_records=20
    ))

    results.append(test_endpoint(
        "News - 1000 articles (AAPL)",
        "GET",
        f"{api_url}/news",
        {"s": symbol, "limit": 1000},
        expected_min_records=100
    ))

    results.append(test_endpoint(
        "News - 1000 articles (AAPL) CACHE TEST",
        "GET",
        f"{api_url}/news",
        {"s": symbol, "limit": 1000},
        expected_min_records=100
    ))

    # ============================================================
    # 6. SEARCH
    # ============================================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}6. SEARCH{Colors.RESET}")
    print(f"{'='*70}")

    results.append(test_endpoint(
        "Search - 'Apple'",
        "GET",
        f"{api_url}/search/Apple",
        {"limit": 15}
    ))

    results.append(test_endpoint(
        "Search - 'Microsoft'",
        "GET",
        f"{api_url}/search/Microsoft",
        {"limit": 15}
    ))

    results.append(test_endpoint(
        "Search - 'NVDA'",
        "GET",
        f"{api_url}/search/NVDA",
        {"limit": 15}
    ))

    # ============================================================
    # 7. EXCHANGES
    # ============================================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}7. EXCHANGES{Colors.RESET}")
    print(f"{'='*70}")

    results.append(test_endpoint(
        "Exchanges List",
        "GET",
        f"{api_url}/exchanges-list"
    ))

    results.append(test_endpoint(
        "Exchange Symbols (US)",
        "GET",
        f"{api_url}/exchange-symbol-list/US"
    ))

    # ============================================================
    # 8. CONTENT
    # ============================================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}8. CONTENT{Colors.RESET}")
    print(f"{'='*70}")

    # Get a content ID from news to test content endpoint
    try:
        news_response = requests.get(f"{api_url}/news", params={"s": symbol, "limit": 1}, timeout=10)
        if news_response.status_code == 200:
            news_data = news_response.json()
            if news_data and len(news_data) > 0:
                content_id = news_data[0].get("content_id")
                if content_id:
                    results.append(test_endpoint(
                        f"Content by ID ({content_id[:16]}...)",
                        "GET",
                        f"{api_url}/content/{content_id}"
                    ))
    except Exception as e:
        print(f"  {Colors.YELLOW}Skipping content test: {e}{Colors.RESET}")

    # ============================================================
    # SUMMARY
    # ============================================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}SUMMARY{Colors.RESET}")
    print(f"{'='*70}")

    success_count = sum(1 for r in results if r.get("success"))
    total_count = len(results)
    total_time = sum(r.get("time_ms", 0) for r in results)

    print(f"Total tests: {total_count}")
    print(f"Successful: {Colors.GREEN}{success_count}{Colors.RESET}")
    if total_count - success_count > 0:
        print(f"Failed: {Colors.RED}{total_count - success_count}{Colors.RESET}")
    print(f"Total time: {total_time:.1f}ms ({total_time/1000:.1f}s)")
    print(f"Average time: {total_time/total_count:.1f}ms per request")

    # Cache effectiveness analysis
    print(f"\n{Colors.BOLD}Cache Effectiveness:{Colors.RESET}")

    cache_tests = [
        ("EOD - 1 week (AAPL)", "EOD - 1 week (AAPL) CACHE TEST"),
        ("Fundamentals (AAPL)", "Fundamentals (AAPL) CACHE TEST"),
        ("News - 50 articles (AAPL)", "News - 50 articles (AAPL) CACHE TEST"),
        ("News - 1000 articles (AAPL)", "News - 1000 articles (AAPL) CACHE TEST"),
    ]

    for first_name, second_name in cache_tests:
        first = next((r for r in results if r.get("name") == first_name), None)
        second = next((r for r in results if r.get("name") == second_name), None)

        if first and second and first.get("success") and second.get("success"):
            first_time = first["time_ms"]
            second_time = second["time_ms"]
            if second_time < first_time:
                speedup = (first_time - second_time) / first_time * 100
                print(f"  {first_name}: {Colors.GREEN}{speedup:.0f}% faster{Colors.RESET} ({first_time:.0f}ms -> {second_time:.0f}ms)")
            else:
                print(f"  {first_name}: {Colors.RED}No speedup{Colors.RESET} ({first_time:.0f}ms -> {second_time:.0f}ms)")

    # Slowest requests
    print(f"\n{Colors.BOLD}Slowest Requests:{Colors.RESET}")
    sorted_results = sorted(results, key=lambda x: x.get("time_ms", 0), reverse=True)
    for r in sorted_results[:5]:
        print(f"  {r.get('name')}: {format_time(r.get('time_ms', 0))}")

    # Failures
    failures = [r for r in results if not r.get("success")]
    if failures:
        print(f"\n{Colors.BOLD}{Colors.RED}FAILURES:{Colors.RESET}")
        for r in failures:
            print(f"  {r.get('name')}: {r.get('error', 'Unknown error')[:80]}")

    return 0 if success_count == total_count else 1


if __name__ == "__main__":
    sys.exit(main())

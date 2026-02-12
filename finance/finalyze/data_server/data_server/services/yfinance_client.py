"""yfinance fallback for shares outstanding, intraday prices, and search."""

import asyncio
import logging
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

# EODHD exchange code → yfinance suffix mapping
# yfinance uses different exchange suffixes than EODHD for many markets
_EODHD_TO_YF_EXCHANGE = {
    "KO": "KS",    # Korea Exchange (EODHD: KO, yfinance: KS)
    "AS": "AS",    # Euronext Amsterdam
    "PA": "PA",    # Euronext Paris
    "LSE": "L",    # London Stock Exchange (EODHD: LSE, yfinance: L)
    "HK": "HK",   # Hong Kong
    "TO": "TO",    # Toronto
    "SN": "SN",    # Santiago
    "SA": "SA",    # Sao Paulo
    "NSE": "NS",   # India NSE (EODHD: NSE, yfinance: NS)
    "BSE": "BO",   # India BSE (EODHD: BSE, yfinance: BO)
    "SHE": "SZ",   # Shenzhen (EODHD: SHE, yfinance: SZ)
    "SHG": "SS",   # Shanghai (EODHD: SHG, yfinance: SS)
    "TSE": "T",    # Tokyo (EODHD: TSE, yfinance: T)
    "F": "F",      # Frankfurt
    "SW": "SW",    # SIX Swiss Exchange
    "AU": "AX",    # Australian Securities Exchange (EODHD: AU, yfinance: AX)
}

# Reverse mapping: yfinance exchange code → EODHD exchange code
_YF_EXCHANGE_TO_EODHD = {
    "NYQ": "US", "NMS": "US", "NGM": "US", "PCX": "US", "BTS": "US",  # US exchanges
    "PNK": "US",  # OTC
    "JPX": "TSE",  # Tokyo
    "KSC": "KO", "KOE": "KO",  # Korea
    "HKG": "HK",  # Hong Kong
    "TOR": "TO",  # Toronto
    "LSE": "LSE",  # London
    "PAR": "PA",  # Paris
    "AMS": "AS",  # Amsterdam
    "FRA": "F",   # Frankfurt
    "SHZ": "SHE",  # Shenzhen
    "SHH": "SHG",  # Shanghai
    "NSI": "NSE",  # India NSE
    "BOM": "BSE",  # India BSE
    "SAO": "SA",  # Sao Paulo
    "ASX": "AU",  # Australia
    "EBS": "SW",  # Switzerland
    "TAI": "TW",  # Taiwan
    "SES": "SG",  # Singapore
}

# Reverse mapping: yfinance symbol suffix → EODHD exchange code
_YF_SUFFIX_TO_EODHD = {v: k for k, v in _EODHD_TO_YF_EXCHANGE.items()}


def _to_yfinance_symbol(ticker: str, exchange: str) -> str:
    """Convert EODHD ticker+exchange to yfinance symbol."""
    if exchange == "US":
        return ticker
    yf_suffix = _EODHD_TO_YF_EXCHANGE.get(exchange, exchange)
    return f"{ticker}.{yf_suffix}"


async def get_shares_outstanding(ticker: str, exchange: str = "US") -> Optional[int]:
    """Get shares outstanding from yfinance as a fallback.

    Args:
        ticker: Stock ticker (e.g., "NVDA")
        exchange: Exchange code (e.g., "US")

    Returns:
        Shares outstanding count, or None if unavailable
    """
    def _fetch() -> Optional[int]:
        try:
            import yfinance as yf
            # yfinance uses standard ticker symbols (no exchange suffix for US)
            symbol = _to_yfinance_symbol(ticker, exchange)
            t = yf.Ticker(symbol)
            info = t.info
            shares = info.get("sharesOutstanding")
            if shares and shares > 0:
                return int(shares)
            return None
        except Exception as e:
            logger.error(f"yfinance error for {ticker}: {e}")
            return None

    return await asyncio.to_thread(_fetch)


async def get_shares_history_entry(ticker: str, exchange: str = "US") -> Optional[dict]:
    """Get a single shares outstanding data point from yfinance.

    Returns a dict compatible with shares_history storage, or None.
    """
    shares = await get_shares_outstanding(ticker, exchange)
    if shares is None:
        return None

    return {
        "shares_outstanding": shares,
        "report_date": date.today(),
        "source": "yfinance",
        "filing_type": None,
        "filed_date": None,
        "fiscal_year": None,
        "fiscal_period": None,
    }


async def get_intraday_prices(
    ticker: str,
    exchange: str = "US",
    interval: str = "1m",
    target_date: Optional[date] = None,
) -> list[dict]:
    """Get intraday prices from yfinance as a fallback when EODHD is unavailable.

    yfinance provides 1-minute data for the last 7 days, available immediately
    after market close (unlike EODHD which can take hours).

    Args:
        ticker: Stock ticker (e.g., "NVDA")
        exchange: Exchange code (e.g., "US")
        interval: Bar interval (default "1m")
        target_date: Specific date to fetch. If None, fetches most recent day.

    Returns:
        List of dicts with timestamp, open, high, low, close, volume
    """
    def _fetch() -> list[dict]:
        try:
            import yfinance as yf
            import pandas as pd

            symbol = _to_yfinance_symbol(ticker, exchange)
            t = yf.Ticker(symbol)

            # yfinance 1m data: need period="5d" (max for 1m), then filter to target_date
            df = t.history(period="5d", interval=interval)

            if df is None or df.empty:
                logger.warning(f"yfinance returned no intraday data for {symbol}")
                return []

            # Filter to target_date if specified
            if target_date is not None:
                # yfinance returns timezone-aware timestamps
                df_dates = df.index.date
                df = df[df_dates == target_date]

                if df.empty:
                    logger.info(f"yfinance has no data for {symbol} on {target_date}")
                    return []

            # Convert to UTC timestamps and format as dicts
            records = []
            for ts, row in df.iterrows():
                # Convert to UTC naive timestamp (matching EODHD format)
                if ts.tzinfo is not None:
                    ts_utc = ts.tz_convert("UTC").tz_localize(None)
                else:
                    ts_utc = ts

                records.append({
                    "timestamp": ts_utc.isoformat(),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"]),
                })

            logger.info(f"yfinance returned {len(records)} intraday bars for {symbol} ({interval})")
            return records

        except Exception as e:
            logger.error(f"yfinance intraday error for {ticker}: {e}")
            return []

    return await asyncio.to_thread(_fetch)


async def get_daily_prices(
    ticker: str,
    exchange: str = "US",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> list[dict]:
    """Get daily OHLCV prices from yfinance as fallback for exchanges EODHD doesn't support.

    Returns list of dicts matching EODHD EOD format: date, open, high, low, close, adjusted_close, volume.
    """
    def _fetch() -> list[dict]:
        try:
            import yfinance as yf

            symbol = _to_yfinance_symbol(ticker, exchange)
            t = yf.Ticker(symbol)

            kwargs = {}
            if from_date:
                kwargs["start"] = from_date
            if to_date:
                kwargs["end"] = to_date
            if not kwargs:
                kwargs["period"] = "5y"

            df = t.history(**kwargs)

            if df is None or df.empty:
                logger.warning(f"yfinance returned no daily data for {symbol}")
                return []

            records = []
            for ts, row in df.iterrows():
                dt = ts.date() if hasattr(ts, 'date') else ts
                records.append({
                    "date": str(dt),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "adjusted_close": float(row["Close"]),
                    "volume": int(row["Volume"]),
                })

            logger.info(f"yfinance returned {len(records)} daily bars for {symbol}")
            return records

        except Exception as e:
            logger.error(f"yfinance daily error for {ticker}: {e}")
            return []

    return await asyncio.to_thread(_fetch)


async def get_fundamentals(ticker: str, exchange: str = "US") -> Optional[dict]:
    """Get company fundamentals from yfinance, returned in EODHD-compatible format.

    Used as fallback when EODHD doesn't support an exchange (e.g., TSE).
    """
    def _fetch() -> Optional[dict]:
        try:
            import yfinance as yf

            symbol = _to_yfinance_symbol(ticker, exchange)
            t = yf.Ticker(symbol)
            info = t.info

            if not info or info.get("regularMarketPrice") is None:
                logger.warning(f"yfinance returned no info for {symbol}")
                return None

            # Map yfinance info to EODHD-compatible structure
            return {
                "General": {
                    "Name": info.get("longName") or info.get("shortName", ticker),
                    "Exchange": exchange,
                    "CurrencyCode": info.get("currency", "USD"),
                    "Sector": info.get("sector"),
                    "Industry": info.get("industry"),
                    "CountryISO": info.get("country"),
                    "Description": info.get("longBusinessSummary"),
                },
                "Highlights": {
                    "MarketCapitalization": info.get("marketCap"),
                    "PERatio": info.get("trailingPE"),
                    "ForwardPE": info.get("forwardPE"),
                    "EarningsShare": info.get("trailingEps"),
                    "DilutedEpsTTM": info.get("trailingEps"),
                    "ProfitMargin": info.get("profitMargins"),
                    "OperatingMarginTTM": info.get("operatingMargins"),
                    "ReturnOnEquityTTM": info.get("returnOnEquity"),
                    "ReturnOnAssetsTTM": info.get("returnOnAssets"),
                    "GrossProfitTTM": info.get("grossProfits"),
                    "EBITDA": info.get("ebitda"),
                    "RevenueTTM": info.get("totalRevenue"),
                    "RevenuePerShareTTM": info.get("revenuePerShare"),
                    "DividendYield": info.get("dividendYield"),
                    "DividendShare": info.get("dividendRate"),
                    "WallStreetTargetPrice": info.get("targetMeanPrice"),
                },
                "Valuation": {
                    "PEGRatio": info.get("pegRatio"),
                    "PriceBookMRQ": info.get("priceToBook"),
                    "PriceSalesTTM": info.get("priceToSalesTrailing12Months"),
                    "EnterpriseValue": info.get("enterpriseValue"),
                    "EnterpriseValueRevenue": info.get("enterpriseToRevenue"),
                    "EnterpriseValueEbitda": info.get("enterpriseToEbitda"),
                },
                "SharesStats": {
                    "SharesOutstanding": info.get("sharesOutstanding"),
                    "SharesFloat": info.get("floatShares"),
                    "PercentInsiders": info.get("heldPercentInsiders"),
                    "PercentInstitutions": info.get("heldPercentInstitutions"),
                    "SharesShort": info.get("sharesShort"),
                    "ShortRatio": info.get("shortRatio"),
                },
                "Technicals": {
                    "Beta": info.get("beta"),
                    "52WeekHigh": info.get("fiftyTwoWeekHigh"),
                    "52WeekLow": info.get("fiftyTwoWeekLow"),
                    "50DayMA": info.get("fiftyDayAverage"),
                    "200DayMA": info.get("twoHundredDayAverage"),
                },
                "_source": "yfinance",
            }

        except Exception as e:
            logger.error(f"yfinance fundamentals error for {ticker}: {e}")
            return None

    return await asyncio.to_thread(_fetch)


def _yf_symbol_to_eodhd(symbol: str) -> tuple[str, str]:
    """Convert yfinance symbol (e.g. '7203.T') to EODHD ticker+exchange."""
    if "." in symbol:
        ticker, suffix = symbol.rsplit(".", 1)
        exchange = _YF_SUFFIX_TO_EODHD.get(suffix, suffix)
        return ticker, exchange
    return symbol, "US"


def _yf_quote_to_eodhd(quote: dict) -> dict:
    """Convert a yfinance search quote to EODHD search result format."""
    symbol = quote.get("symbol", "")
    ticker, exchange = _yf_symbol_to_eodhd(symbol)

    # Also try exchange code from the quote itself
    yf_exchange = quote.get("exchange", "")
    if exchange == "US" and yf_exchange in _YF_EXCHANGE_TO_EODHD:
        exchange = _YF_EXCHANGE_TO_EODHD[yf_exchange]
    elif yf_exchange in _YF_EXCHANGE_TO_EODHD:
        exchange = _YF_EXCHANGE_TO_EODHD[yf_exchange]

    # Map yfinance quoteType to EODHD Type
    type_map = {
        "EQUITY": "Common Stock",
        "ETF": "ETF",
        "MUTUALFUND": "Fund",
        "INDEX": "Index",
        "CRYPTOCURRENCY": "Crypto",
    }
    asset_type = type_map.get(quote.get("quoteType", ""), quote.get("typeDisp", ""))

    return {
        "Code": ticker,
        "Exchange": exchange,
        "Name": quote.get("longname") or quote.get("shortname", ""),
        "Type": asset_type,
        "Country": quote.get("sectorDisp", ""),
        "Currency": quote.get("currency", ""),
        "ISIN": None,
        "previousClose": quote.get("previousClose"),
        "_source": "yfinance",
    }


async def search(query: str, max_results: int = 15, exchange: str = None) -> list[dict]:
    """Search for tickers using yfinance, returning results in EODHD format."""
    def _fetch() -> list[dict]:
        try:
            import yfinance as yf
            results = yf.Search(query, max_results=max_results)
            quotes = results.quotes if results.quotes else []

            eodhd_results = []
            for quote in quotes:
                converted = _yf_quote_to_eodhd(quote)
                # Filter by exchange if specified
                if exchange and converted["Exchange"] != exchange:
                    continue
                eodhd_results.append(converted)

            logger.info(f"yfinance search '{query}' returned {len(eodhd_results)} results")
            return eodhd_results

        except Exception as e:
            logger.error(f"yfinance search error for '{query}': {e}")
            return []

    return await asyncio.to_thread(_fetch)


def _build_financial_record(col_date, income_df, balance_df, cashflow_df) -> dict:
    """Build a single financial record from yfinance DataFrames for a given date.

    Works for both quarterly and annual DataFrames since field names are identical.
    """
    import math

    dt = col_date.date() if hasattr(col_date, 'date') else col_date
    date_str = str(dt)

    def _get(df, field):
        if df is not None and not df.empty and field in df.index and col_date in df.columns:
            val = df.loc[field, col_date]
            if val is not None:
                try:
                    fval = float(val)
                    if not math.isnan(fval):
                        return fval
                except (ValueError, TypeError):
                    pass
        return None

    income = {
        "totalRevenue": _get(income_df, "Total Revenue"),
        "grossProfit": _get(income_df, "Gross Profit"),
        "operatingIncome": _get(income_df, "Operating Income"),
        "netIncome": _get(income_df, "Net Income"),
        "ebit": _get(income_df, "EBIT"),
        "costOfRevenue": _get(income_df, "Cost Of Revenue"),
        "researchDevelopment": _get(income_df, "Selling General And Administration"),
        "interestExpense": _get(income_df, "Interest Expense"),
        "taxProvision": _get(income_df, "Tax Provision"),
    }
    balance = {}
    if balance_df is not None and not balance_df.empty and col_date in balance_df.columns:
        balance = {
            "cash": _get(balance_df, "Cash And Cash Equivalents"),
            "shortTermInvestments": _get(balance_df, "Other Short Term Investments"),
            "totalAssets": _get(balance_df, "Total Assets"),
            "totalCurrentAssets": _get(balance_df, "Current Assets"),
            "totalLiab": _get(balance_df, "Total Liabilities Net Minority Interest"),
            "totalCurrentLiabilities": _get(balance_df, "Current Liabilities"),
            "totalStockholderEquity": _get(balance_df, "Stockholders Equity"),
            "longTermDebt": _get(balance_df, "Long Term Debt"),
            "retainedEarnings": _get(balance_df, "Retained Earnings"),
        }
    cashflow = {}
    if cashflow_df is not None and not cashflow_df.empty and col_date in cashflow_df.columns:
        cashflow = {
            "totalCashFromOperatingActivities": _get(cashflow_df, "Operating Cash Flow"),
            "capitalExpenditures": _get(cashflow_df, "Capital Expenditure"),
            "freeCashFlow": _get(cashflow_df, "Free Cash Flow"),
            "dividendsPaid": _get(cashflow_df, "Cash Dividends Paid"),
        }

    return {
        "date": date_str,
        "income": income,
        "balance": balance,
        "cashflow": cashflow,
    }


def _has_income_data(records: list[dict]) -> bool:
    """Check if any record has meaningful income data (revenue or net income)."""
    for r in records:
        inc = r.get("income", {})
        if inc.get("totalRevenue") is not None or inc.get("netIncome") is not None:
            return True
    return False


async def get_quarterly_financials(ticker: str, exchange: str = "US") -> list[dict]:
    """Get quarterly financials from yfinance in EODHD-compatible format.

    Uses union of dates from income, balance sheet, and cashflow DataFrames.
    If quarterly data lacks income metrics (common for Japanese stocks),
    supplements with annual financial data.
    """
    def _fetch() -> list[dict]:
        try:
            import yfinance as yf

            symbol = _to_yfinance_symbol(ticker, exchange)
            t = yf.Ticker(symbol)

            qf = t.quarterly_financials
            qbs = t.quarterly_balance_sheet
            qcf = t.quarterly_cashflow

            # Use union of ALL quarterly dates (not just income statement)
            all_dates = set()
            for df in [qf, qbs, qcf]:
                if df is not None and not df.empty:
                    all_dates.update(df.columns)

            results = []
            for col_date in sorted(all_dates, reverse=True):
                record = _build_financial_record(col_date, qf, qbs, qcf)
                results.append(record)

            # If quarterly data lacks income metrics, use annual data ONLY
            # (don't mix quarterly balance-only records with annual income records)
            if not _has_income_data(results):
                logger.info(f"Quarterly data for {symbol} lacks income metrics, using annual data")
                af = t.financials
                abs_ = t.balance_sheet
                acf = t.cashflow

                annual_dates = set()
                for df in [af, abs_, acf]:
                    if df is not None and not df.empty:
                        annual_dates.update(df.columns)

                if annual_dates:
                    # Replace quarterly-only records with annual data
                    results = []
                    for col_date in sorted(annual_dates, reverse=True):
                        record = _build_financial_record(col_date, af, abs_, acf)
                        results.append(record)
                    logger.info(f"Using {len(results)} annual periods for {symbol}")

            if not results:
                return []

            logger.info(f"yfinance returned {len(results)} financial periods for {symbol}")
            return results

        except Exception as e:
            logger.error(f"yfinance quarterly error for {ticker}: {e}")
            return []

    return await asyncio.to_thread(_fetch)

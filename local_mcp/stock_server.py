# stock_server.py
from fastmcp import FastMCP
import asyncio
from pydantic import BaseModel
import yfinance as yf

class StockPriceParams(BaseModel):
    symbol: str

class StockPriceResponse(BaseModel):
    symbol: str
    price: float
    currency: str

class StockInfoParams(BaseModel):
    symbol: str

class StockInfoResponse(BaseModel):
    symbol: str
    company_name: str
    price: float
    market_cap: str
    pe_ratio: float

# Instantiate the MCP server
mcp = FastMCP("StockServer")

@mcp.tool()
async def get_stock_price(params: StockPriceParams) -> StockPriceResponse:
    """Get the current stock price for a given symbol."""
    try:
        ticker = yf.Ticker(params.symbol)
        info = ticker.info
        price = float(info.get("regularMarketPrice", info.get("currentPrice", 0)))
        currency = info.get("currency", "USD")
        
        return StockPriceResponse(
            symbol=params.symbol.upper(),
            price=price,
            currency=currency
        )
    except Exception as e:
        return StockPriceResponse(
            symbol=params.symbol.upper(),
            price=0.0,
            currency="USD"
        )

@mcp.tool()
async def get_stock_info(params: StockInfoParams) -> StockInfoResponse:
    """Get detailed information about a stock."""
    try:
        ticker = yf.Ticker(params.symbol)
        info = ticker.info
        print("ollama calling with stock :", info)  # Debugging output
        return StockInfoResponse(
            symbol=params.symbol.upper(),
            company_name=info.get("longName", "Unknown"),
            price=float(info.get("regularMarketPrice", info.get("currentPrice", 0))),
            market_cap=info.get("marketCap", "N/A"),
            pe_ratio=float(info.get("trailingPE", 0))
        )
    except Exception as e:
        return StockInfoResponse(
            symbol=params.symbol.upper(),
            company_name="Unknown",
            price=0.0,
            market_cap="N/A",
            pe_ratio=0.0
        )

if __name__ == "__main__":
    # Run over STDIO for local testing
    mcp.run(transport="stdio")

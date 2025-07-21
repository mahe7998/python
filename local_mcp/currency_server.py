# currency_server.py
from fastmcp import FastMCP
import asyncio
from pydantic import BaseModel
import httpx
from typing import Optional

class CurrencyConversionParams(BaseModel):
    amount: float
    from_currency: str
    to_currency: str

class CurrencyConversionResponse(BaseModel):
    amount: float
    from_currency: str
    to_currency: str
    converted_amount: float
    exchange_rate: float

class ExchangeRateParams(BaseModel):
    from_currency: str
    to_currency: str

class ExchangeRateResponse(BaseModel):
    from_currency: str
    to_currency: str
    exchange_rate: float

# Instantiate the MCP server
mcp = FastMCP("CurrencyServer")

@mcp.tool()
async def convert_currency(params: CurrencyConversionParams) -> CurrencyConversionResponse:
    """Convert amount from one currency to another using real-time exchange rates."""
    try:
        # Using exchangerate-api.com free service
        from_curr = params.from_currency.upper()
        to_curr = params.to_currency.upper()
        
        async with httpx.AsyncClient() as client:
            # Free API endpoint - no key required for basic usage
            url = f"https://api.exchangerate-api.com/v4/latest/{from_curr}"
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                rates = data.get("rates", {})
                
                if to_curr in rates:
                    exchange_rate = rates[to_curr]
                    converted_amount = params.amount * exchange_rate
                    
                    return CurrencyConversionResponse(
                        amount=params.amount,
                        from_currency=from_curr,
                        to_currency=to_curr,
                        converted_amount=round(converted_amount, 2),
                        exchange_rate=round(exchange_rate, 6)
                    )
                else:
                    # Currency not found, return error values
                    return CurrencyConversionResponse(
                        amount=params.amount,
                        from_currency=from_curr,
                        to_currency=to_curr,
                        converted_amount=0.0,
                        exchange_rate=0.0
                    )
            else:
                # API error, return zero values
                return CurrencyConversionResponse(
                    amount=params.amount,
                    from_currency=from_curr,
                    to_currency=to_curr,
                    converted_amount=0.0,
                    exchange_rate=0.0
                )
                
    except Exception as e:
        print(f"Currency conversion error: {e}")
        return CurrencyConversionResponse(
            amount=params.amount,
            from_currency=params.from_currency.upper(),
            to_currency=params.to_currency.upper(),
            converted_amount=0.0,
            exchange_rate=0.0
        )

@mcp.tool()
async def get_exchange_rate(params: ExchangeRateParams) -> ExchangeRateResponse:
    """Get the current exchange rate between two currencies."""
    try:
        from_curr = params.from_currency.upper()
        to_curr = params.to_currency.upper()
        
        async with httpx.AsyncClient() as client:
            url = f"https://api.exchangerate-api.com/v4/latest/{from_curr}"
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                rates = data.get("rates", {})
                
                if to_curr in rates:
                    exchange_rate = rates[to_curr]
                    
                    return ExchangeRateResponse(
                        from_currency=from_curr,
                        to_currency=to_curr,
                        exchange_rate=round(exchange_rate, 6)
                    )
                else:
                    return ExchangeRateResponse(
                        from_currency=from_curr,
                        to_currency=to_curr,
                        exchange_rate=0.0
                    )
            else:
                return ExchangeRateResponse(
                    from_currency=from_curr,
                    to_currency=to_curr,
                    exchange_rate=0.0
                )
                
    except Exception as e:
        print(f"Exchange rate error: {e}")
        return ExchangeRateResponse(
            from_currency=params.from_currency.upper(),
            to_currency=params.to_currency.upper(),
            exchange_rate=0.0
        )

if __name__ == "__main__":
    # Run over STDIO for local testing
    mcp.run(transport="stdio")
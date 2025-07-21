# demo.py - Manual demonstration of the multi-server system
import asyncio
from fastmcp import Client

async def demo_multi_server():
    """Demonstrate both stock and currency servers working together"""
    
    print("=== Multi-Server MCP Demo ===")
    
    # Step 1: Get AAPL stock price
    print("\n1. Getting AAPL stock price...")
    stock_client = Client("stock_server.py")
    
    async with stock_client:
        stock_result = await stock_client.call_tool("get_stock_price", {
            "params": {"symbol": "AAPL"}
        })
        
        stock_data = stock_result.structured_content
        print(f"   AAPL Price: ${stock_data['price']} {stock_data['currency']}")
        
        # Step 2: Convert to Euros
        print("\n2. Converting to Euros...")
        currency_client = Client("currency_server.py")
        
        async with currency_client:
            conversion_result = await currency_client.call_tool("convert_currency", {
                "params": {
                    "amount": stock_data['price'],
                    "from_currency": "USD",
                    "to_currency": "EUR"
                }
            })
            
            conversion_data = conversion_result.structured_content
            print(f"   Exchange Rate: 1 USD = {conversion_data['exchange_rate']} EUR")
            print(f"   AAPL Price in Euros: €{conversion_data['converted_amount']}")
            
        print(f"\n=== FINAL ANSWER ===")
        print(f"Current AAPL stock price: €{conversion_data['converted_amount']} EUR")
        print(f"(${stock_data['price']} USD at rate {conversion_data['exchange_rate']})")

if __name__ == "__main__":
    asyncio.run(demo_multi_server())
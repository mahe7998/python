# test_mcp.py
import asyncio
from fastmcp import Client

async def test_mcp_connection():
    print("Testing MCP connection...")
    
    try:
        # Connect to the MCP server
        client = Client("stock_server.py")
        
        async with client:
            print("Connected to MCP server successfully!")
            
            # List available tools
            tools = await client.list_tools()
            print(f"Available tools: {[tool.name for tool in tools]}")
            
            # Print tool schema for debugging
            for tool in tools:
                if tool.name == "get_stock_price":
                    print(f"\nTool schema for {tool.name}:")
                    print(f"Input schema: {tool.inputSchema}")
                    break
            
            # Test the get_stock_price tool
            print("\nTesting get_stock_price tool...")
            # Based on the schema, try passing arguments as a dict
            try:
                # The schema shows it expects: {"params": {"symbol": "AAPL"}}
                arguments = {"params": {"symbol": "AAPL"}}
                result = await client.call_tool("get_stock_price", arguments)
                print(f"Result with arguments dict: {result}")
            except Exception as e1:
                print(f"Error with arguments dict: {e1}")
                try:
                    # Try without the arguments parameter
                    result = await client.call_tool("get_stock_price")
                    print(f"Result with no args: {result}")
                except Exception as e2:
                    print(f"Error with no args: {e2}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_mcp_connection())

# agent.py - Fixed version using direct FastMCP + Ollama integration
import asyncio
from fastmcp import Client
import ollama

async def get_realtime_data(user_query: str):
    """Get real-time data using MCP servers and Ollama LLM for any request"""
    
    # Connect to both MCP servers
    stock_client = Client("stock_server.py")
    currency_client = Client("currency_server.py")
    
    async with stock_client, currency_client:
        # Get tools from both MCP servers and convert to Ollama format
        stock_tools = await stock_client.list_tools()
        currency_tools = await currency_client.list_tools()
        
        all_mcp_tools = list(stock_tools) + list(currency_tools)
        print(f"Available MCP tools: {[tool.name for tool in all_mcp_tools]}")
        
        # Convert MCP tools to Ollama tool format
        ollama_tools = []
        for tool in all_mcp_tools:
            ollama_tool = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                }
            }
            ollama_tools.append(ollama_tool)
        
        # Get response from LLM with tools - let Ollama decide if tools are needed
        initial_response = ollama.chat(
            model="llama3.3:70b",
            messages=[{
                "role": "user", 
                "content": f"{user_query}. IMPORTANT: You must use the available tools to get real-time data. Do not just describe what you would do - actually call the tools. Call one tool at a time."
            }],
            tools=ollama_tools,
        )
        
        print(f"Initial response: {initial_response.message}")
        
        # Handle multi-round tool calling
        messages = [{"role": "user", "content": f"{user_query}. IMPORTANT: You must use the available tools to get real-time data. Do not just describe what you would do - actually call the tools. Call one tool at a time."}]
        current_response = initial_response
        
        # Allow up to 3 rounds of tool calls to handle multi-step queries
        for round_num in range(3):
            if current_response.message.tool_calls:
                print(f"\n--- Tool Call Round {round_num + 1} ---")
                
                # Handle the first tool call (we only support one at a time)
                tool_call = current_response.message.tool_calls[0]
                print(f"Tool call: {tool_call.function.name} with args: {tool_call.function.arguments}")
                
                # Execute the tool call on the appropriate client
                try:
                    # Determine which client to use based on tool name
                    stock_tool_names = [tool.name for tool in stock_tools]
                    currency_tool_names = [tool.name for tool in currency_tools]
                    
                    if tool_call.function.name in stock_tool_names:
                        result = await stock_client.call_tool(
                            tool_call.function.name, 
                            tool_call.function.arguments
                        )
                    elif tool_call.function.name in currency_tool_names:
                        result = await currency_client.call_tool(
                            tool_call.function.name, 
                            tool_call.function.arguments
                        )
                    else:
                        raise Exception(f"Unknown tool: {tool_call.function.name}")
                    
                    print(f"Tool result: {result}")
                    
                    # Add the messages to the conversation
                    messages.append(current_response.message)
                    messages.append({
                        "role": "tool", 
                        "name": tool_call.function.name, 
                        "content": str(result.content[0].text) if result.content else str(result)
                    })
                    
                    # Get next response from LLM
                    current_response = ollama.chat(
                        model="llama3.3:70b",
                        messages=messages,
                        tools=ollama_tools,
                    )
                    
                except Exception as e:
                    print(f"Error executing tool: {e}")
                    return f"Error using tool {tool_call.function.name}: {e}"
            else:
                # No more tool calls, return the final response
                return current_response.message.content
        
        # If we've exhausted all rounds and still have tool calls, return the latest response
        return current_response.message.content or "Unable to complete the request after multiple tool calls."

async def main():
    print("Real-time Data Assistant - Processing query using MCP servers...")
    result = await get_realtime_data("What is the current AAPL price in Euros?")
    print(f"\n=== FINAL RESULT ===")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
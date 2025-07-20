# agent.py - Fixed version using direct FastMCP + Ollama integration
import asyncio
from fastmcp import Client
import ollama

async def get_realtime_data(user_query: str):
    """Get real-time data using MCP server and Ollama LLM for any request"""
    
    # Connect to the MCP server
    client = Client("stock_server.py")
    
    async with client:
        # Get tools from MCP server and convert to Ollama format
        mcp_tools = await client.list_tools()
        print(f"Available MCP tools: {[tool.name for tool in mcp_tools]}")
        
        # Convert MCP tools to Ollama tool format
        ollama_tools = []
        for tool in mcp_tools:
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
                "content": f"{user_query}. If this requires real-time data that you have tools for, use the appropriate tool instead of relying on your training data."
            }],
            tools=ollama_tools,
        )
        
        print(f"Initial response: {initial_response.message}")
        
        # Check if the model wants to use tools
        if initial_response.message.tool_calls:
            for tool_call in initial_response.message.tool_calls:
                print(f"Tool call: {tool_call.function.name} with args: {tool_call.function.arguments}")
                
                # Execute the tool call
                try:
                    result = await client.call_tool(
                        tool_call.function.name, 
                        tool_call.function.arguments
                    )
                    print(f"Tool result: {result}")
                    
                    # Get final response with tool result
                    final_response = ollama.chat(
                        model="llama3.3:70b",
                        messages=[
                            {"role": "user", "content": f"{user_query}. If this requires real-time data that you have tools for, use the appropriate tool."},
                            initial_response.message,
                            {
                                "role": "tool", 
                                "name": tool_call.function.name, 
                                "content": str(result.content[0].text) if result.content else str(result)
                            }
                        ],
                    )
                    
                    return final_response.message.content
                    
                except Exception as e:
                    print(f"Error executing tool: {e}")
                    return f"Error getting stock price: {e}"
        else:
            # If no tool calls, the LLM responded directly (this is what we want to avoid)
            return f"Warning: LLM responded without using tools: {initial_response.message.content}"

async def main():
    print("Real-time Data Assistant - Processing query using MCP server...")
    result = await get_realtime_data("Get the AAPL stock price")
    print(f"\n=== FINAL RESULT ===")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
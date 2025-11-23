# config.py - Configuration constants for the MCP project

# LLM Configuration
DEFAULT_LLM = "qwen2.5:7b"

# Alternative LLM options (uncomment to use)
# DEFAULT_LLM = "llama3.3:70b"
# DEFAULT_LLM = "llama3.2:3b"
# DEFAULT_LLM = "llama3.1:8b" 
# DEFAULT_LLM = "qwen2.5:7b"
# DEFAULT_LLM = "qwen3:32b"
# DEFAULT_LLM = "openai/gpt-4o"  # For OpenAI API
# DEFAULT_LLM = "anthropic/claude-3-5-sonnet-20241022"  # For Anthropic API

# MCP Server Configuration
STOCK_SERVER_COMMAND = "stock_server.py"
CURRENCY_SERVER_COMMAND = "currency_server.py"

# Agent Configuration
MAX_EXECUTION_TIME = 120  # seconds
MAX_TOOL_ROUNDS = 3  # Maximum number of tool calling rounds
VERBOSE_MODE = True

# API Configuration
CURRENCY_API_BASE_URL = "https://api.exchangerate-api.com/v4/latest"

# Default currencies
DEFAULT_BASE_CURRENCY = "USD"
DEFAULT_TARGET_CURRENCY = "EUR"

# Tool descriptions for better LLM understanding
TOOL_INSTRUCTIONS = {
    "stock": "Use get_stock_price to get current stock prices. Use get_stock_info for detailed company information.",
    "currency": "Use convert_currency to convert amounts between currencies. Use get_exchange_rate for just the rate.",
    "general": "You must use the available tools to get real-time data. Do not describe what you would do - actually call the tools. Call one tool at a time."
}
# Local MCP Stock Price Assistant

A local implementation of Model Context Protocol (MCP) for real-time stock price retrieval using FastMCP, Ollama, and yfinance.

## Overview

This project demonstrates how to create an MCP server that provides stock market tools and integrate it with Ollama LLM to ensure real-time data retrieval instead of relying on training data.

## Components

- **`stock_server.py`**: FastMCP server providing stock price tools via yfinance
- **`agent.py`**: Direct FastMCP + Ollama integration for stock price queries
- **`test_mcp.py`**: Test script for validating MCP server functionality

## Features

- Real-time stock price retrieval using Yahoo Finance
- MCP server with two main tools:
  - `get_stock_price`: Returns current stock price for a symbol
  - `get_stock_info`: Returns detailed stock information (market cap, P/E ratio, etc.)
- Forces LLM to use tools instead of providing outdated training data

## Installation

```bash
# Install dependencies
uv sync
```

## Usage

### 1. Test MCP Server Connection

```bash
uv run test_mcp.py
```

This will test the MCP server connection and validate tool functionality.

### 2. Run the Stock Price Agent

```bash
uv run agent.py
```

This will start the agent that uses the MCP server to get Apple's current stock price.

### 3. Run MCP Server Standalone

```bash
uv run stock_server.py
```

This starts the MCP server in STDIO mode for external clients.

## How It Works

1. **MCP Server**: `stock_server.py` creates a FastMCP server with stock-related tools
2. **Tool Integration**: `agent.py` connects to the MCP server and converts tools to Ollama format
3. **Forced Tool Usage**: The agent implementation ensures Ollama uses real-time tools instead of training data
4. **Real-time Data**: yfinance fetches current stock prices from Yahoo Finance

## Example Output

```
Stock Price Assistant - Getting Apple stock price using MCP server...
Available MCP tools: ['get_stock_price', 'get_stock_info']
Initial response: role='assistant' content='' tool_calls=[...]
Tool call: get_stock_price with args: {'params': {'symbol': 'AAPL'}}
Tool result: {"symbol":"AAPL","price":211.18,"currency":"USD"}

=== FINAL RESULT ===
The current stock price for AAPL is $211.18 USD.
```

## Requirements

- Python 3.12+
- UV package manager
- Ollama with llama3.3:70b model

## Dependencies

- `fastmcp>=2.10.6`: MCP server/client implementation
- `mcp>=1.12.0`: Core MCP protocol
- `yfinance>=0.2.65`: Stock data source
- `ollama>=0.5.1`: LLM integration
- `pydantic>=2.11.7`: Data validation

## Architecture

The project uses a direct integration approach:
- FastMCP creates the MCP server with stock tools
- Ollama LLM receives properly formatted tools
- Tool calls are executed against the MCP server
- Real-time stock data is returned to the LLM for response generation

This ensures that stock prices are always current and not from the LLM's training data.
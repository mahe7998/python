# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a local MCP (Model Context Protocol) project that demonstrates stock price retrieval using FastMCP and integration with Ollama LLM. The project consists of several components:

- **stock_server.py**: FastMCP server providing stock price tools via yfinance
- **agent.py**: Direct FastMCP + Ollama integration for stock price queries
- **test_mcp.py**: Test script for validating MCP server functionality

## Common Commands

### Running the MCP Server
```bash
uv run stock_server.py
```

### Running the Agent
```bash
uv run agent.py
```

### Testing MCP Connection
```bash
uv run test_mcp.py
```

### Installing Dependencies
```bash
uv sync
```

## Architecture

### MCP Server Pattern
The project uses FastMCP to create an MCP server (`stock_server.py`) that exposes stock-related tools:
- `get_stock_price()`: Returns current stock price for a symbol
- `get_stock_info()`: Returns detailed stock information including market cap and P/E ratio

### Client Integration
The project demonstrates direct Ollama + FastMCP integration (`agent.py`) that:
- Connects to the MCP server using FastMCP Client
- Converts MCP tools to Ollama-compatible format
- Forces LLM to use real-time data instead of training data

### Data Models
Pydantic models define the API contracts:
- `StockPriceParams`/`StockPriceResponse` for price queries
- `StockInfoParams`/`StockInfoResponse` for detailed information

## Key Dependencies

- `fastmcp>=2.10.6`: MCP server/client implementation
- `mcp>=1.12.0`: Core MCP protocol
- `praisonaiagents[llm]>=0.0.144`: Agent framework
- `yfinance>=0.2.65`: Stock data source
- `ollama>=0.5.1`: LLM integration

## Development Notes

- All scripts expect Python 3.12+
- The MCP server runs via STDIO transport
- Stock data is fetched in real-time from Yahoo Finance
- Uses "llama3.3:70b" model through Ollama
- The agent implementation forces tool usage to prevent outdated stock prices
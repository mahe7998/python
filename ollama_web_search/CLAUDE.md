# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python project that integrates Ollama with web search capabilities using the `gpt-oss` library. The project enables AI models to perform web searches and browse web content through a custom browser interface.

## Architecture

The project consists of two main components:

### Core Components

1. **main.py**: Entry point that sets up the Ollama client and browser integration
   - Creates a Browser instance with web search capabilities
   - Defines tool functions (`browser_search`, `browser_open`, `browser_find`) that wrap the Browser API
   - Implements a chat loop with the GPT-OSS model, enabling tool usage for web searching
   - Handles tool calling and response processing

2. **web_search_gpt_oss_helper.py**: Browser implementation and web search functionality
   - `Browser` class: Main interface for web searching and content browsing
   - `Page` dataclass: Represents web pages with metadata, content, and links
   - `BrowserState`/`BrowserStateData`: Manages browsing session state and page history
   - Web content processing: Markdown link processing, text wrapping, and content formatting
   - Search result aggregation and display

### Key Features

- **Web Search**: Uses Ollama client's `web_search()` method to find relevant web content
- **Content Browsing**: Navigate through search results with numbered links
- **Page State Management**: Maintains a stack of visited pages for navigation
- **Content Processing**: Converts markdown links to numbered references, wraps text for display
- **Find Functionality**: Search for text patterns within loaded pages

## Development Commands

The project uses `uv` as the package manager:

- **Run the application**: `uv run main.py`
- **Install dependencies**: `uv add <package>`
- **Remove dependencies**: `uv remove <package>`
- **Sync environment**: `uv sync`
- **View dependency tree**: `uv tree`

## Dependencies

- **ollama**: Core client for interacting with Ollama models
- **gpt-oss**: Provides enhanced capabilities for the GPT-OSS model integration

## Python Requirements

- Python 3.12+ (required by gpt-oss library)
- The project is configured with `requires-python = ">=3.12"` in pyproject.toml

## Usage Pattern

The main script demonstrates a typical usage pattern:
1. Initialize Ollama client and Browser
2. Define tool functions that expose browser capabilities
3. Set up tool schemas for the AI model
4. Run chat loop with tool calling enabled
5. Process tool calls and return results to continue the conversation

The Browser class maintains state across tool calls, allowing for multi-step web research sessions where the AI can search, open specific results, and find information within pages.
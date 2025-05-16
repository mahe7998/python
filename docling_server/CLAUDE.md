# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands
- Run server: `python main.py --url [pdf_path]`
- Install dependencies: `pip install -r requirements.txt` or `pip install -e .`
- Debug: Run VS Code launch configuration "Python: docling server"

## Code Style Guidelines
- Imports: Group standard library, third-party, and local imports (separated by newlines)
- Types: Use type hints for all function parameters and return values
- Naming: snake_case for variables/functions, PascalCase for classes
- Error handling: Use try/except blocks with specific exception types
- Documentation: Add docstrings for classes and functions (as in DoclingPDFLoader)
- Format: Follow PEP 8 guidelines
- Path handling: Use pathlib.Path for file paths instead of string manipulation
- Global variables: Minimize use; when necessary, declare with global keyword
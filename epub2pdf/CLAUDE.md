# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TextEpub2PDF is a Python tool that converts text-based EPUB files to PDF with proper formatting and support for multiple languages, including Chinese, Japanese, and Korean (CJK). The tool extracts content from EPUB files, renders text as images with appropriate fonts, and combines them into a PDF.

## Key Files

- `textepub2pdf.py`: Main script that handles the EPUB to PDF conversion with CJK language support
- `epub2pdf.py`: Alternative conversion script with different implementation
- `main.py`: Entry point for the application

## Core Functionality

The conversion process works as follows:
1. Extract metadata, table of contents, and content from the EPUB file
2. Render text content as images with appropriate fonts (searching for system fonts with CJK support)
3. Combine images into a PDF file
4. Set PDF metadata and viewing options (direction, layout, etc.)

## Command Examples

### Run the converter with Chinese language support

```bash
python textepub2pdf.py path/to/file.epub -o output.pdf -d R2L
```

### Install required dependencies

```bash
pip install lxml Pillow img2pdf pikepdf fonttools
```

## Development Notes

- When working with font handling, test with the `get_system_fonts()` method in the `TextEpubToPdfConverter` class
- The text rendering is handled in the `text_to_image()` method
- Metadata extraction uses both the .opf and .ncx files within the EPUB
- For debugging font issues, enable the debug print statements in the font detection code
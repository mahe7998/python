# Markdown Translation with Ollama

This project provides functionality to translate markdown files using Ollama, a local large language model.

## Features

- Translate markdown files while preserving formatting, tables, and image references
- Support for large files by automatically chunking the content
- Configurable target language
- Configurable Ollama model

## Prerequisites

- Python 3.6+
- Ollama installed and running locally (default: http://localhost:11434)
- Required Python packages (see `requirements.txt`)

## Usage

### Direct Method

You can use the main script directly:

```bash
python main.py --markdown-file "path/to/your/file.md" --language "French" --ollama-model "granite3.2:8b"
```

### Using the Helper Script

Alternatively, use the provided helper script:

```bash
python translate_markdown.py --file "path/to/your/file.md" --language "French" --model "granite3.2:8b"
```

### Arguments

- `--file` or `--markdown-file`: Path to the markdown file to translate (required)
- `--language`: Target language for translation (default: "French")
- `--model` or `--ollama-model`: Ollama model to use (default: "granite3.2:8b")

## Example

To translate the example lab report to French:

```bash
python translate_markdown.py --file "output/Lucas TB report-with-text_imagerefs.md" --language "French"
```

The translated file will be saved as `output/Lucas TB report-with-text_imagerefs-french.md`.

## Supported Models

The script works with any Ollama model that supports translation. Recommended models:

- `llama3.3:70b` - High quality but requires more resources
- `granite3.2:8b` - Good balance of quality and resource usage

## Notes

- For large files, the script automatically splits the content into manageable chunks
- The translation preserves markdown formatting, tables, and image references
- Proper names and technical terms are preserved in their original language

# pymypdf

A simple Python script to convert PDF files to Markdown using PyMuPDF.

## Requirements

- Python 3.x
- Mac M4 (Apple Silicon) compatible

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python parse_pdf.py <path-to-pdf-file>
```

The script will create a Markdown file with the same name as the input PDF in the same directory.

### Example

```bash
python parse_pdf.py document.pdf
# Output: document.md
```

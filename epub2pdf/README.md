# TextEpub2PDF

A tool to convert text-based EPUB files to PDF with proper formatting and support for Chinese and other languages.

## Features

- Converts text-based EPUB files to PDF
- Extracts and preserves book metadata (title, author, publisher, etc.)
- Creates a table of contents based on the EPUB structure
- Automatically finds and uses fonts with CJK (Chinese, Japanese, Korean) support
- Supports different reading directions (left-to-right or right-to-left)
- Multiple page layout options

## Requirements

- Python 3.6+
- Required packages: lxml, Pillow, img2pdf, pikepdf

## Installation

```bash
# Install required packages
pip install lxml Pillow img2pdf pikepdf fonttools
```

## Usage

```bash
python textepub2pdf.py example.epub -o output.pdf

# For Chinese/Japanese books (right-to-left reading)
python textepub2pdf.py example.epub -o output.pdf -d R2L
```

### Command-line options

```
usage: textepub2pdf.py [-h] [-o OUTPUT_PATH] [-l {SinglePage,OneColumn,TwoColumnLeft,TwoColumnRight,TwoPageLeft,TwoPageRight}]
                        [-m {UseNone,UseOutlines,UseThumbs,FullScreen,UseOC,UseAttachments}] [-d {L2R,R2L}]
                        input_path

Convert text-based EPUB files to PDF with support for Chinese and other languages.

positional arguments:
  input_path            Path to the input EPUB file

options:
  -h, --help            show this help message and exit
  -o OUTPUT_PATH, --output OUTPUT_PATH
                        Path to the output PDF file. If not specified, the output file name is generated from the input file name.
  -l {SinglePage,OneColumn,TwoColumnLeft,TwoColumnRight,TwoPageLeft,TwoPageRight}, --pagelayout {SinglePage,OneColumn,TwoColumnLeft,TwoColumnRight,TwoPageLeft,TwoPageRight}
                        Page layout of the PDF file.
  -m {UseNone,UseOutlines,UseThumbs,FullScreen,UseOC,UseAttachments}, --pagemode {UseNone,UseOutlines,UseThumbs,FullScreen,UseOC,UseAttachments}
                        Page mode of the PDF file.
  -d {L2R,R2L}, --direction {L2R,R2L}
                        Reading direction of the PDF file. Use R2L for Chinese, Japanese, etc.
```

## Recommendations for Chinese Text

For optimal results with Chinese text:
1. Use the `-d R2L` option to set the reading direction to right-to-left
2. The program will automatically detect and use fonts with Chinese support
3. Verify the output PDF to ensure characters are displayed correctly

## License

GNU General Public License v3
#!/bin/bash
#
# md2pdf.sh - Convert Markdown to PDF and open in Preview
#
# This script takes a Markdown file as input, converts it to a temporary PDF
# using the readme_processor.py script, opens the PDF in Preview, and then
# cleans up the temporary file when Preview is closed.
#

# Ensure we have a file argument
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <markdown-file.md>"
    exit 1
fi

# Get the input file (absolute path)
INPUT_FILE=$(realpath "$1")

# Check if the file exists and is a Markdown file
if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: File '$INPUT_FILE' does not exist."
    exit 1
fi

if [[ ! "$INPUT_FILE" =~ \.(md|markdown)$ ]]; then
    echo "Error: File '$INPUT_FILE' is not a Markdown file (.md or .markdown)."
    exit 1
fi

# Directory where the script and md2pdf.py are located
SCRIPT_DIR="/Users/jmahe/projects/python/md2pdf"
PROCESSOR="${SCRIPT_DIR}/md2pdf.py"

# Check if the processor script exists
if [ ! -f "$PROCESSOR" ]; then
    echo "Error: The processor script '$PROCESSOR' does not exist."
    exit 1
fi

# Create a temporary file for the PDF output
TEMP_PDF=$(mktemp /tmp/md2pdf_XXXXXX.pdf)

echo "Converting '$INPUT_FILE' to PDF..."

# Run the conversion
cd "$SCRIPT_DIR" || exit 1
uv run python3 "$PROCESSOR" "$INPUT_FILE" "$TEMP_PDF"

# Check if conversion was successful
if [ ! -f "$TEMP_PDF" ]; then
    echo "Error: Failed to create PDF. Check your markdown file."
    exit 1
fi

echo "Opening PDF in Preview..."

# Open the PDF with the default application (Preview on macOS)
open "$TEMP_PDF"

# Wait for Preview to close (this is a bit tricky)
# We'll monitor for processes that have our temp file open
echo "PDF is open in Preview. Close it when you're done to clean up the temporary file."

# Small delay to ensure Preview has time to open the file
sleep 1

# Loop until the file is no longer in use
while lsof "$TEMP_PDF" >/dev/null 2>&1; do
    sleep 1
done

# Clean up the temporary file
echo "Cleaning up temporary PDF file..."
rm -f "$TEMP_PDF"

echo "Done."
exit 0

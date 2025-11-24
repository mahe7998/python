import pymupdf4llm
import argparse
import os

# Set up argument parser
parser = argparse.ArgumentParser(description='Convert PDF file to Markdown.')
parser.add_argument('--filename', type=str, required=True, help='The PDF file to convert.')

# Parse the arguments
args = parser.parse_args()

# Assign the parsed argument to a variable
filename = args.filename

# Remove the extension from the filename
filename = os.path.splitext(filename)[0]

filename = "Q4 People, Culture and Compensation Committee (March 7)"
md_text = pymupdf4llm.to_markdown(f"{filename}.pdf")

# now work with the markdown text, e.g. store as a UTF8-encoded file
import pathlib
pathlib.Path(f"{filename}.md").write_bytes(md_text.encode())

import fitz.table
import pymupdf
import argparse
import os
import fitz

# Set up argument parser
parser = argparse.ArgumentParser(description='Convert PDF file to Markdown.')
parser.add_argument('--filename', type=str, required=True, help='The PDF file to convert.')
parser.add_argument('--output_dir', type=str, required=False, help='The directory to save the PNG images.')
# Parse the arguments
args = parser.parse_args()

# Assign the parsed argument to a variable
filename = args.filename
output_dir = args.output_dir if args.output_dir else "pngs"

# Remove the extension from the filename
filename_no_ext = os.path.splitext(filename)[0]

# Create a directory named filename
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Convert all pages from PDF into PNG images using pymupdf
pdf_document = fitz.Document(filename)
for page in range(pdf_document.page_count):
    # Get the page
    page = pdf_document.load_page(page)
    
    # Convert the page to a PNG image
    print(f"Converting page {page} to PNG", end="\r")
    page.get_pixmap().save(f"{output_dir}/{filename_no_ext}_page_{page}.png")

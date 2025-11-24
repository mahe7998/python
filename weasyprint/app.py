from weasyprint import HTML

import sys
import os
import argparse

# Set up argument parser
parser = argparse.ArgumentParser(description='Convert a web URL to PDF.')
parser.add_argument('url', help='The URL to convert to PDF.')
parser.add_argument('-o', '--output', default='output.pdf', help='Output file name (default: output.pdf)')

if len(sys.argv) != 2:
    print("Usage: python app.py \"<URL>\" [-o output_file.pdf]")
    sys.exit(1)

args = parser.parse_args()
url = args.url
output_file = args.output

# Create potential folders if provided in the file name
output_dir = os.path.dirname(output_file)
if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Convert a web URL to PDF
HTML(url).write_pdf(output_file)  # from URL&#8203;:contentReference[oaicite:6]{index=6}

# Or convert an HTML string to PDF
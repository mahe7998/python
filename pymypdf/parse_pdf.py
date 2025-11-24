import pymupdf4llm
import pymupdf
import fitz
import pathlib
import sys

if len(sys.argv) < 2:
    print("Error: Please provide the path to the PDF file as a mandatory argument.")
    sys.exit(1)

pdf_path = sys.argv[1]
md_text = pymupdf4llm.to_markdown(pdf_path)
output_file_name = pathlib.Path(pdf_path).with_suffix('.md')
pathlib.Path(output_file_name).write_bytes(md_text.encode())
print(f"Markdown file created: {output_file_name}")

import os
import json
import re

from typing import List
from pathlib import Path
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document as LCDocument
from docling.document_converter import DocumentConverter
from docling.backend.docling_parse_backend import DoclingParseDocumentBackend
from docling.datamodel.base_models import InputFormat
from docling_core.types.doc import ImageRefMode, PictureItem, TableItem
from docling.datamodel.pipeline_options import (
    EasyOcrOptions,
    OcrMacOptions,
    PdfPipelineOptions,
    RapidOcrOptions,
    TesseractCliOcrOptions,
    TesseractOcrOptions,
    AcceleratorOptions
)
from docling.document_converter import DocumentConverter, PdfFormatOption#from langchain_huggingface import HuggingFaceEndpoint
from docling.datamodel.pipeline_options import granite_picture_description
from typing import Iterable, Dict, Any
import argparse
import os

def parse_args():
    parser = argparse.ArgumentParser(description="Process a PDF URL or query existing vector store.")
    parser.add_argument("--url", type=str, help="The URL of the PDF to process (optional)")
    parser.add_argument("--show-sources", action="store_true", help="Show the full content of sources")
    parser.add_argument("--debug", action="store_true", help="Show debug information")
    return parser.parse_args()

args = parse_args()

class DoclingPDFLoader(BaseLoader):

    def __init__(self) -> None:
        self._converter = DocumentConverter()

    def load(self, source: str) -> List[LCDocument]:
        dl_doc = self._converter.convert(source).document
        text = dl_doc.export_to_markdown()
        # Add source information to metadata
        metadata = {"source": source}
        # Get page information if available
        if hasattr(dl_doc, "pages") and dl_doc.pages:
            metadata["num_pages"] = len(dl_doc.pages)
        
        # Return a list containing a single document as per LangChain conventions
        return [LCDocument(page_content=text, metadata=metadata)]

def format_docs(docs: Iterable[LCDocument]):
    return "\n\n".join(doc.page_content for doc in docs)

def capture_and_format_docs(docs: Iterable[LCDocument]) -> Dict[str, Any]:
    """Capture the retrieved documents and format them for the LLM."""
    # Store the documents in the global space for later display
    global retrieved_docs
    retrieved_docs = list(docs)
    
    # Format the documents for the LLM
    formatted_text = format_docs(docs)
    return formatted_text

def is_header(entry):
    return entry.get("label") == "section_header"

def main():
    
    # Initialize global variable to store retrieved documents
    global retrieved_docs
    retrieved_docs = []
    
    try:
        # Determine if we're processing a new PDF or just querying existing data
        if args.url:
            print(f"Processing PDF from URL: {args.url}")

            # Set the number of threads for parallel processing
            os.environ["OMP_NUM_THREADS"] = "8"  # You can adjust the number of threads as needed
            accelerator_options = AcceleratorOptions()
            accelerator_options.num_threads = 8

            # Important: For operating with page images, we must keep them, otherwise the DocumentConverter
            # will destroy them for cleaning up memory.
            # This is done by setting PdfPipelineOptions.images_scale, which also defines the scale of images.
            # scale=1 correspond of a standard 72 DPI image
            # The PdfPipelineOptions.generate_* are the selectors for the document elements which will be enriched
            # with the image field
            pipeline_options = PdfPipelineOptions()
            pipeline_options.generate_page_images = False
            pipeline_options.generate_picture_images = True
            pipeline_options.do_picture_classification = False
            pipeline_options.do_picture_description = False
            #pipeline_options.picture_description_options = granite_picture_description
            pipeline_options.images_scale = 2
            pipeline_options.accelerator_options = accelerator_options
 
            doc_converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )

            conv_res = doc_converter.convert(args.url)

            output_dir = Path("output")
            current_folder = Path.cwd()
            output_dir = current_folder / output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            doc_filename = conv_res.input.file.stem

            # Save markdown with externally referenced pictures
            md_filename = output_dir / f"{doc_filename}-with-complete-metadata.md"
            conv_res.document.save_as_markdown(md_filename, image_mode=ImageRefMode.EMBEDDED)
            with open(md_filename, "r") as readfile:
                markdown_text = readfile.read()
                readfile.close()
            # Delete the markdown file with complete metadata as it's no longer needed
            if md_filename.exists():
                md_filename.unlink()

            json_complete_metada_filename = output_dir / f"{doc_filename}-with_complete-metadata.json"
            conv_res.document.save_as_json(json_complete_metada_filename, image_mode=ImageRefMode.EMBEDDED)

            # Load the JSON content we just saved
            jason_complete_metadata_file = open(json_complete_metada_filename)
            # returns JSON object as a dictionary
            json_content = json.load(jason_complete_metadata_file)
            json_text_image_metadata = []
            try:
                json_header_content = json_content["texts"]
                json_header_content = [entry for entry in json_header_content if is_header(entry)]
                json_picture_content = json_content["pictures"]
                #json_content.append({"label": "url", "text": args.url})
            except KeyError:
                print("Error: 'texts' or 'pictures' entry does not exist in the JSON content.")
            jason_complete_metadata_file.close();

            json_text_image_metadata.append({
                "url": args.url, 
                "headers": json_header_content, 
                "pictures": json_picture_content,
                "markdown": markdown_text,
            })
            # Export markdown to local folder
            output_folder = "output"
            os.makedirs(output_folder, exist_ok=True)
            json_with_text_image_filename = output_dir / f"{doc_filename}-with-text_image.json"
            with open(json_with_text_image_filename, "w") as outfile:
                outfile.write(json.dumps(json_text_image_metadata, indent=4))
                outfile.close()
            output_markdown_file = output_dir / f"{doc_filename}-with-text_image.md"
            with open(output_markdown_file, "w") as outfile:
                outfile.write(markdown_text)
                outfile.close()
        
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    try:
        main()
    finally:
        pass
 
import os
import json

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
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import granite_picture_description
from typing import Iterable, Dict, Any, List
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="Process a PDF URL or query existing vector store.")
    parser.add_argument("--url", type=str, help="The URL of the PDF to process (optional)")
    parser.add_argument("--show-sources", action="store_true", help="Show the full content of sources")
    parser.add_argument("--debug", action="store_true", help="Show debug information")
    return parser.parse_args()

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

def process_pdf_document(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Process a PDF document and extract structured data.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        List of dictionaries containing extracted metadata
    """
    try:
        print(f"Processing PDF: {pdf_path}")
        print(f"Current working directory: {os.getcwd()}")
        
        if not os.path.exists(pdf_path):
            print(f"ERROR: PDF file does not exist at path: {pdf_path}")
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        # Configure PyTorch to use MPS if available (Apple Silicon)
        try:
            import torch
            if torch.backends.mps.is_available():
                print("Using MPS (Metal Performance Shaders) for acceleration")
                os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
                # Torch should now use MPS by default
            else:
                print("MPS not available, using CPU")
        except (ImportError, AttributeError):
            print("PyTorch MPS support not available")
            
        # Set the number of threads for parallel processing
        print("Setting up parallel processing options...")
        os.environ["OMP_NUM_THREADS"] = "8"
        
        # Check for model cache path in multiple locations
        model_cache_paths = [
            Path("/app/models"),               # Docker path
            Path.home() / ".cache/docling",    # User home cache path
            Path.home() / ".docling",          # User home docling path
            Path("models")                      # Local models directory
        ]
        
        model_cache_found = False
        for model_cache_path in model_cache_paths:
            if model_cache_path.exists():
                print(f"Using model cache: {model_cache_path}")
                os.environ["DOCLING_CACHE_DIR"] = str(model_cache_path)
                model_cache_found = True
                break
                
        if not model_cache_found:
            print("No pre-downloaded model cache found. Models will be downloaded if needed.")
        
        # Create the accelerator options, optimized for local execution
        accelerator_options = AcceleratorOptions()
        accelerator_options.num_threads = 8

        # Configure pipeline options for optimal performance on local machine
        pipeline_options = PdfPipelineOptions()
        pipeline_options.generate_page_images = False
        pipeline_options.generate_picture_images = True
        pipeline_options.do_picture_classification = False
        pipeline_options.do_picture_description = False
        pipeline_options.images_scale = 2
        pipeline_options.accelerator_options = accelerator_options

        # Create document converter
        print("Creating document converter...")
        doc_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

        # Convert document
        print(f"Converting document: {pdf_path}")
        try:
            # Make sure the file exists and has the correct permissions
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF file not found at path: {pdf_path}")
                
            # Check file size
            file_size = os.path.getsize(pdf_path) / (1024 * 1024)  # Size in MB
            print(f"PDF file size: {file_size:.2f} MB")
            
            # Check file permissions
            file_stat = os.stat(pdf_path)
            print(f"File permissions: {oct(file_stat.st_mode)}")
            
            # Convert the document
            print(f"Starting document conversion with Docling...")
            conv_res = doc_converter.convert(pdf_path)
            print("Document converted successfully")
        except Exception as e:
            print(f"ERROR in document conversion: {str(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            raise

        # Setup output directory (flexible for both Docker and local execution)
        print("Setting up output directory...")
                    
        # Local environment
        output_dir = Path("output")
        
        print(f"Output directory path: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Get document filename
        doc_filename = conv_res.input.file.stem
        print(f"Document filename: {doc_filename}")

        # Save markdown with externally referenced pictures
        print("Saving markdown file...")
        md_filename = output_dir / f"{doc_filename}-with-complete-metadata.md"
        print(f"Markdown file path: {md_filename}")
        
        try:
            conv_res.document.save_as_markdown(md_filename, image_mode=ImageRefMode.EMBEDDED)
            print(f"Saved markdown file to: {md_filename}")
        except Exception as e:
            print(f"ERROR saving markdown: {str(e)}")
            raise
            
        # Read markdown content
        try:
            with open(md_filename, "r") as readfile:
                markdown_text = readfile.read()
                print(f"Read markdown file, size: {len(markdown_text)} bytes")
        except Exception as e:
            print(f"ERROR reading markdown: {str(e)}")
            raise
            
        # Delete the markdown file with complete metadata as it's no longer needed
        if md_filename.exists():
            md_filename.unlink()
            print(f"Deleted temporary markdown file: {md_filename}")

        # Save JSON with complete metadata
        print("Saving JSON with complete metadata...")
        json_complete_metada_filename = output_dir / f"{doc_filename}-with_complete-metadata.json"
        print(f"JSON complete metadata file path: {json_complete_metada_filename}")
        
        try:
            conv_res.document.save_as_json(json_complete_metada_filename, image_mode=ImageRefMode.EMBEDDED)
            print(f"Saved JSON metadata to: {json_complete_metada_filename}")
        except Exception as e:
            print(f"ERROR saving JSON metadata: {str(e)}")
            raise

        # Load the JSON content we just saved
        print("Loading JSON content...")
        try:
            with open(json_complete_metada_filename, "r") as jason_complete_metadata_file:
                json_content = json.load(jason_complete_metadata_file)
                print(f"Loaded JSON content, keys: {list(json_content.keys())}")
        except Exception as e:
            print(f"ERROR loading JSON content: {str(e)}")
            raise
        
        json_text_image_metadata = []
        
        # Extract header and picture content
        print("Extracting headers and pictures...")
        try:
            json_header_content = json_content["texts"]
            print(f"Found {len(json_header_content)} text entries")
            
            json_header_content = [entry for entry in json_header_content if is_header(entry)]
            print(f"Filtered to {len(json_header_content)} header entries")
            
            json_picture_content = json_content["pictures"]
            print(f"Found {len(json_picture_content)} picture entries")
            
        except KeyError as e:
            print(f"ERROR: Key not found in JSON content: {str(e)}")
            print(f"Available keys: {list(json_content.keys())}")
            json_header_content = []
            json_picture_content = []

        # Create final metadata structure
        print("Creating final metadata structure...")
        json_text_image_metadata.append({
            "url": pdf_path, 
            "headers": json_header_content, 
            "pictures": json_picture_content,
            "markdown": markdown_text,
        })
        
        # Export JSON with text and image
        print("Exporting JSON with text and image...")
        json_with_text_image_filename = output_dir / f"{doc_filename}-with-text_image.json"
        print(f"JSON with text and image file path: {json_with_text_image_filename}")
        
        try:
            with open(json_with_text_image_filename, "w") as outfile:
                json.dump(json_text_image_metadata, outfile, indent=4)
                print(f"Saved JSON with text and image to: {json_with_text_image_filename}")
        except Exception as e:
            print(f"ERROR saving JSON with text and image: {str(e)}")
            raise
        
        # Export markdown
        print("Exporting markdown...")
        output_markdown_file = output_dir / f"{doc_filename}-with-text_image.md"
        print(f"Output markdown file path: {output_markdown_file}")
        
        try:
            with open(output_markdown_file, "w") as outfile:
                outfile.write(markdown_text)
                print(f"Saved markdown to: {output_markdown_file}")
        except Exception as e:
            print(f"ERROR saving markdown: {str(e)}")
            raise
        
        print("Document processing completed successfully")
        
        # List all files in output directory to confirm
        try:
            print(f"Files in output directory: {[f.name for f in output_dir.iterdir()]}")
        except Exception as e:
            print(f"ERROR listing output directory: {str(e)}")
        
        return json_text_image_metadata
        
    except Exception as e:
        print(f"ERROR in process_pdf_document: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        raise

def main():
    args = parse_args()
    
    # Initialize global variable to store retrieved documents
    global retrieved_docs
    retrieved_docs = []
    
    try:
        # Determine if we're processing a new PDF or just querying existing data
        if args.url:
            process_pdf_document(args.url)
        
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    try:
        main()
    finally:
        pass
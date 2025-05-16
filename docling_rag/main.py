# Embedded Models tested:
# - BAAI/bge-small-en-v1.5
# - ibm-granite/granite-embedding-30m-english
# Ollama model: 
# - llama3.3:70b
# - granite3.2:8b

import os
from dotenv import dotenv_values
import atexit
import threading
import json
import re

config = dotenv_values(".env")
print(f"config: {config}")

from typing import List
from pathlib import Path
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document as LCDocument
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
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
#from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_milvus import Milvus
from typing import Iterable, Dict, Any
from langchain_milvus import Milvus
import signal
import sys
import argparse
import os

default_ollama_uri = "http://localhost:11434"
default_ollama_model = "granite3.2:8b"

def parse_args():
    global default_ollama_uri
    global default_ollama_model
    parser = argparse.ArgumentParser(description="Process a PDF URL or query existing vector store.")
    parser.add_argument("--collection", type=str, default="docling_docs", help="The name of the collection to use")
    parser.add_argument("--url", type=str, help="The URL of the PDF to process (optional)")
    parser.add_argument("--model", type=str, default="BAAI/bge-small-en-v1.5", help="The model to use for embeddings")
    parser.add_argument("--query", type=str, default="Porvide a summary of the paper?", 
                       help="Query to use when searching the vector store")
    parser.add_argument('--ollama-uri', type=str, default=default_ollama_uri, help='URI for the Ollama service')
    parser.add_argument('--ollama-model', type=str, default=default_ollama_model, help='Model to use with the Ollama service')
    parser.add_argument("--show-sources", action="store_true", help="Show the full content of sources")
    parser.add_argument("--debug", action="store_true", help="Show debug information")
    parser.add_argument("--max-refs", type=int, default=5, 
                       help="Maximum number of reference documents to retrieve (default: 5)")
    parser.add_argument('--answer-length', type=int, help='Desired answer length in number of words')
    parser.add_argument('--start-page', type=int, default=1, help='First page to process (default: 1)')
    parser.add_argument('--end-page', type=int, help='Last page to process (default: process all pages)')
    return parser.parse_args()

args = parse_args()

# Global variable to hold resources that need cleanup
_resources_to_clean = {}

def cleanup_resources():
    """Clean up any resources before program exit"""
    print("Cleaning up resources...")
    
    # Close Milvus connection if it exists
    if 'vectorstore' in _resources_to_clean:
        try:
            # Force close connection to release resources
            if hasattr(_resources_to_clean['vectorstore'], '_client'):
                _resources_to_clean['vectorstore']._client.close()
            print("Closed Milvus connection")
        except Exception as e:
            print(f"Error closing Milvus connection: {e}")
    
    # Clean up any other resources
    print("Cleanup complete")

# Function to cleanup TQDM resources
def cleanup_tqdm():
    # Close any remaining tqdm instances
    try:
        tqdm._instances.clear()
    except:
        pass

# Register the cleanup function to run on exit
atexit.register(cleanup_resources)
atexit.register(cleanup_tqdm)# Also handle termination signals

def signal_handler(sig, frame):
    print(f"Received signal {sig}, cleaning up...")
    cleanup_resources()
    cleanup_tqdm()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Custom exception handler for threading errors during shutdown
original_threading_excepthook = threading.excepthook

def custom_threading_excepthook(args):
    # If it's the shutdown error from tqdm, ignore it
    if isinstance(args.exc_value, RuntimeError) and "can't create new thread at interpreter shutdown" in str(args.exc_value):
        # Just suppress this specific error
        return
    # Otherwise, use the original handler
    original_threading_excepthook(args)

# Set our custom exception handler
threading.excepthook = custom_threading_excepthook

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

def display_source_documents(docs: List[LCDocument], show_full_content: bool = False):
    """Display information about the source documents."""
    print("\n" + "="*80)
    print(f"Sources used ({len(docs)} documents):")
    print("="*80)
    
    for i, doc in enumerate(docs, 1):
        print(f"\nSource {i}:")
        print(f"  Metadata: {json.dumps(doc.metadata, indent=4)}")
        
        if show_full_content:
            print("\n  Content:")
            print("  " + "\n  ".join(doc.page_content.split("\n")[:20]))
            if len(doc.page_content.split("\n")) > 20:
                print("  ... (content truncated)")
        else:
            # Show just a snippet of the content
            content_preview = doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
            print(f"  Content preview: {content_preview}")
        
        print("-"*40)

def is_header(entry):
    return entry.get("label") == "section_header"

def main():
    # Configure Milvus connection to an external server
    MILVUS_HOST = "localhost"
    MILVUS_PORT = "9091"
    
    # Initialize global variable to store retrieved documents
    global retrieved_docs
    retrieved_docs = []
    
    embeddings = HuggingFaceEmbeddings(model_name=args.model)
    
    print(f"Connecting to Milvus server at {MILVUS_HOST}:{MILVUS_PORT}")
    # Connect to existing Milvus collection
    vectorstore = Milvus(
        embedding_function=embeddings,
        collection_name=args.collection,
        connection_args={"host": MILVUS_HOST, "port": MILVUS_PORT},
        auto_id=True,
        index_params={"index_type": "AUTOINDEX"}
    )
    # Store vectorstore in global resources for cleanup
    _resources_to_clean['vectorstore'] = vectorstore
    print("Connected to existing vector store")
    print(f"Vector store: {vectorstore}")
    
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
            ocr_options = EasyOcrOptions(lang=['ch_tra', 'en'])  # Traditional Chinese with English
            pipeline_options = PdfPipelineOptions()
            pipeline_options.ocr_options = ocr_options
            pipeline_options.ocr_options.use_gpu = True
            pipeline_options.generate_page_images = True
            pipeline_options.generate_picture_images = True
            pipeline_options.do_picture_classification = False
            pipeline_options.do_picture_description = False
            #pipeline_options.picture_description_options = granite_picture_description
            pipeline_options.images_scale = 2
            pipeline_options.accelerator_options = accelerator_options
            
            # Set page range if specified
            if args.start_page > 1 or args.end_page is not None:
                print(f"Processing pages from {args.start_page} to {args.end_page if args.end_page else 'end'}")
                pipeline_options.page_range = (args.start_page, args.end_page) if args.end_page else (args.start_page, None)

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

            # Save page images
            for page_no, page in conv_res.document.pages.items():
                page_no = page.page_no
                page_image_filename = output_dir / f"{doc_filename}-{page_no}.png"
                with page_image_filename.open("wb") as fp:
                    page.image.pil_image.save(fp, format="PNG")

            # Save markdown with externally referenced pictures
            md_filename = output_dir / f"{doc_filename}-with-complete-metadata.md"
            conv_res.document.save_as_markdown(md_filename, image_mode=ImageRefMode.REFERENCED)
            with open(md_filename, "r") as readfile:
                markdown_text = readfile.read()
                readfile.close()
            # Delete the markdown file with complete metadata as it's no longer needed
            if md_filename.exists():
                md_filename.unlink()

            # Convert markdown picture absolute references to relative references
            def convert_to_relative_path(match):
                absolute_path = match.group(1)
                relative_path = os.path.relpath(absolute_path, output_dir)
                return f"![Image]({relative_path})"
            markdown_text = re.sub(r'!\[Image\]\((.*?)\)', convert_to_relative_path, markdown_text)

            json_complete_metada_filename = output_dir / f"{doc_filename}-with_complete-metadata.json"
            conv_res.document.save_as_json(json_complete_metada_filename, image_mode=ImageRefMode.REFERENCED)

            # Load the JSON content we just saved
            jason_complete_metadata_file = open(json_complete_metada_filename)
            # returns JSON object as a dictionary
            json_content = json.load(jason_complete_metadata_file)
            json_text_imageref_metadata = []
            try:
                json_header_content = json_content["texts"]
                json_header_content = [entry for entry in json_header_content if is_header(entry)]
                json_picture_content = json_content["pictures"]
                json_text_imageref_metadata.append({"url": args.url, "headers": json_header_content, "pictures": json_picture_content})
                #json_content.append({"label": "url", "text": args.url})
            except KeyError:
                print("Error: 'texts' or 'pictures' entry does not exist in the JSON content.")
            jason_complete_metadata_file.close();

            # Export markdown to local folder
            output_folder = "output"
            os.makedirs(output_folder, exist_ok=True)
            json_with_text_imagerefs_filename = output_dir / f"{doc_filename}-with-text_imagerefs.json"
            with open(json_with_text_imagerefs_filename, "w") as outfile:
                outfile.write(json.dumps(json_text_imageref_metadata, indent=4))
                outfile.close()
            output_markdown_file = output_dir / f"{doc_filename}-with-text_imagerefs.md"
            with open(output_markdown_file, "w") as outfile:
                outfile.write(markdown_text)
                outfile.close()

            # Split the markdown text into chunks
            # See https://python.langchain.com/docs/how_to/markdown_header_metadata_splitter/
            splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=[
                    ("#", "Header_1"),
                    ("##", "Header_2"),
                    ("###", "Header_3"),
                ],
            )
            splits = splitter.split_text(markdown_text)
            print(f"Generated {len(splits)} document chunks")

            # Now enhance the metadata of the splits before adding to vector store
            enhanced_splits = []
            for split in splits:
                # Get existing metadata (which already contains headers from MarkdownHeaderTextSplitter)
                metadata = split.metadata.copy()

                # Add page number if available in the original document metadata
                if hasattr(split, 'metadata'):
                    # Try to determine page from content or header references
                    # Default to page 1 if can't determine
                    page = 1
                    bbox = None
                    page_match = False
                    
                    # If your headers contain page references (like "Chapter 1, Page 5"),
                    # you could extract them here with regex
                    for header_key in ["Header_1", "Header_2", "Header_3"]:
                        if header_key in metadata and metadata[header_key]:
                            header_title = metadata[header_key]
                            # Replace "&amp;" with "&" in header title if it exists
                            if "&amp;" in header_title:
                                header_title = header_title.replace("&amp;", "&")

                            # Example: Look for page numbers in headers
                            for header_entry in json_text_imageref_metadata[0]['headers']:
                                if header_entry['text'] == header_title:
                                    page = header_entry['prov'][0]['page_no']
                                    bbox = header_entry['prov'][0]['bbox']
                                    page_match = True
                                    break
                            if not page_match:
                                break

                    metadata["file"] = doc_filename
                    if page_match:
                        metadata["page"] = page
                        metadata["bbox"] = bbox
                    else:
                        metadata["page"] = 1
                        metadata["bbox"] = { "l": 0, "t": 0, "r": 0, "b": 0, "coord_origin": "BOTTOMLEFT" }

                # Create a new document with enhanced metadata
                # Check if the content is only an image reference
                content = split.page_content.strip()
                # Skip documents that only contain image references (like "![Image](path/to/image.png)")
                if re.match(r'^!\[.*?\]\(.*?\)$', content):
                    print(f"Skipping image-only content: {content[:50]}...")
                    continue
                if re.match(r'^\s*!\[.*?\]\(.*?\)\s*$', content):
                    print(f"Skipping image-only content with whitespace: {content[:50]}...")
                    continue
                enhanced_splits.append(
                    LCDocument(
                        page_content=split.page_content,
                        metadata=metadata
                    )
                )
                
            vectorstore.add_documents(enhanced_splits)
        
        ollama_llm = OllamaLLM(model=args.ollama_model, base_url=args.ollama_uri)

        # Set up the retriever with the max_ref parameter from command line
        retriever = vectorstore.as_retriever(
            search_kwargs={
                "k": args.max_refs,  # Use the max_ref argument here
                "fetch_k": max(args.max_refs * 2, args.max_refs * 2),  # Fetch more candidates before filtering
                "include_metadata": True  # Make sure to include all metadata
            }
        )
        
        prompt = PromptTemplate.from_template(
            "Context information is below.\n---------------------\n{context}\n---------------------\nGiven the context information and not prior knowledge, answer the query.\nQuery: {question}\nAnswer:\n"
        )

        rag_chain = (
            {
                "context": retriever | capture_and_format_docs, 
                "question": RunnablePassthrough()
            }
            | prompt
            | ollama_llm
            | StrOutputParser()
        )

        query = args.query
        if args.answer_length:
            query += f" Provide an answer using approximately {args.answer_length} words."
        print(f"\nQuerying: {query}")
        response = rag_chain.invoke(query)
        print("\nRAG Response:")
        print(response)
        
        # Display the source documents
        if retrieved_docs:
            display_source_documents(retrieved_docs, show_full_content=args.show_sources)
        
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    try:
        main()
    finally:
        # Ensure resources are cleaned up even if main() raises an exception
        cleanup_resources()
        cleanup_tqdm()

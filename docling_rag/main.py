import os
from dotenv import dotenv_values
import atexit
import json

config = dotenv_values(".env")
print(f"config: {config}")

from typing import List
from pathlib import Path
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document as LCDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
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
)
from docling.document_converter import DocumentConverter, PdfFormatOption#from langchain_huggingface import HuggingFaceEndpoint
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

def parse_args():
    parser = argparse.ArgumentParser(description="Process a PDF URL or query existing vector store.")
    parser.add_argument("--collection", type=str, default="docling_docs", help="The name of the collection to use")
    parser.add_argument("--url", type=str, help="The URL of the PDF to process (optional)")
    parser.add_argument("--model", type=str, default="BAAI/bge-small-en-v1.5", help="The model to use for embeddings")
    parser.add_argument("--query", type=str, default="What is the main idea of the paper?", 
                       help="Query to use when searching the vector store")
    parser.add_argument("--show-sources", action="store_true", help="Show the full content of sources")
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

# Register the cleanup function to run on exit
atexit.register(cleanup_resources)

# Also handle termination signals
def signal_handler(sig, frame):
    print(f"Received signal {sig}, cleaning up...")
    cleanup_resources()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

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
        print(f"  Metadata: {json.dumps(doc.metadata, indent=2)}")
        
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
    
    print(f"Connecting to Milvus server at {MILVUS_HOST}:{MILVUS_PORT}")
    
    embeddings = HuggingFaceEmbeddings(model_name=args.model)
    
    try:
        # Determine if we're processing a new PDF or just querying existing data
        if args.url:
            print(f"Processing PDF from URL: {args.url}")

            # Important: For operating with page images, we must keep them, otherwise the DocumentConverter
            # will destroy them for cleaning up memory.
            # This is done by setting PdfPipelineOptions.images_scale, which also defines the scale of images.
            # scale=1 correspond of a standard 72 DPI image
            # The PdfPipelineOptions.generate_* are the selectors for the document elements which will be enriched
            # with the image field
            pipeline_options = PdfPipelineOptions()
            pipeline_options.generate_page_images = True
            pipeline_options.generate_picture_images = True

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

            # Save images of figures
            picture_counter = 0
            for element, _ in conv_res.document.iterate_items():
                if isinstance(element, PictureItem):
                    picture_counter += 1
                    element_image_filename = (
                        output_dir / f"{doc_filename}-picture-{picture_counter}.png"
                    )
                    with element_image_filename.open("wb") as fp:
                        element.get_image(conv_res.document).save(fp, "PNG")

            # Save markdown with externally referenced pictures
            md_filename = output_dir / f"{doc_filename}-with-image-refs.md"
            conv_res.document.save_as_markdown(md_filename, image_mode=ImageRefMode.REFERENCED)
            markdown_text = conv_res.document.export_to_markdown()

            json_filename = output_dir / f"{doc_filename}-with-image-refs.json"
            conv_res.document.save_as_json(json_filename, image_mode=ImageRefMode.REFERENCED)

            # Load the JSON content we just saved
            jason_file = open(json_filename)
            # returns JSON object as a dictionary
            json_content = json.load(jason_file)
            json_metadata = []
            try:
                json_header_content = json_content["texts"]
                json_header_content = [entry for entry in json_header_content if is_header(entry)]
                json_picture_content = json_content["pictures"]
                json_metadata.append({"url": args.url, "headers": json_header_content, "pictures": json_picture_content})
                #json_content.append({"label": "url", "text": args.url})
            except KeyError:
                print("Error: 'texts' or 'pictures' entry does not exist in the JSON content.")
            jason_file.close();

            # Export markdown to local folder
            output_folder = "output"
            os.makedirs(output_folder, exist_ok=True)
            output_file_path = os.path.join(output_folder, "document.json")
            with open(output_file_path, "w") as outfile:
                outfile.write(json.dumps(json_metadata, indent=4))
                outfile.close();

            # Split the markdown text into chunks
            # See https://python.langchain.com/docs/how_to/markdown_header_metadata_splitter/
            #loader = DoclingPDFLoader()
            splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=[
                    ("#", "Header_1"),
                    ("##", "Header_2"),
                    ("###", "Header_3"),
                ],
            )
            splits = splitter.split_text(markdown_text)
            print(f"Generated {len(splits)} document chunks")
            file_name = Path(args.url).name
            file_name = ''.join(e for e in file_name if e.isalnum() or e == '_')
            vectorstore = Milvus.from_documents(
                documents=splits,
                embedding=embeddings,
                connection_args={"host": MILVUS_HOST, "port": MILVUS_PORT},
                collection_name=args.collection,
                drop_old=True
            )
            # Store vectorstore in global resources for cleanup
            _resources_to_clean['vectorstore'] = vectorstore
            print("Added new documents to vector store")
            print(f"Vector store: {vectorstore}")

        else:
            print("No URL provided. Connecting to existing vector store...")
            # Connect to existing Milvus collection
            vectorstore = Milvus(
                embedding_function=embeddings,
                collection_name=args.collection,
                connection_args={"host": MILVUS_HOST, "port": MILVUS_PORT}
            )
            # Store vectorstore in global resources for cleanup
            _resources_to_clean['vectorstore'] = vectorstore
            print("Connected to existing vector store")
            print(f"Vector store: {vectorstore}")
        
        
        OLLAMA_URI = "http://localhost:11434"
        ollama_llm = OllamaLLM(model="llama3.3:70b", base_url=OLLAMA_URI)

        # Set up the retriever with a higher k value to see more documents
        retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
        
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

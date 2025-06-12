# This script processes a PDF document, extracts text, tables and images and creates an md file to translate original PDF content
# Ollama model: 
# - llama3.3:70b
# - granite3.2:8b

import os
from dotenv import dotenv_values
import re

config = dotenv_values(".env")
print(f"config: {config}")

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
#from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_text_splitters import MarkdownHeaderTextSplitter
from typing import Iterable, Dict, Any
import signal
import sys
import argparse
import os

default_ollama_uri = "http://localhost:11434"
default_ollama_model = "granite3.2:8b"

def parse_args():
    global default_ollama_uri
    global default_ollama_model
    parser = argparse.ArgumentParser(description="Translate a PDF URL or markdown file.")
    parser.add_argument("file", type=str, help="Path to the markdown file to translate")
    parser.add_argument("--language", type=str, default="French", help="Target language for translation")
    parser.add_argument('--ollama-uri', type=str, default=default_ollama_uri, help='URI for the Ollama service')
    parser.add_argument('--ollama-model', type=str, default=default_ollama_model, help='Ollama Model to use with the translation')
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
        if args.file:
            print(f"Processing PDF from URL: {args.file}")

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
            pipeline_options.generate_page_images = True
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

            conv_res = doc_converter.convert(args.file)

            output_dir = Path("output")
            current_folder = Path.cwd()
            output_dir = current_folder / output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            doc_filename = conv_res.input.file.stem

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

            # Export markdown to local folder
            output_folder = "output"
            os.makedirs(output_folder, exist_ok=True)
            output_markdown_file = output_dir / f"{doc_filename}-with-text_imagerefs.md"
            with open(output_markdown_file, "w") as outfile:
                outfile.write(markdown_text)
                outfile.close()
            
            # Set the markdown file for translation
            args.markdown_file = str(output_markdown_file)
        
        # Initialize Ollama LLM
        ollama_llm = OllamaLLM(model=args.ollama_model, base_url=args.ollama_uri)
        
        # If a markdown file is specified, translate it
        if args.markdown_file:
            print(f"Translating markdown file: {args.markdown_file}")
            
            # Read the markdown file with error handling for different encodings
            markdown_text = ""
            encodings_to_try = ["utf-8", "latin-1", "windows-1252", "iso-8859-1"]
            
            for encoding in encodings_to_try:
                try:
                    with open(args.markdown_file, "r", encoding=encoding) as file:
                        markdown_text = file.read()
                    print(f"Successfully read file using {encoding} encoding")
                    break
                except UnicodeDecodeError:
                    print(f"Failed to read file with {encoding} encoding, trying next...")
                    if encoding == encodings_to_try[-1]:
                        # If we've tried all encodings and none worked, raise an error
                        raise ValueError(f"Could not read file {args.markdown_file} with any of the attempted encodings: {encodings_to_try}")
            
            if not markdown_text:
                print(f"Error: Could not read file {args.markdown_file}")
                return
            
            # Create a translation prompt
            prompt_template = ChatPromptTemplate.from_messages(
                [
                    ("system", f"Translate the following text to {args.language}. Preserve all markdown formatting, tables, and image references. Do not translate proper names or technical terms that should remain in their original language."),
                    ("user", "{text}")
                ]
            )
            
            # Split the markdown text into chunks if it's too large
            # This is a simple approach - for very large files, a more sophisticated chunking strategy might be needed
            max_chunk_size = 4000  # Adjust based on model's context window
            chunks = []
            
            if len(markdown_text) > max_chunk_size:
                # Use markdown headers as natural splitting points
                headers_splitter = MarkdownHeaderTextSplitter(
                    headers_to_split_on=[
                        ("#", "header1"),
                        ("##", "header2"),
                        ("###", "header3"),
                        ("####", "header4"),
                    ]
                )
                split_docs = headers_splitter.split_text(markdown_text)
                
                # If the splitting by headers doesn't work well (e.g., no headers), fall back to simple chunking
                if not split_docs or len(split_docs) == 1:
                    # Simple chunking by paragraphs
                    paragraphs = markdown_text.split("\n\n")
                    current_chunk = ""
                    
                    for para in paragraphs:
                        if len(current_chunk) + len(para) + 2 <= max_chunk_size:
                            if current_chunk:
                                current_chunk += "\n\n"
                            current_chunk += para
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = para
                    
                    if current_chunk:
                        chunks.append(current_chunk)
                else:
                    # Use the header-based splits
                    current_chunk = ""
                    for doc in split_docs:
                        if len(current_chunk) + len(doc.page_content) + 2 <= max_chunk_size:
                            if current_chunk:
                                current_chunk += "\n\n"
                            current_chunk += doc.page_content
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = doc.page_content
                    
                    if current_chunk:
                        chunks.append(current_chunk)
            else:
                chunks = [markdown_text]
            
            # Translate each chunk
            translated_chunks = []
            for i, chunk in enumerate(chunks):
                print(f"Translating chunk {i+1}/{len(chunks)}...")
                
                prompt_value = prompt_template.invoke({
                    "text": chunk
                })
                
                translated_chunk = ollama_llm.invoke(prompt_value)
                translated_chunks.append(translated_chunk)
            
            # Combine the translated chunks
            translated_text = "\n\n".join(translated_chunks)
            
            # Save the translated text to a new file
            output_path = Path(args.markdown_file)
            translated_file = output_path.parent / f"{output_path.stem}-{args.language.lower()}{output_path.suffix}"
            
            with open(translated_file, "w", encoding="utf-8") as file:
                file.write(translated_text)
            
            print(f"Translation completed and saved to: {translated_file}")
        else:
            # Example translation (for testing)
            prompt_template = ChatPromptTemplate.from_messages(
                [
                    ("system", "Translate the text from English to {language}."),
                    ("user", "{text}")
                ]
            )

            prompt_value = prompt_template.invoke({
                "language": args.language,
                "text": "I am a software engineer."
            })

            result = ollama_llm.invoke(prompt_value)
            print(f"Translation result: {result}")
        
    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        main()
    finally:
        # Clean up any resources or temporary files if needed
        pass

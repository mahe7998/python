from langchain_community.document_loaders import PDFPlumberLoader
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_ollama import ChatOllama
from langchain.chains import sql_database
from langchain.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain.prompts import ChatPromptTemplate, PromptTemplate
from langchain.retrievers.multi_query import MultiQueryRetriever

import argparse

# Set up argument parser
parser = argparse.ArgumentParser(description='Add PDF file content to Chroma DB.')
parser.add_argument('--llm', type=str, required=False, help='The name of the language model to use.')
parser.add_argument('--pdf', type=str, required=False, help='The PDF file to process.')
parser.add_argument('--db', type=str, required=False, help='The directory to persist the Chroma database.')

# Parse the arguments
args = parser.parse_args()

# Assign the parsed arguments to variables
MODEL = args.llm if args.llm else "deepseek-r1:70b"
pdf_file = args.pdf if args.pdf else "./pdfs/Universal-declaration-of-human-rights.pdf"
persist_directory = args.db if args.db else "chroma_dir"

embeddings = OllamaEmbeddings(model=MODEL)

# Write DB
def load_pdf(pdf_file):
    loader = PDFPlumberLoader(pdf_file)
    documents = loader.load()
    return documents

# Load documents from PDF
documents = load_pdf(pdf_file)

pages = []
source_metadata = []
for doc in documents:
    pages.append(doc.page_content)
    source_metadata.append( {"source": f"{doc.metadata['source']} - {doc.metadata['page']}"} )

vector_db = Chroma.from_texts(pages, embeddings, metadatas=source_metadata , persist_directory=persist_directory)
print("DB created")


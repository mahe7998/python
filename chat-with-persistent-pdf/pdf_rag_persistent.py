# from langchain_core.vectorstores import Chroma  
# from langchain_core.embeddings import OpenAIEmbeddings  
# from langchain_core.llms import OpenAI  
# from langchain_core.text_splitter import CharacterTextSplitter  

# # Initialize the embeddings model  
# embeddings = OpenAIEmbeddings(api_key='your_openai_api_key')  

# # Create a Chroma vector store  
# vector_store = Chroma(  
#     embedding_function=embeddings.embed_query,  
#     persist_directory="chroma_dir"  # Directory to persist the Chroma database  
# )  

# # Sample documents to add to the vector store  
# documents = [  
#     "LangChain is a framework for developing applications powered by language models.",  
#     "ChromaDB provides efficient storage and retrieval for vector embeddings.",  
#     "Using embeddings, you can find semantically similar documents."  
# ]  

# # Add documents to the vector store  
# for doc in documents:  
#     vector_store.add_texts([doc])  

# # Querying the vector store  
# query = "What is LangChain?"  
# results = vector_store.similarity_search(query, k=2)  # k is the number of similar documents to return  

# # Display the results  
# for result in results:  
#     print(result)


import streamlit as st

from langchain_community.document_loaders import PDFPlumberLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.vectorstores import Chroma
#from langchain_core.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

template = """
You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know. Provide a detailed answer with relevant examples.
Question: {question} 
Context: {context} 
Answer:
"""

pdfs_directory = './pdfs/'

#embeddings = OllamaEmbeddings(model="hf.co/bartowski/DeepSeek-R1-Distill-Qwen-14B-GGUF:Q5_K_L")
embeddings = OllamaEmbeddings(model="deepseek-r1:70b")

vector_db = Chroma.from_texts(documents, embeddings, metadatas=None)
#model = OllamaLLM(model="hf.co/bartowski/DeepSeek-R1-Distill-Qwen-14B-GGUF:Q5_K_L")
model = OllamaLLM(model="deepseek-r1:70b")

def upload_pdf(file):
    with open(pdfs_directory + file.name, "wb") as f:
        f.write(file.getbuffer())

def load_pdf(file_path):
    loader = PDFPlumberLoader(file_path)
    documents = loader.load()
    return documents


#def index_docs(documents):
#    vector_store.add_documents(documents)

def retrieve_docs(query):
    return vector_store.similarity_search(query)

def answer_question(question, documents):
    context = "\n\n".join([doc.page_content for doc in documents])
    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | model
    return chain.invoke({"question": question, "context": context})

uploaded_file = st.file_uploader(
    "Upload PDF",
    type="pdf",
    accept_multiple_files=False
)

if uploaded_file:
    upload_pdf(uploaded_file)
    documents = load_pdf(pdfs_directory + uploaded_file.name)
    chunked_documents = split_text(documents)
#   index_docs(chunked_documents)

    question = st.chat_input()

    if question:
        st.chat_message("user").write(question)
        related_documents = retrieve_docs(question)
        answer = answer_question(question, related_documents)
        st.chat_message("assistant").write(answer)



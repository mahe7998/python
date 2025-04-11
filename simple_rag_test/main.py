from langchain_huggingface import HuggingFaceEmbeddings
from transformers import AutoTokenizer
from langchain_ollama.llms import OllamaLLM
from langchain.document_loaders import TextLoader
from langchain_milvus import Milvus
from langchain.text_splitter import CharacterTextSplitter
from langchain.prompts import PromptTemplate
from langchain.chains.retrieval import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain

import os
import wget
import atexit
import argparse

# Configure Milvus connection to an external server
MILVUS_HOST = "localhost"
MILVUS_PORT = "9091"
vector_db = None

# Register cleanup function to ensure proper Milvus cleanup
def cleanup_resources():
    try:
        # Close Milvus connection if possible
        if hasattr(vector_db, '_milvus_client') and vector_db._milvus_client is not None:
            vector_db._milvus_client.close()
    except Exception as e:
        print(f"Warning: Error during cleanup: {e}")

# Register the cleanup function to run at exit
atexit.register(cleanup_resources)

def main():
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--embedding_model', type=str, required=False, help='Path to the embedding model', 
                        default="ibm-granite/granite-embedding-30m-english")
    
    # Parse the arguments
    args = parser.parse_args()
    
    # Use the argument in your code
    embedding_model_path = args.embedding_model
    print(f'Using embedding model from: {embedding_model_path}')
    embeddings_model = HuggingFaceEmbeddings(
        model_name=embedding_model_path,
    )
    embeddings_tokenizer = AutoTokenizer.from_pretrained(embedding_model_path)
    print("Tokenizer done")

    model = OllamaLLM(model="granite3.2:8b")
    print("Model done")
    # Get the tokenizer for the Granite model from HuggingFace
    tokenizer = AutoTokenizer.from_pretrained("ibm-granite/granite-3.2-8b-instruct")
    print("Granite Tokenizer done")

    filename = 'state_of_the_union.txt'
    url = 'https://raw.githubusercontent.com/IBM/watson-machine-learning-samples/master/cloud/data/foundation_models/state_of_the_union.txt'
    if not os.path.isfile(filename):
        wget.download(url, out=filename)

    loader = TextLoader(filename)
    documents = loader.load()
    text_splitter = CharacterTextSplitter.from_huggingface_tokenizer(
        tokenizer=embeddings_tokenizer,
        chunk_size=embeddings_tokenizer.max_len_single_sentence,
        chunk_overlap=0,
    )
    texts = text_splitter.split_documents(documents)
    for doc_id, text in enumerate(texts):
        text.metadata["doc_id"] = doc_id
    print(f"\n{len(texts)} text document chunks created")

    vector_db = Milvus(
        embedding_function=embeddings_model,
        connection_args={"host": MILVUS_HOST, "port": MILVUS_PORT},
        collection_name="state_of_the_union",
        auto_id=True,
        index_params={"index_type": "AUTOINDEX"}
    )
   
    # ids = vector_db.add_documents(texts)
    # print(f"{len(ids)} documents added to the vector database")
    
    query = "What did the president say about president Zelenskyy?"
    docs = vector_db.similarity_search(query)
    print(f"{len(docs)} documents returned")
    for doc in docs:
        print(doc)
        print("=" * 80)  # Separator for clarity

    # Create a Granite prompt for question-answering with the retrieved context
    prompt = tokenizer.apply_chat_template(
        conversation=[{
            "role": "user",
            "content": "{input}",
        }],
        documents=[{
            "title": "placeholder",
            "text": "{context}",
        }],
        add_generation_prompt=True,
        tokenize=False,
    )
    prompt_template = PromptTemplate.from_template(template=prompt)

    # Create a Granite document prompt template to wrap each retrieved document
    document_prompt_template = PromptTemplate.from_template(template="""\
    Document {doc_id}
    {page_content}""")
    document_separator="\n\n"

    # Assemble the retrieval-augmented generation chain
    combine_docs_chain = create_stuff_documents_chain(
        llm=model,
        prompt=prompt_template,
        document_prompt=document_prompt_template,
        document_separator=document_separator,
    )
    rag_chain = create_retrieval_chain(
        retriever=vector_db.as_retriever(),
        combine_docs_chain=combine_docs_chain,
    )
    output = rag_chain.invoke({"input": query})
    print(output['answer'])
    
    # Explicitly call cleanup to ensure resources are released
    cleanup_resources()

if __name__ == "__main__":
    main()

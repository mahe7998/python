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
parser = argparse.ArgumentParser(description='Query prevous PDF file content using Chroma DB.')
parser.add_argument('--llm', type=str, required=False, help='The name of the language model to use.')
parser.add_argument('--query', type=str, required=False, help="""
Can you have workers and not pay them?
""")
parser.add_argument('--db', type=str, required=False, help='The directory to persist the Chroma database.')

# Parse the arguments
args = parser.parse_args()

# Assign the parsed arguments to variables
MODEL = args.llm if args.llm else "deepseek-r1:70b"
persist_directory = args.db if args.db else "chroma_dir"
user_input = args.query if args.query else "Can you have workers and not pay them?"

def get_vector_db():
    embedding = OllamaEmbeddings(model=MODEL)
    db = Chroma(
        persist_directory=persist_directory,
        embedding_function=embedding
    )
    return db


# Convert the database into a retriever
chroma_database = get_vector_db()

template = """Answer the question based only on the following context:
{context}

Question: {question}
"""

QUERY_PROMPT = PromptTemplate(
        input_variables=["question"],
        template="""You are an AI language model assistant. Your task is to generate five
        different versions of the given user question to retrieve relevant documents from
        a vector database. By generating multiple perspectives on the user question, your
        goal is to help the user overcome some of the limitations of the distance-based
        similarity search. Provide these alternative questions separated by newlines.
        Original question: {question}""",
    )

# Use the template to build a prompt
prompt = ChatPromptTemplate.from_template(template)

# Define the data processing chain
llm = ChatOllama(model=MODEL)

retriever = MultiQueryRetriever.from_llm(
            chroma_database.as_retriever(), 
            llm,
            prompt=QUERY_PROMPT
 )

chain = (
    { "context": retriever, "question": RunnablePassthrough() }
    | prompt
    | llm
    | StrOutputParser()
)

# Execute the pipeline
print(chain.invoke(user_input))
# response = chain.invoke(user_input, stream=True)
# for output in response:
#     print(output)


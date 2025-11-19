import os
import tempfile
import textwrap

import streamlit as st
import torch
from dotenv import load_dotenv
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_openai import ChatOpenAI
from langchain_community.embeddings import HuggingFaceEmbeddings

# Disable ChromaDB telemetry to avoid errors
os.environ["ANONYMIZED_TELEMETRY"] = "False"

# Load environment variables
load_dotenv()

st.set_page_config(page_title="LLM App Example", page_icon="🦜")


def main():
    st.title("LLM App Example")
    st.title("PDF Question Answering App")
    st.text("Before ask your question, upload a PDF " "file as knowledge source.")
    st.text("We will answer your question firstly" " base on the PDF you upload")
    st.text("If can't find the answer, we will" " responde by pre-trained LLM")
    uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

    if uploaded_file is not None:
        # Create a temporary file to store the uploaded PDF
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.write(uploaded_file.read())
        document_path = temp_file.name  # Use the temp file path
        loader = PyPDFLoader(document_path)
        documents = loader.load_and_split()
        text_splitter = CharacterTextSplitter(chunk_size=1200, chunk_overlap=25)
        docs = text_splitter.split_documents(documents)
        # Use HuggingFace embeddings (free, no API key needed)
        # Specify device to avoid meta tensor issues
        device = "cuda" if torch.cuda.is_available() else "cpu"
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            model_kwargs={"device": device},
            encode_kwargs={"normalize_embeddings": True}
        )
        vector_store = Chroma.from_documents(docs, embeddings)
        template = textwrap.dedent(
            """
       You are a very helpful assistant. You must answer the questions in \
ENGLISH or Chinese based on Question language.
        Instructions:
        - All information in your answers if contained in PDF, should get \
from PDF, if not, should get answer from model yourself
        - In case the question cannot be answered using the information \
provided in the PDF, honestly state that you cannot answer that question.
        - Be detailed in your answers but stay focused on the question.\
Add all details that are useful to provide a complete answer, but do not\
add details beyond the scope of the question.
        PDF Context: {context}
        Question: {question}
        Helpful Answer:  """
        )

        QA_CHAIN_PROMPT = PromptTemplate(
            input_variables=["context", "question"], template=template
        )

        # Configure DeepSeek API
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not deepseek_api_key:
            st.error("⚠️ DEEPSEEK_API_KEY is not set. Please set it in your .env file or environment variables.")
            st.info("Get your API key from: https://platform.deepseek.com/")
            st.stop()
        
        llm = ChatOpenAI(
            model="deepseek-chat",
            openai_api_base="https://api.deepseek.com",
            openai_api_key=deepseek_api_key,
            temperature=0.5
        )

        retriever = vector_store.as_retriever()

        qa = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=retriever,
            return_source_documents=True,
            chain_type_kwargs={"prompt": QA_CHAIN_PROMPT},
        )

        question = st.text_input("Ask a question:")
        chat_history = []
        if question:
            chat_history.append(QA_CHAIN_PROMPT)
            result = qa.invoke({"query": question, "chat_history": chat_history})
            answer = result["result"]
            st.subheader("Answer")
            st.write(answer)
            chat_history.append(answer)


if __name__ == "__main__":
    main()

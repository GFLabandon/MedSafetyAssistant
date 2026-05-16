"""
LangChain RAG 对照 Demo
目标：在不改主项目架构前提下，快速跑通标准 RAG 流程。

流程：TextLoader -> OllamaEmbeddings -> FAISS -> RetrievalQA
运行：python examples/langchain_rag_demo.py
"""

from pathlib import Path

from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

BASE_DIR = Path(__file__).resolve().parent
DOC_PATH = BASE_DIR / "demo_med_faq.txt"


def build_qa_chain() -> RetrievalQA:
    loader = TextLoader(str(DOC_PATH), encoding="utf-8")
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=220, chunk_overlap=40)
    chunks = splitter.split_documents(docs)

    embeddings = OllamaEmbeddings(
        model="mxbai-embed-large:latest",
        base_url="http://localhost:11434",
    )
    vector_db = FAISS.from_documents(chunks, embeddings)
    retriever = vector_db.as_retriever(search_kwargs={"k": 3})

    prompt = PromptTemplate(
        input_variables=["context", "question"],
        template=(
            "你是用药安全助手。仅基于给定资料回答，不要编造。\n\n"
            "资料:\n{context}\n\n问题: {question}\n回答:"
        ),
    )

    llm = Ollama(model="qwen2.5-coder:14b", base_url="http://localhost:11434", temperature=0.1)
    return RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        chain_type_kwargs={"prompt": prompt},
    )


def main() -> None:
    qa = build_qa_chain()
    question = "我有高血压，感冒时能不能随便吃复方感冒药和退烧药？"
    result = qa.invoke({"query": question})

    print("=" * 60)
    print("[Question]", question)
    print("[Answer]", result.get("result", ""))
    print("=" * 60)


if __name__ == "__main__":
    main()

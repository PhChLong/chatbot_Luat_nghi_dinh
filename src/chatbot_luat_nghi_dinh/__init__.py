from pathlib import Path

import numpy as np
import torch
from langchain_core.documents import Document

from .chunking import chunk_documents, split_document, turn_files_into_documents
from .deepagent import Agent
from .embedding import ProxyAITeamVNEmbeddingManager
from .rag import RAGRetrieval
from .reranking import ProxyAITeamVNReranker
from .sqlite_db import SQLiteDB
from .tools import LegalTools
from .vector_db import VectorDB

CHUNK_SIZE: int = 1000
CHUNK_OVERLAP: int = 200

device = (
    "cuda"
    if torch.cuda.is_available()
    else "mps"
    if torch.backends.mps.is_available()
    else "cpu"
)

embedding_manager = ProxyAITeamVNEmbeddingManager(device=device)
vector_store = VectorDB(Path("data/vector_db"))
retriever = RAGRetrieval(vector_db=vector_store, embedding_manager=embedding_manager)
reranker = ProxyAITeamVNReranker(device=device)
sqlite_store: SQLiteDB = SQLiteDB(Path("data/legal.sqlite3"))
legal_tools: LegalTools = LegalTools(sqlite_store, retriever, reranker)


#@ Lưu toàn văn và chunk vào SQLite, đồng bộ cùng ID vào Chroma.
def update_vector_database() -> None:
    print("Hello from chatbot-luat-nghi-dinh!")
    documents: list[Document] = turn_files_into_documents(Path("data/md"))
    if not documents:
        raise ValueError("Không có Markdown trong data/md; chưa thay đổi index")
    sections: list[Document] = split_document(documents)
    chunks: list[Document] = chunk_documents(
        sections, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    if not chunks:
        raise ValueError("Không tạo được chunk; chưa thay đổi index")

    texts_from_chunks: list[str] = [chunk.page_content for chunk in chunks]
    embeddings: np.ndarray = embedding_manager.generate_embeddings(texts_from_chunks)
    sqlite_store.save_documents(documents, sections, chunks)
    vector_store.add_documents(documents=chunks, embeddings=embeddings)


#@ Dùng chung search tool với filter hiệu lực luôn bật, giữ dạng kết quả cũ.
def query(question: str) -> list[tuple[dict, float]]:
    assert isinstance(question, str)

    reranked_results: list[tuple[dict, float]] = [
        (chunk, chunk["rerank_score"]) for chunk in legal_tools.search(question)
    ]
    for chunk, score in reranked_results:
        print(chunk["content"][:50])
        print(score)
    return reranked_results


def chatbot() -> None:
    agent = Agent()
    while True:
        prompt : str = input(">>>")
        if prompt == "\\exit":
            break
        agent.invoke(prompt)

from pathlib import Path

import torch
from langchain_core.documents import Document

from .chunking import process_all
from .deepagent import Agent
from .embedding import ProxyAITeamVNEmbeddingManager
from .rag import RAGRetrieval
from .reranking import ProxyAITeamVNReranker
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


# @ Khởi tạo model embedding và in kết quả mã hóa văn bản mẫu.
def update_vector_database() -> None:
    print("Hello from chatbot-luat-nghi-dinh!")
    chunks: list[Document] = process_all(
        Path("data/md"), chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )

    texts_from_chunks: list[str] = [chunk.page_content for chunk in chunks]
    embeddings = embedding_manager.generate_embeddings(texts_from_chunks)
    vector_store.add_documents(documents=chunks, embeddings=embeddings)


def query(question: str) -> list[tuple[dict, float]]:
    assert isinstance(question, str)

    related_chunks = retriever.query(question=question, top_k=20)
    reranked_results: list[tuple[dict, float]] = reranker.rerank(
        query=question, docs=related_chunks, top_k=5
    )
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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import torch

from .chunking import sync_chroma
from .database import sync_database
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


def sync(
    metadata_path: str | Path = "data/metadata.json",
    html_path: str | Path = "data/html",
    database_path: str | Path = "legal_units.db",
) -> dict:
    """Chạy đồng thời SQLite và Chroma, mỗi nhánh tự cập nhật cờ riêng.

    sync=[SQLite, Chroma]. Lỗi được trả về kèm tên văn bản và document_id.
    Chỉ chạy một tiến trình sync; không chạy crawler đồng thời trên JSON này.
    """
    results = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = {
            "sqlite": executor.submit(sync_database, metadata_path, html_path, database_path),
            "chroma": executor.submit(
                sync_chroma, embedding_manager, vector_store, metadata_path, html_path,
                CHUNK_SIZE, CHUNK_OVERLAP,
            ),
        }
        for branch, future in jobs.items():
            try:
                results[branch] = future.result()
            except Exception as exc:
                results[branch] = {"synced": [], "errors": [{"error": str(exc)}]}
            for error in results[branch]["errors"]:
                print(f"[{branch}] {error}")
    return results


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
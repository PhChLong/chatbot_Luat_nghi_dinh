import os
from pathlib import Path

import chromadb
import numpy as np
from chromadb import Collection
from chromadb.api.types import Metadata
from langchain_core.documents import Document


class VectorDB:
    def __init__(self, consistent_path: Path, collection_name: str = "luat-nghi-dinh"):
        self.consistent_path = consistent_path
        self.collection_name = collection_name
        self.client, self.collection = self._init_store()

    def _init_store(self):
        try:
            os.makedirs(self.consistent_path, exist_ok=True)
            client = chromadb.PersistentClient(self.consistent_path)
            collection: Collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={
                    "description": "Lưu lại các luật nghị định, cả embedding và text gốc"
                },
            )
            return client, collection

        except Exception as e:
            print(f"Error initializing vector store: {e}")
            raise

    #@ Đồng bộ snapshot chunk của các văn bản đầu vào, dùng cùng ID với SQLite.
    def add_documents(self, documents: list[Document], embeddings: np.ndarray) -> None:
        if len(documents) != len(embeddings):
            raise ValueError("Số chunk và embedding không khớp")
        if not documents:
            return
        ids: list[str] = [doc.metadata["chunk_id"] for doc in documents]
        if len(ids) != len(set(ids)):
            raise ValueError("Trùng chunk_id trong lần ingest")
        metadatas: list[Metadata] = [
            {**doc.metadata, "content_length": len(doc.page_content)} for doc in documents
        ]
        names: list[str] = sorted({doc.metadata["name"] for doc in documents})
        old_ids: list[str] = self.collection.get(
            where={"name": {"$in": names}}, include=[]
        )["ids"]
        batch_size: int = self.client.get_max_batch_size()
        start: int
        for start in range(0, len(documents), batch_size):
            self.collection.upsert(
                ids=ids[start:start + batch_size],
                embeddings=embeddings[start:start + batch_size].tolist(),
                metadatas=metadatas[start:start + batch_size],
                documents=[doc.page_content for doc in documents[start:start + batch_size]],
            )
        #? Chỉ bỏ chunk cũ sau khi ghi xong toàn bộ chunk mới của các văn bản này.
        current_ids: set[str] = set(ids)
        stale_ids: list[str] = [value for value in old_ids if value not in current_ids]
        for start in range(0, len(stale_ids), batch_size):
            self.collection.delete(ids=stale_ids[start:start + batch_size])

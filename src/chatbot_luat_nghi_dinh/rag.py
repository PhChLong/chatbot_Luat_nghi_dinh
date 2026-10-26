from typing import Any

import numpy as np
from chromadb.api.types import Metadata, QueryResult, Where

from .embedding import EmbeddingManager
from .vector_db import VectorDB


class RAGRetrieval:
    def __init__(
        self, vector_db: VectorDB, embedding_manager: EmbeddingManager
    ) -> None:
        self.vector_db = vector_db
        self.embedding_manager = embedding_manager

    #@ Tìm tối đa top_k chunk theo ngữ nghĩa trong phạm vi metadata được lọc.
    def query(
        self, question: str, top_k: int = 5, where: Where | None = None
    ) -> list[dict[str, Any]]:
        embeded_question: np.ndarray = self.embedding_manager.generate_embeddings(
            [question]
        )[0]
        result: QueryResult = self.vector_db.collection.query(
            query_embeddings=[embeded_question], n_results=top_k, where=where
        )
        retrieved_docs: list[dict[str, Any]] = []
        if (
            result["documents"] and result["documents"][0]
        ):  # ? vì chỉ hỏi một câu hỏi nên cũng chỉ cần lấy list documents đầu tiên
            ids: list[str] = result["ids"][0]
            documents: list[str] = (result["documents"] or [[]])[0]
            metadatas: list[Metadata | None] = (result["metadatas"] or [[]])[0]
            distances: list[float] = (result["distances"] or [[]])[0]

            id: str
            doc: str
            metadata: Metadata | None
            distance: float
            for i, (id, doc, metadata, distance) in enumerate(
                zip(ids, documents, metadatas, distances)
            ):
                retrieved_docs.append(
                    {
                        "id": id,
                        "content": doc,
                        "metadata": metadata,
                        "similarity": 1 - distance,
                        "rank": i + 1,
                    }
                )

        return retrieved_docs

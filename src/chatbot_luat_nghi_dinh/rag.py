from typing import Any

import numpy as np

from .embedding import EmbeddingManager
from .vector_db import VectorDB


class RAGRetrieval:
    def __init__(
        self, vector_db: VectorDB, embedding_manager: EmbeddingManager
    ) -> None:
        self.vector_db = vector_db
        self.embedding_manager = embedding_manager

    #@ Tìm chunk bằng embedding, có thể giới hạn vào các ID đã qua lọc SQLite.
    def query(
        self, question: str, top_k: int = 5, ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        if top_k < 1:
            raise ValueError("top_k phải lớn hơn 0")
        if ids == []:
            return []
        count: int = self.vector_db.collection.count()
        if count == 0:
            return []
        embeded_question: np.ndarray = self.embedding_manager.generate_embeddings(
            [question]
        )[0]
        result = self.vector_db.collection.query(
            query_embeddings=[embeded_question],
            n_results=min(top_k, count, len(ids) if ids is not None else count),
            ids=ids,
        )
        retrieved_docs: list[dict[str, Any]] = []
        if (
            result["documents"] and result["documents"][0]
        ):  # ? vì chỉ hỏi một câu hỏi nên cũng chỉ cần lấy list documents đầu tiên
            ids = result["ids"][0]
            documents = (result["documents"] or [[]])[0]
            metadatas = (result["metadatas"] or [[]])[0]
            distances = (result["distances"] or [[]])[0]

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

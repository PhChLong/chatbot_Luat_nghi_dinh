from .vector_db import VectorDB
from .embedding import EmbeddingManager
import numpy as np
from typing import Any

class RAGRetrieval:
    def __init__(self, vector_db: VectorDB, embedding_manager: EmbeddingManager) -> None:
        self.vector_db = vector_db
        self.embedding_manager = embedding_manager

    def query(self, question: str, top_k: int = 5) -> list:
        embeded_question: np.ndarray = self.embedding_manager.generate_embeddings([question])
        result = self.vector_db.collection.query(
            query_embeddings= [embeded_question],
            n_results=top_k
        )
        retrieved_docs:list[dict[str, Any]] = []
        if result['documents'] and result['documents'][0]: #? vì chỉ hỏi một câu hỏi nên cũng chỉ cần lấy list documents đầu tiên
            ids = result['ids'][0]
            documents = (result['documents'] or [[]])[0]
            metadatas = (result['metadatas'] or [[]])[0]
            distance = (result['distances'] or [[]])[0]

            for i, (id, doc, metadata, distance) in enumerate(zip(ids, documents, metadatas, distance)):
                retrieved_docs.append({
                    "id": id,
                    "content": doc,
                    "metadata": metadata,
                    "similarity": 1 - distance,
                    "rank": i+1,
                })

        return retrieved_docs

        
        

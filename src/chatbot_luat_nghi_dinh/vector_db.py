import os
import uuid
from collections.abc import Sequence
from pathlib import Path

import chromadb
import numpy as np
from chromadb import Collection
from chromadb.api.types import Metadata
from langchain_core.documents import Document


class VectorDB:
    def __init__(self, consistent_path:Path, collection_name:str = "luật nghị định"):
        self.consistent_path = consistent_path
        self.collection_name = collection_name
        self.client, self.collection = self._init_store()

    def _init_store(self):
        try:
            os.makedirs(self.consistent_path, exist_ok= True)
            client = chromadb.PersistentClient(self.consistent_path)
            collection : Collection = client.get_or_create_collection(
                name= self.collection_name,
                metadata={"description": "Lưu lại các luật nghị định, cả embedding và text gốc"}
            )
            return client, collection

        except Exception as e:
            print(f"Error initializing vector store: {e}")
            raise

    def add_documents(self, documents: list[Document], embeddings: np.ndarray):
        assert len(documents) == len(embeddings)
        # self.collection.add()
        ids :list[str] = []
        metadatas:list[Metadata] = []
        documents_text: list[str] = []
        embeddings_list:list[Sequence[float]] = []

        for i, (doc, emb) in enumerate(zip(documents, embeddings)):
            # id = f"{doc.metadata['nghi_dinh']}_d{doc.metadata['dieu']}_k{doc.metadata['khoan']}"
            ids.append(f"{uuid.uuid4().hex}_{i}")
            metadata = dict(doc.metadata)
            metadata["doc_index"] = i
            metadata["content_length"] = len(doc.page_content)
            metadatas.append(metadata)
            documents_text.append(doc.page_content)
            embeddings_list.append(emb.tolist())
            
        self.collection.add(
            ids = ids,
            embeddings= embeddings_list,
            metadatas= metadatas,
            documents= documents_text
        )


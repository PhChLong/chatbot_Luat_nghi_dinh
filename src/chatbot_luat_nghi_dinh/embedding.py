
from abc import ABC, abstractmethod

import numpy as np
from sentence_transformers import SentenceTransformer


class EmbeddingManager(
    ABC
):  # ? Quản lý model SentenceTransformer và tạo embedding cho văn bản
    # @ Mã hóa tập văn bản đầu vào và trả về các vector embedding.
    @abstractmethod
    def generate_embeddings(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError


class AITeamVNEmbeddingManage(EmbeddingManager):
    # @ Lưu cấu hình và nạp model embedding khi khởi tạo.
    def __init__(self, device: str = "cuda"):
        self.model_name = "AITeamVN/Vietnamese_Embedding"
        self.device = device
        self.model = self._load_model()

    def _load_model(self) -> SentenceTransformer:
        try:
            return SentenceTransformer(self.model_name, device=self.device)
        except Exception as e:
            print(f"Error loading model {self.model_name}: {e}")
            raise

    def generate_embeddings(self, texts: list[str]) -> np.ndarray:
        print(f"Generating embeddings for {len(texts)} texts...")
        embeddings: np.ndarray = self.model.encode(texts, show_progress_bar=True)
        print(f"Generated embeddings with shape: {embeddings.shape}")
        return embeddings


class ProxyAITeamVNEmbeddingManager(EmbeddingManager):
    def __init__(self, device: str = "cuda"):
        self.model_name = "AITeamVN/Vietnamese_Embedding"
        self.device = device
        self._real_manager: AITeamVNEmbeddingManage | None = None

    def generate_embeddings(self, texts: list[str]) -> np.ndarray:
        if self._real_manager is None:
            self._real_manager = AITeamVNEmbeddingManage(device=self.device)
        return self._real_manager.generate_embeddings(texts)

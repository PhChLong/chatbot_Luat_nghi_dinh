import numpy as np
from sentence_transformers import SentenceTransformer


class EmbeddingManager:  #? Quản lý model SentenceTransformer và tạo embedding cho văn bản.
    #@ Lưu cấu hình và nạp model embedding khi khởi tạo.
    def __init__(self, model_name: str = "AITeamVN/Vietnamese_Embedding", device:str = "cpu"):
        self.model_name = model_name
        self.device = device
        self.model: SentenceTransformer = self._load_model()

    #@ Nạp model theo tên đã cấu hình và báo lỗi nếu nạp thất bại.
    def _load_model(self):
        try:
            return SentenceTransformer(self.model_name, device = self.device)
        except Exception as e:
            print(f"Error loading model {self.model_name}: {e}")
            raise

    #@ Mã hóa tập văn bản đầu vào và trả về các vector embedding.
    def generate_embeddings(self, texts: list[str]) -> np.ndarray:
        print(f"Generating embeddings for {len(texts)} texts...")
        embeddings :np.ndarray = self.model.encode(texts, show_progress_bar=True)
        print(f"Generated embeddings with shape: {embeddings.shape}")
        return embeddings

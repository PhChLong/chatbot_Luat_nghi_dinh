from sentence_transformers import SentenceTransformer

class EmbeddingManager:
    def __init__(self, model_name: str = "AITeamVN/Vietnamese_Embedding", device:str = "cpu"):
        self.model_name = model_name
        self.device = device
        self.model: SentenceTransformer = self._load_model()

    def _load_model(self):
        try:
            return SentenceTransformer(self.model_name)
        except Exception as e:
            print(f"Error loading model {self.model_name}: {e}")
            raise


    def generate_embeddings(self, texts):
        print(f"Generating embeddings for {len(texts)} texts...")
        embeddings = self.model.encode(texts, show_progress_bar=True)
        print(f"Generated embeddings with shape: {embeddings.shape}")
        return embeddings


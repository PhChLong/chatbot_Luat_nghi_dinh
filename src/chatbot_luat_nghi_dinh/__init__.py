from .embedding import EmbeddingManager
from dotenv import load_dotenv
load_dotenv()

device = "mps"
def main() -> None:
    print("Hello from chatbot-luat-nghi-dinh!")
    embedding_manager = EmbeddingManager(device = device)
    embedding = embedding_manager.generate_embeddings("Xin chào tôi là người Việt Nam")
    print(embedding.shape)


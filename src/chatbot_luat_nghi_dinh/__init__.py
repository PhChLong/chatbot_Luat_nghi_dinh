from .embedding import EmbeddingManager
from .chunking import process_all
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

device = "mps"
#@ Khởi tạo model embedding và in kết quả mã hóa văn bản mẫu.
def main() -> None:
    print("Hello from chatbot-luat-nghi-dinh!")
    # embedding_manager = EmbeddingManager(device = device)
    # embedding = embedding_manager.generate_embeddings("Xin chào tôi là người Việt Nam")
    # print(embedding.shape)
    chunks = process_all(Path("../data/md"))
    print(len(chunks))


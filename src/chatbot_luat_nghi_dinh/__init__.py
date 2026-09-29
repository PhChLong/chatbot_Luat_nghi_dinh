from .embedding import EmbeddingManager
from .chunking import process_all
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.documents import Document
from .vector_db import VectorDB
import torch
load_dotenv()

device = (
    "cuda" if torch.cuda.is_available()
    else "mps" if torch.backends.mps.is_available()
    else "cpu"
)

#@ Khởi tạo model embedding và in kết quả mã hóa văn bản mẫu.
def main() -> None:
    print("Hello from chatbot-luat-nghi-dinh!")
    chunks:list[Document] = process_all(Path("data/md"))
    embedding_manager = EmbeddingManager(device = device)
    vector_db = VectorDB(Path("data/vector_db"))
    texts_from_chunks: list[str] = [chunk.page_content for chunk in chunks]
    embeddings = embedding_manager.generate_embeddings(texts_from_chunks)
    vector_db.add_documents(documents=chunks, embeddings=embeddings)

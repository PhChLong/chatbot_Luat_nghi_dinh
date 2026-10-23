from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .database import mark_synced, parse_html, read_metadata


def turn_html_into_documents(metadata: dict, html_path: str | Path = "data/html") -> list[Document]:
    """Mỗi Document chứa toàn văn một điều, bao gồm các khoản và điểm."""
    source = Path(html_path) / (metadata["name"] + ".html")
    parsed = parse_html(source)
    return [
        Document(
            page_content="\n".join(article["parts"]),
            metadata={
                "document_id": metadata["document_id"],
                "name": metadata["name"],
                "source": str(source),
                "article": article["label"],
                "section_kind": "PROV-ARTICLE",
            },
        )
        for article in parsed["articles"]
    ]


def chunk_documents(
    sections_from_all_documents: list[Document],
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[Document]:
    """Chia từng điều thành chunk; không chủ động tách ở khoản hoặc điểm."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""], length_function=len,
    )
    return splitter.split_documents(sections_from_all_documents)


def process_all(
    metadata_path: str | Path = "data/metadata.json",
    html_path: str | Path = "data/html",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[Document]:
    """Chuẩn bị chunk cho những văn bản có sync[1]=false, chưa đổi cờ."""
    chunks = []
    for metadata in read_metadata(metadata_path):
        if not metadata["sync"][1]:
            chunks.extend(chunk_documents(
                turn_html_into_documents(metadata, html_path), chunk_size, chunk_overlap
            ))
    return chunks


def sync_chroma(
    embedding_manager,
    vector_store,
    metadata_path: str | Path = "data/metadata.json",
    html_path: str | Path = "data/html",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> dict:
    """Chunk theo điều, embedding và upsert; hoàn tất mới đổi sync[1].

    ID theo document_id và vị trí chunk giúp thử lại sau lỗi không nhân đôi.
    Chưa hỗ trợ refresh nội dung đã sync hoặc dọn chunk từ pipeline cũ.
    """
    result = {"synced": [], "errors": []}
    for metadata in read_metadata(metadata_path):
        if metadata["sync"][1]:
            continue
        document_id = metadata["document_id"]
        try:
            chunks = chunk_documents(
                turn_html_into_documents(metadata, html_path), chunk_size, chunk_overlap
            )
            if not chunks:
                raise ValueError("Không có chunk để ghi vào Chroma.")
            for start in range(0, len(chunks), 128):
                batch = chunks[start:start + 128]
                vectors = embedding_manager.generate_embeddings([doc.page_content for doc in batch])
                if len(vectors) != len(batch):
                    raise ValueError("Số embedding không khớp số chunk.")
                vector_store.collection.upsert(
                    ids=[f"document_{document_id}_chunk_{start + i}" for i in range(len(batch))],
                    documents=[doc.page_content for doc in batch],
                    metadatas=[dict(doc.metadata, doc_index=start + i,
                                    content_length=len(doc.page_content))
                               for i, doc in enumerate(batch)],
                    embeddings=[vector.tolist() for vector in vectors],
                )
            mark_synced(metadata_path, document_id, 1)
            result["synced"].append(document_id)
        except Exception as exc:
            result["errors"].append({"document_id": document_id, "name": metadata["name"], "error": str(exc)})
    return result

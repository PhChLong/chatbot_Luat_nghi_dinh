from typing import Any

from langchain_core.tools import StructuredTool

from .rag import RAGRetrieval
from .reranking import Reranker
from .sqlite_db import SQLiteDB


class LegalTools:
    #@ Dùng lại retriever và reranker hiện có, thêm kho tra cứu chính xác.
    def __init__(
        self, db: SQLiteDB, retriever: RAGRetrieval, reranker: Reranker
    ) -> None:
        self.db: SQLiteDB = db
        self.retriever: RAGRetrieval = retriever
        self.reranker: Reranker = reranker

    #@ Lọc hiệu lực trước retrieval rồi rerank 20 ứng viên để lấy 5 kết quả.
    def search(
        self, query: str, filters: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        """Tìm nội dung còn hiệu lực theo metadata nguồn. Filters: so_hieu, document_type, article."""
        if not query.strip():
            raise ValueError("Query không được rỗng")
        ids: list[str] = self.db.eligible_chunk_ids(filters)
        if not ids:
            return []
        candidates: list[dict[str, Any]] = self.retriever.query(
            query, top_k=20, ids=ids
        )
        if not candidates:
            return []
        return [
            {**chunk, "rerank_score": score}
            for chunk, score in self.reranker.rerank(query, candidates, top_k=5)
        ]

    #@ Tra toàn văn Điều gốc; metadata trả kèm để người gọi kiểm tra hiệu lực.
    def get_article(self, so_hieu: str, dieu: str) -> dict[str, Any]:
        """Lấy chính xác Điều theo số hiệu văn bản và số Điều, không dùng embedding."""
        article: dict[str, Any] | None = self.db.get_article(so_hieu, dieu)
        return {"status": "ok", **article} if article else {"status": "not_found"}

    #@ Mở rộng chunk thành toàn bộ Điều chứa nó.
    def expand(self, chunk_id: str) -> dict[str, Any]:
        """Lấy toàn văn Điều chứa chunk. Không ghép các chunk có overlap."""
        chunk: dict[str, Any] | None = self.db.get_chunk(chunk_id)
        if chunk is None:
            return {"status": "not_found"}
        if chunk["article_number"] is None:
            return {"status": "no_article", "content": chunk["content"]}
        return self.get_article(chunk["document_id"], chunk["article_number"])

    #@ Tra các quan hệ đã được nhập và giữ rõ trạng thái thiếu dữ liệu.
    def get_relations(self, so_hieu: str) -> dict[str, Any]:
        """Tra quan hệ văn bản đã lưu; no_data nghĩa là chưa có dữ liệu, không phải không có quan hệ."""
        items: list[dict[str, Any]] = self.db.get_relations(so_hieu)
        return {"status": "ok" if items else "no_data", "items": items}

    #@ Chỉ lấy quan hệ có loại amends trong bảng quan hệ.
    def get_amendments(self, so_hieu: str) -> dict[str, Any]:
        """Tra quan hệ sửa đổi đã lưu (source sửa đổi target); không tự tổng hợp văn bản hợp nhất."""
        items: list[dict[str, Any]] = self.db.get_relations(so_hieu, kind="amends")
        return {"status": "ok" if items else "no_data", "items": items}

    #@ Giải các dẫn chiếu tường minh trong cùng văn bản và giữ bằng chứng.
    def get_references(self, chunk_id: str) -> dict[str, Any]:
        """Lấy Điều được dẫn dạng 'Điều N Nghị định này'; chưa xử lý dẫn chiếu liên văn bản."""
        if self.db.get_chunk(chunk_id) is None:
            return {"status": "not_found", "items": []}
        items: list[dict[str, Any]] = [
            {
                **reference,
                "target": self.get_article(
                    reference["target_document"], reference["target_article"]
                ),
            }
            for reference in self.db.get_references(chunk_id)
        ]
        return {"status": "ok" if items else "no_data", "items": items}

    #@ Tạo tool LangChain để có thể truyền cho agent khi người dùng nối agent sau này.
    def as_langchain_tools(self) -> list[StructuredTool]:
        return [
            StructuredTool.from_function(method)
            for method in (
                self.search,
                self.get_article,
                self.expand,
                self.get_relations,
                self.get_amendments,
                self.get_references,
            )
        ]

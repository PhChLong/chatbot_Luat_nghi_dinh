import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from langchain_core.documents import Document


#@ Chuẩn hóa số hiệu nhập bằng dấu gạch chéo về tên file nguồn.
def document_key(value: str) -> str:
    return value.strip().replace("/", "-")


#@ Lấy số Điều từ số đơn hoặc tiêu đề Điều đầy đủ.
def article_number(value: str) -> str:
    match: re.Match[str] | None = re.match(
        r"^(?:Điều\s+)?(\d+[a-zđ]?)(?=[.\s]|$)", value.strip(), re.IGNORECASE
    )
    if match is None:
        raise ValueError(f"Không nhận diện được số Điều: {value}")
    return match[1].lower()


class SQLiteDB:
    #@ Mở kho nội dung; cho phép tool đọc từ worker thread của LangChain.
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection: sqlite3.Connection = sqlite3.connect(
            path, check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, content TEXT NOT NULL, metadata TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS articles (
                document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                number TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT NOT NULL,
                PRIMARY KEY (document_id, number)
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                article_number TEXT, position INTEGER NOT NULL,
                content TEXT NOT NULL, metadata TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id);
            CREATE TABLE IF NOT EXISTS relations (
                source_id TEXT NOT NULL, target_id TEXT NOT NULL,
                kind TEXT NOT NULL, evidence TEXT NOT NULL,
                PRIMARY KEY (source_id, target_id, kind)
            );
            CREATE TABLE IF NOT EXISTS article_references (
                chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
                target_document TEXT NOT NULL, target_article TEXT NOT NULL,
                evidence TEXT NOT NULL,
                PRIMARY KEY (chunk_id, target_document, target_article)
            );
        """)

    #@ Đóng kết nối SQLite.
    def close(self) -> None:
        self.connection.close()

    #@ Thay snapshot của từng văn bản trong một transaction, giữ nguyên văn bản khác.
    def save_documents(
        self,
        documents: list[Document],
        sections: list[Document],
        chunks: list[Document],
    ) -> None:
        doc: Document
        section: Document
        chunk: Document
        with self.connection:
            for doc in documents:
                key: str = document_key(doc.metadata["name"])
                self.connection.execute(
                    "INSERT INTO documents VALUES (?, ?, ?) ON CONFLICT(id) "
                    "DO UPDATE SET content=excluded.content, metadata=excluded.metadata",
                    (
                        key,
                        doc.page_content,
                        json.dumps(doc.metadata, ensure_ascii=False),
                    ),
                )
                self.connection.execute(
                    "DELETE FROM articles WHERE document_id=?", (key,)
                )
                self.connection.execute(
                    "DELETE FROM chunks WHERE document_id=?", (key,)
                )
            for section in sections:
                if section.metadata.get("section_kind") != "PROV-ARTICLE":
                    continue
                self.connection.execute(
                    "INSERT INTO articles VALUES (?, ?, ?, ?)",
                    (
                        document_key(section.metadata["name"]),
                        article_number(section.metadata["article"]),
                        section.page_content,
                        json.dumps(section.metadata, ensure_ascii=False),
                    ),
                )
            for chunk in chunks:
                key = document_key(chunk.metadata["name"])
                number: str | None = (
                    article_number(chunk.metadata["article"])
                    if chunk.metadata.get("section_kind") == "PROV-ARTICLE"
                    else None
                )
                self.connection.execute(
                    "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        chunk.metadata["chunk_id"],
                        key,
                        number,
                        chunk.metadata["position"],
                        chunk.page_content,
                        json.dumps(chunk.metadata, ensure_ascii=False),
                    ),
                )
                #? shortcut: chỉ giải dẫn chiếu tường minh trong cùng văn bản; mở rộng khi có parser liên văn bản.
                document_type: str = chunk.metadata.get("document_type", "")
                if document_type.casefold() not in {
                    "luật",
                    "nghị định",
                    "thông tư",
                    "quyết định",
                    "bộ luật",
                }:
                    continue
                match: re.Match[str]
                for match in re.finditer(
                    r"\bĐiều\s+(\d+[a-zđ]?)\s+(?:của\s+)?"
                    + re.escape(document_type)
                    + r"\s+này\b",
                    chunk.page_content,
                    re.IGNORECASE,
                ):
                    self.connection.execute(
                        "INSERT OR IGNORE INTO article_references VALUES (?, ?, ?, ?)",
                        (chunk.metadata["chunk_id"], key, match[1].lower(), match[0]),
                    )

    #@ Lấy Điều gốc, không ghép lại các chunk có overlap.
    def get_article(self, so_hieu: str, dieu: str) -> dict[str, Any] | None:
        row: sqlite3.Row | None = self.connection.execute(
            "SELECT * FROM articles WHERE document_id=? AND number=?",
            (document_key(so_hieu), article_number(dieu)),
        ).fetchone()
        if row is None:
            return None
        return {
            "document_id": row["document_id"],
            "article": row["number"],
            "content": row["content"],
            "metadata": json.loads(row["metadata"]),
        }

    #@ Tra chunk bằng cùng ID được lưu trong Chroma.
    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        row: sqlite3.Row | None = self.connection.execute(
            "SELECT * FROM chunks WHERE id=?", (chunk_id,)
        ).fetchone()
        return dict(row) if row else None

    #@ Chọn chunk đủ metadata hiệu lực tại hôm nay và khớp filter được hỗ trợ.
    def eligible_chunk_ids(self, filters: dict[str, str] | None = None) -> list[str]:
        selected: dict[str, str] = filters or {}
        if set(selected) - {"so_hieu", "document_type", "article"}:
            raise ValueError("Filter chỉ hỗ trợ so_hieu, document_type, article")
        today: date = date.today()
        ids: list[str] = []
        row: sqlite3.Row
        #? shortcut: lọc snapshot bằng Python cho corpus nhỏ; chuyển sang cột SQL khi corpus lớn.
        for row in self.connection.execute(
            "SELECT id, document_id, article_number, metadata FROM chunks"
        ):
            metadata: dict[str, Any] = json.loads(row["metadata"])
            if metadata.get("status") != "Còn hiệu lực":
                continue
            try:
                effective_from: date = date.fromisoformat(metadata["eff_from"])
                end_value: str | None = metadata.get("eff_to")
                effective_to: date | None = (
                    date.fromisoformat(end_value)
                    if end_value not in (None, "", "null", "None")
                    else None
                )
            except (KeyError, ValueError, TypeError):
                continue
            if effective_from > today or (
                effective_to is not None and today >= effective_to
            ):
                continue
            if "so_hieu" in selected and row["document_id"] != document_key(
                selected["so_hieu"]
            ):
                continue
            if "article" in selected and row["article_number"] != article_number(
                selected["article"]
            ):
                continue
            if (
                "document_type" in selected
                and metadata.get("document_type") != selected["document_type"]
            ):
                continue
            ids.append(row["id"])
        return ids

    #@ Tra quan hệ đã nhập, không suy luận sửa đổi từ nội dung văn bản.
    def get_relations(
        self, so_hieu: str, kind: str | None = None
    ) -> list[dict[str, Any]]:
        key: str = document_key(so_hieu)
        query: str = "SELECT * FROM relations WHERE (source_id=? OR target_id=?)"
        parameters: list[str] = [key, key]
        if kind is not None:
            query += " AND kind=?"
            parameters.append(kind)
        return [dict(row) for row in self.connection.execute(query, parameters)]

    #@ Trả các dẫn chiếu nội bộ đã trích cùng đoạn bằng chứng.
    def get_references(self, chunk_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT * FROM article_references WHERE chunk_id=?", (chunk_id,)
            )
        ]

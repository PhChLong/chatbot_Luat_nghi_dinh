import importlib
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import numpy as np
from langchain_core.documents import Document

#? Nạp module dưới tên riêng để test không chạy __init__ mở index thật của dự án.
package: types.ModuleType = types.ModuleType("_legal_test")
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "src/chatbot_luat_nghi_dinh")
]
sys.modules[package.__name__] = package
chunking: Any = importlib.import_module("_legal_test.chunking")
SQLiteDB: Any = importlib.import_module("_legal_test.sqlite_db").SQLiteDB
LegalTools: Any = importlib.import_module("_legal_test.tools").LegalTools
VectorDB: Any = importlib.import_module("_legal_test.vector_db").VectorDB
RAGRetrieval: Any = importlib.import_module("_legal_test.rag").RAGRetrieval


class LegalToolsTest(unittest.TestCase):
    #@ Dựng hai Điều giả và SQLite tạm, không mở corpus hoặc model thật.
    def setUp(self) -> None:
        self.directory: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.db: Any = SQLiteDB(Path(self.directory.name) / "legal.sqlite3")
        self.source: Document = Document(
            page_content=(
                "PROV-ARTICLE\nĐiều 1. Phạm vi\n"
                "Thực hiện theo Điều 2 Nghị định này. "
                + "Nội dung mẫu. " * 20
                + "\nPROV-ARTICLE\nĐiều 2. Đối tượng\nToàn văn Điều hai."
            ),
            metadata={
                "name": "1-2020-NĐ-CP",
                "source": "fixture.md",
                "status": "Còn hiệu lực",
                "eff_from": "2020-01-01",
                "eff_to": "null",
                "document_type": "NGHỊ ĐỊNH",
            },
        )
        self.sections: list[Document] = chunking.split_document([self.source])
        self.chunks: list[Document] = chunking.chunk_documents(self.sections, 120, 20)
        self.db.save_documents([self.source], self.sections, self.chunks)
        self.retriever: Mock = Mock()
        self.reranker: Mock = Mock()
        self.tools: Any = LegalTools(self.db, self.retriever, self.reranker)

    #@ Đóng SQLite và xóa riêng dữ liệu test tạm.
    def tearDown(self) -> None:
        self.db.close()
        self.directory.cleanup()

    #@ Bảo đảm Điều đầy đủ, ID ổn định và ingest lại không thêm trùng.
    def test_article_and_repeat_ingestion(self) -> None:
        article: dict[str, Any] = self.tools.get_article("1/2020/NĐ-CP", "Điều 1")
        self.assertEqual(article["content"], self.sections[0].page_content)
        self.assertEqual(
            self.tools.expand(self.chunks[0].metadata["chunk_id"]), article
        )
        again: list[Document] = chunking.chunk_documents(self.sections, 120, 20)
        self.assertEqual(
            [c.metadata["chunk_id"] for c in again],
            [c.metadata["chunk_id"] for c in self.chunks],
        )
        self.db.save_documents([self.source], self.sections, again)
        self.assertEqual(
            self.db.connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            len(self.chunks),
        )
        self.assertEqual(
            self.tools.get_article("1/2020/NĐ-CP", "99")["status"], "not_found"
        )

    #@ Lọc ngày và trạng thái, không coi metadata thiếu hoặc hiệu lực một phần là hợp lệ.
    def test_validity_and_filters(self) -> None:
        self.assertEqual(
            len(self.db.eligible_chunk_ids({"so_hieu": "1/2020/NĐ-CP"})),
            len(self.chunks),
        )
        self.assertEqual(self.db.eligible_chunk_ids({"so_hieu": "khác"}), [])
        self.assertEqual(len(self.db.eligible_chunk_ids({"article": "2"})), 1)
        self.assertEqual(self.db.eligible_chunk_ids({"document_type": "LUẬT"}), [])
        with self.assertRaises(ValueError):
            self.db.eligible_chunk_ids({"status": "Còn hiệu lực"})
        metadata: dict[str, Any]
        for metadata in (
            {**self.source.metadata, "status": "Hết hiệu lực một phần"},
            {**self.source.metadata, "eff_from": "null"},
            {
                **self.source.metadata,
                "eff_from": (date.today() + timedelta(days=1)).isoformat(),
            },
            {**self.source.metadata, "eff_to": date.today().isoformat()},
        ):
            with self.db.connection:
                self.db.connection.execute(
                    "UPDATE chunks SET metadata=?", (json.dumps(metadata),)
                )
            self.assertEqual(self.db.eligible_chunk_ids(), [])

    #@ Phân biệt không có dữ liệu quan hệ với đã tra được quan hệ có bằng chứng.
    def test_relations_and_references(self) -> None:
        self.assertEqual(self.tools.get_amendments("1/2020/NĐ-CP")["status"], "no_data")
        with self.db.connection:
            self.db.connection.execute(
                "INSERT INTO relations VALUES (?, ?, ?, ?)",
                ("2-2021-NĐ-CP", "1-2020-NĐ-CP", "amends", "Nguồn kiểm chứng mẫu"),
            )
        self.assertEqual(len(self.tools.get_amendments("1/2020/NĐ-CP")["items"]), 1)
        reference_chunk: Document = next(
            chunk
            for chunk in self.chunks
            if "Điều 2 Nghị định này" in chunk.page_content
        )
        references: dict[str, Any] = self.tools.get_references(
            reference_chunk.metadata["chunk_id"]
        )
        self.assertEqual(
            references["items"][0]["target"]["content"], self.sections[1].page_content
        )
        self.assertEqual(self.tools.get_references("missing")["status"], "not_found")
        self.assertEqual(self.tools.expand("missing")["status"], "not_found")

    #@ Không gọi retrieval/rerank khi không có chunk hợp lệ; lọc ID trước lấy ứng viên.
    def test_search(self) -> None:
        self.assertEqual(self.tools.search("câu hỏi", {"so_hieu": "missing"}), [])
        self.retriever.query.assert_not_called()
        self.reranker.rerank.assert_not_called()
        candidates: list[dict[str, Any]] = [{"id": "test", "content": "mẫu"}]
        self.retriever.query.return_value = candidates
        self.reranker.rerank.return_value = [(candidates[0], 0.9)]
        self.assertEqual(self.tools.search("câu hỏi")[0]["rerank_score"], 0.9)
        self.assertEqual(
            self.retriever.query.call_args.kwargs["ids"], self.db.eligible_chunk_ids()
        )
        self.reranker.rerank.assert_called_once_with("câu hỏi", candidates, top_k=5)
        with self.assertRaises(ValueError):
            self.tools.search(" ")
        self.assertEqual(len(self.tools.as_langchain_tools()), 6)
        self.assertEqual(
            self.tools.as_langchain_tools()[1].invoke(
                {"so_hieu": "1/2020/NĐ-CP", "dieu": "2"}
            )["status"],
            "ok",
        )

    #@ Không nhầm “Luật này” thành chính Nghị định; giữ rõ đích dẫn chiếu còn thiếu.
    def test_reference_scope_and_missing_target(self) -> None:
        chunk: Document = Document(
            page_content="Điều 2 Luật này. Điều 99 Nghị định này.",
            metadata={**self.chunks[0].metadata, "chunk_id": "scope-test"},
        )
        self.db.save_documents([self.source], self.sections, [chunk])
        result: dict[str, Any] = self.tools.get_references("scope-test")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["target_article"], "99")
        self.assertEqual(result["items"][0]["target"]["status"], "not_found")

    #@ Transaction thất bại phải giữ snapshot trước đó.
    def test_sqlite_rollback(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.save_documents(
                [self.source], self.sections + self.sections, self.chunks
            )
        self.assertEqual(self.tools.get_article("1/2020/NĐ-CP", "2")["status"], "ok")
        self.assertEqual(len(self.db.eligible_chunk_ids()), len(self.chunks))

    #@ Kiểm tra Chroma thật với vector giả: ingest lại, xóa chunk cũ và filter trước retrieval.
    def test_chroma_sync_and_filtered_retrieval(self) -> None:
        store: Any = VectorDB(Path(self.directory.name) / "chroma")
        embeddings: np.ndarray = np.tile([1.0, 0.0, 0.0], (len(self.chunks), 1))
        store.collection.add(
            ids=["legacy-uuid", "other-document"],
            embeddings=[[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            metadatas=[{"name": self.source.metadata["name"]}, {"name": "other"}],
            documents=["chunk cũ", "văn bản khác"],
        )
        store.add_documents(self.chunks, embeddings)
        store.add_documents(self.chunks, embeddings)
        self.assertEqual(store.collection.count(), len(self.chunks) + 1)
        self.assertEqual(store.collection.get(ids=["legacy-uuid"])["ids"], [])
        embedding: Mock = Mock()
        embedding.generate_embeddings.return_value = np.array([[1.0, 0.0, 0.0]])
        retriever: Any = RAGRetrieval(store, embedding)
        ids: list[str] = self.db.eligible_chunk_ids({"article": "2"})
        result: list[dict[str, Any]] = retriever.query("mẫu", top_k=20, ids=ids)
        self.assertEqual([item["id"] for item in result], ids)
        self.assertEqual(retriever.query("mẫu", ids=[]), [])
        store.add_documents([self.chunks[-1]], embeddings[:1])
        self.assertEqual(store.collection.count(), 2)
        self.assertEqual(
            store.collection.get(ids=["other-document"])["ids"], ["other-document"]
        )


if __name__ == "__main__":
    unittest.main()

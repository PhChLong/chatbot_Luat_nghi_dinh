import importlib
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import Mock, patch

#? Nạp package riêng để test không khởi tạo Chroma, model hoặc đọc API key trong __init__.
PACKAGE: str = "_legal_workflow_test"
package: ModuleType = ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "src/chatbot_luat_nghi_dinh")]
sys.modules[PACKAGE] = package
agent_module: ModuleType = ModuleType(f"{PACKAGE}.deepagent")
agent_module.Agent = Mock
sys.modules[agent_module.__name__] = agent_module
package.retriever = Mock()
package.reranker = Mock()
workflow: ModuleType = importlib.import_module(f"{PACKAGE}.tools")
database: ModuleType = importlib.import_module(f"{PACKAGE}.database")


class DocumentContentTests(unittest.TestCase):
    #@ Khởi tạo dữ liệu context và mock sạch cho mỗi test.
    def setUp(self) -> None:
        self.doc: dict[str, Any] = {
            "id": "chunk-1", "content": "Nội dung thử nghiệm",
            "metadata": {"name": "test-doc", "article": "5", "source": "test.html"},
        }
        self.info: dict[str, str | None] = {
            "name": None, "article_label": None, "clause_label": None, "label": None,
        }
        package.retriever.reset_mock()
        package.reranker.reset_mock()
        package.retriever.query.return_value = [self.doc]

    #@ Xác minh filter Điều/văn bản, ngưỡng rerank và trường hợp tìm toàn corpus.
    def test_chroma_filters_and_rerank(self) -> None:
        state: dict[str, Any] = {
            "question": "Câu hỏi gốc", "search_query": "Query mới",
            "name": "test-doc", "article_label": "5",
        }
        docs: list[dict[str, Any]] = [dict(self.doc, id=f"chunk-{index}") for index in range(6)]
        package.retriever.query.return_value = docs
        package.reranker.rerank.return_value = [(doc, 0.9) for doc in docs[:5]]
        result: dict = workflow.doc_retrieve(state)
        self.assertEqual(len(result["retrieved_docs"]), 5)
        package.retriever.query.assert_called_once_with(
            question="Query mới", top_k=20,
            where={"$and": [{"name": "test-doc"}, {"article": "5"}]},
        )
        package.reranker.rerank.assert_called_once_with(query="Query mới", docs=docs, top_k=5)
        package.reranker.reset_mock()
        package.retriever.query.return_value = docs[:5]
        workflow.doc_retrieve({"question": "?", "name": "test-doc"})
        self.assertEqual(package.retriever.query.call_args.kwargs["where"], {"name": "test-doc"})
        workflow.doc_retrieve({"question": "?"})
        self.assertIsNone(package.retriever.query.call_args.kwargs["where"])
        package.reranker.rerank.assert_not_called()

    #@ Dùng SQLite thật để kiểm tra Khoản chứa đủ Điểm, không lẫn Khoản khác.
    def test_sqlite_subtree_keeps_all_points(self) -> None:
        connection: sqlite3.Connection = sqlite3.connect(":memory:")
        connection.executescript("""
            CREATE TABLE metadata (document_id INTEGER, name TEXT);
            INSERT INTO metadata VALUES (1, 'test-doc');
            CREATE TABLE legal_units (
                id INTEGER, document_id INTEGER, parent_id INTEGER, unit_type TEXT,
                label TEXT, article_label TEXT, clause_label TEXT, title TEXT, body TEXT
            );
            INSERT INTO legal_units VALUES
                (1, 1, NULL, 'article', '5', '5', NULL, 'Điều thử', ''),
                (2, 1, 1, 'clause', '3', '5', '3', NULL, 'Khoản thử'),
                (3, 1, 2, 'point', 'a', '5', '3', NULL, 'Điểm thứ nhất'),
                (4, 1, 2, 'point', 'b', '5', '3', NULL, 'Điểm thứ hai'),
                (5, 1, 1, 'clause', '4', '5', '4', NULL, 'Khoản ngoài phạm vi');
        """)
        state: dict[str, Any] = {
            "question": "Khoản 3 Điều 5?", "name": "test-doc",
            "article_label": "5", "clause_label": "3", "label": None,
        }
        with patch.object(database.sqlite3, "connect", return_value=connection):
            result: dict = workflow.doc_retrieve(state)
        content: str = result["retrieved_docs"][0]["content"]
        self.assertIn("Khoản thử", content)
        self.assertIn("Điểm thứ nhất", content)
        self.assertIn("Điểm thứ hai", content)
        self.assertNotIn("Khoản ngoài phạm vi", content)
        package.retriever.query.assert_not_called()
        package.reranker.rerank.assert_not_called()

    #@ Kiểm tra Điểm được truyền đủ địa chỉ vào query_content.
    def test_point_address_and_ambiguous_rows(self) -> None:
        state: dict[str, Any] = {
            "question": "?", "name": "test-doc", "article_label": "5",
            "clause_label": "3", "label": "a",
        }
        with patch.object(workflow, "query_content", return_value=[]) as query:
            self.assertEqual(workflow.doc_retrieve(state)["retrieved_docs"], [])
            query.assert_called_once_with("test-doc", "điểm", "a", article_label="5", clause_label="3")
        with patch.object(workflow, "query_content", side_effect=ValueError("Địa chỉ không duy nhất")):
            self.assertIn("clarify_reason", workflow.doc_retrieve(state))

    #@ Hỏi lại khi thiếu tên/Điều hoặc văn bản không tồn tại, không đoán địa chỉ.
    def test_resolve_ambiguous_address(self) -> None:
        info: dict = dict(self.info, clause_label="3")
        with patch.object(workflow, "extract_info", return_value=info):
            self.assertTrue(workflow.doc_resolve({"question": "?"})["clarify_reason"])
        info.update(name="test-doc")
        with patch.object(workflow, "extract_info", return_value=info):
            self.assertTrue(workflow.doc_resolve({"question": "?"})["clarify_reason"])
        info.update(article_label="5")
        with (
            patch.object(workflow, "extract_info", return_value=info),
            patch.object(workflow, "query_metadata", return_value=None),
        ):
            self.assertIn("Không tìm thấy", workflow.doc_resolve({"question": "?"})["clarify_reason"])

    #@ Grade dựa vào câu hỏi gốc; boolean sai kiểu và JSON hỏng đều không được coi là đủ.
    def test_grade_validates_output(self) -> None:
        state: dict[str, Any] = {
            "question": "Câu hỏi gốc", "search_query": "Query mới", "retrieved_docs": [self.doc],
        }
        outputs: list[str] = [
            "không phải JSON", '{"context_sufficient": "false"}',
            '{"context_sufficient": true, "insufficient_reason": null, "clarify_reason": null}',
        ]
        with patch.object(workflow, "Agent") as factory:
            factory.return_value.invoke.side_effect = outputs
            self.assertFalse(workflow.doc_grade(state)["context_sufficient"])
            self.assertFalse(workflow.doc_grade(state)["context_sufficient"])
            self.assertTrue(workflow.doc_grade(state)["context_sufficient"])
            payload: dict = json.loads(factory.return_value.invoke.call_args.args[0])
            self.assertEqual(payload["question"], "Câu hỏi gốc")
        self.assertFalse(workflow.doc_grade({"question": "?", "retrieved_docs": []})["context_sufficient"])

    #@ Chạy graph đủ ba lượt retrieval, hai rewrite; giữ nguyên câu hỏi gốc và filter.
    def test_graph_stops_after_two_retries(self) -> None:
        info: dict = dict(self.info, name="test-doc", article_label="5")
        grade: str = json.dumps({"context_sufficient": False, "insufficient_reason": "Thiếu ngoại lệ"})
        responses: list[str] = [
            "document_content", json.dumps(info), grade, "Query lần 2",
            grade, "Query lần 3", grade, "Có quy định liên quan [1].",
        ]
        with patch.object(workflow, "Agent") as factory:
            factory.return_value.invoke.side_effect = responses
            with patch.object(workflow, "query_metadata", return_value={"name": "test-doc"}):
                result: dict = workflow.build_graph().invoke({"question": "Câu hỏi gốc"})
        self.assertEqual(result["retry_count"], 2)
        self.assertEqual(result["question"], "Câu hỏi gốc")
        self.assertEqual(package.retriever.query.call_count, 3)
        self.assertIn("chưa đủ", result["answer"])
        self.assertEqual([call.kwargs["question"] for call in package.retriever.query.call_args_list],
                         ["Câu hỏi gốc", "Query lần 2", "Query lần 3"])
        self.assertTrue(all(call.kwargs["where"] == {"$and": [{"name": "test-doc"}, {"article": "5"}]}
                            for call in package.retriever.query.call_args_list))
        rewrite_payload: dict = json.loads(factory.return_value.invoke.call_args_list[3].args[0])
        self.assertEqual(rewrite_payload["insufficient_reason"], "Thiếu ngoại lệ")

    #@ Dừng ngay khi grade đủ hoặc yêu cầu hỏi lại người dùng.
    def test_grade_routes(self) -> None:
        self.assertEqual(workflow.after_grade({"context_sufficient": True}), "generate")
        self.assertEqual(workflow.after_grade({"context_sufficient": False, "retry_count": 1}), "retry")
        self.assertEqual(workflow.after_grade({"clarify_reason": "Bạn thuộc nhóm nào?"}), "clarify")
        self.assertEqual(workflow.clarify({"clarify_reason": "Bạn thuộc nhóm nào?"}),
                         {"answer": "Bạn thuộc nhóm nào?"})

    #@ Không sinh câu trả lời khi context rỗng; từ chối số nguồn model tự bịa.
    def test_generation_empty_context_and_invalid_citation(self) -> None:
        with patch.object(workflow, "Agent") as factory:
            self.assertIn("Chưa tìm thấy", workflow.doc_generate({"question": "?"})["answer"])
            factory.assert_not_called()
            factory.return_value.invoke.return_value = "Nội dung [9]"
            self.assertIn("không có trong context", workflow.doc_generate({
                "question": "?", "retrieved_docs": [self.doc], "context_sufficient": True,
            })["answer"])

    #@ Kiểm tra graph dừng ngay khi đủ context hoặc khi grade yêu cầu hỏi người dùng.
    def test_graph_early_exit(self) -> None:
        grade: dict[str, Any]
        for grade in (
            {"context_sufficient": True, "insufficient_reason": None, "clarify_reason": None},
            {"context_sufficient": False, "insufficient_reason": None, "clarify_reason": "Bạn thuộc nhóm nào?"},
        ):
            package.retriever.reset_mock()
            responses: list[str] = ["document_content", json.dumps(self.info), json.dumps(grade)]
            if grade["context_sufficient"]:
                responses.append("Nội dung có căn cứ [1].")
            with patch.object(workflow, "Agent") as factory:
                factory.return_value.invoke.side_effect = responses
                result: dict[str, Any] = workflow.build_graph().invoke({"question": "?"})
            self.assertEqual(result["retry_count"], 0)
            package.retriever.query.assert_called_once()
            if grade["clarify_reason"]:
                self.assertEqual(result["answer"], "Bạn thuộc nhóm nào?")
            else:
                self.assertEqual(result["answer"], "Nội dung có căn cứ [1].")

    #@ Xác minh RAGRetrieval truyền filter vào API Chroma, giữ tương thích lời gọi cũ.
    def test_retrieval_forwards_where(self) -> None:
        embedding_module: ModuleType = ModuleType(f"{PACKAGE}.embedding")
        embedding_module.EmbeddingManager = Mock
        vector_module: ModuleType = ModuleType(f"{PACKAGE}.vector_db")
        vector_module.VectorDB = Mock
        with patch.dict(sys.modules, {
            embedding_module.__name__: embedding_module,
            vector_module.__name__: vector_module,
        }):
            rag: ModuleType = importlib.import_module(f"{PACKAGE}.rag")
        store: Mock = Mock()
        embedding: Mock = Mock()
        embedding.generate_embeddings.return_value = [[0.1, 0.2]]
        store.collection.query.return_value = {
            "ids": [["chunk-1"]], "documents": [["Nội dung"]],
            "metadatas": [[{"name": "test-doc"}]], "distances": [[0.1]],
        }
        retriever: Any = rag.RAGRetrieval(store, embedding)  #? Module được nạp riêng để tránh khởi tạo runtime thật.
        docs: list[dict[str, Any]] = retriever.query("?", top_k=20, where={"name": "test-doc"})
        self.assertEqual(docs[0]["content"], "Nội dung")
        store.collection.query.assert_called_once_with(
            query_embeddings=[[0.1, 0.2]], n_results=20, where={"name": "test-doc"},
        )
        retriever.query("?")
        self.assertIsNone(store.collection.query.call_args.kwargs["where"])
        self.assertEqual(store.collection.query.call_args.kwargs["n_results"], 5)

    #@ Situation dùng chung retrieval và filter, nhưng chọn prompt grade/trả lời riêng.
    def test_situation_uses_shared_pipeline_and_own_prompts(self) -> None:
        info: dict[str, Any] = dict(self.info, name="test-doc", article_label="5")
        metadata: dict[str, str] = {"name": "test-doc", "eff_from": "2026-10-01"}
        with (
            patch.object(workflow, "Agent") as factory,
            patch.object(workflow, "query_metadata", return_value=metadata),
        ):
            factory.return_value.invoke.side_effect = [
                "situation", json.dumps(info),
                '{"context_sufficient": true, "insufficient_reason": null, "clarify_reason": null}',
                "Căn cứ: quy định [1]. Đối chiếu tình huống: đủ điều kiện. Kết luận: được áp dụng.",
            ]
            result: dict[str, Any] = workflow.build_graph().invoke({
                "question": "Tình huống của tôi?",
                "entities": {"doc_ids": [], "article": None, "as_of_date": "2026-10-26"},
            })
        self.assertEqual(result["question_type"], "situation")
        self.assertEqual(result["retry_count"], 0)
        self.assertIn("Đối chiếu tình huống", result["answer"])
        package.retriever.query.assert_called_once_with(
            question="Tình huống của tôi?", top_k=20,
            where={"$and": [{"name": "test-doc"}, {"article": "5"}]},
        )
        self.assertEqual(factory.call_args_list[2].args[0], workflow.SIT_GRADE_PROMPT)
        self.assertEqual(factory.call_args_list[3].args[0], workflow.SIT_ANSWER_PROMPT)
        payload: dict[str, Any]
        for payload in (
            json.loads(factory.return_value.invoke.call_args_list[2].args[0]),
            json.loads(factory.return_value.invoke.call_args_list[3].args[0]),
        ):
            self.assertEqual(payload["document_metadata"], metadata)
            self.assertEqual(payload["as_of_date"], "2026-10-26")

    #@ Thiếu dữ kiện tình huống thì hỏi lại ngay, không rewrite để tự đoán.
    def test_situation_missing_facts_asks_user(self) -> None:
        with patch.object(workflow, "Agent") as factory:
            factory.return_value.invoke.side_effect = [
                "situation", json.dumps(self.info),
                json.dumps({
                    "context_sufficient": False, "insufficient_reason": None,
                    "clarify_reason": "Bạn có hưởng thu nhập tăng thêm không?",
                }),
            ]
            result: dict[str, Any] = workflow.build_graph().invoke({"question": "Tôi hưởng mức phụ cấp nào?"})
        self.assertEqual(result["answer"], "Bạn có hưởng thu nhập tăng thêm không?")
        self.assertEqual(result["retry_count"], 0)
        package.retriever.query.assert_called_once_with(
            question="Tôi hưởng mức phụ cấp nào?", top_k=20, where=None,
        )
        self.assertEqual(factory.return_value.invoke.call_count, 3)

    #@ Thiếu nguồn tình huống được rewrite tối đa hai lần như document_content.
    def test_situation_retry_limit(self) -> None:
        grade: str = json.dumps({
            "context_sufficient": False, "insufficient_reason": "Thiếu quy định về ngoại lệ",
            "clarify_reason": None,
        })
        with patch.object(workflow, "Agent") as factory:
            factory.return_value.invoke.side_effect = [
                "situation", json.dumps(self.info), grade, "Query bổ sung 1",
                grade, "Query bổ sung 2", grade, "Có một phần căn cứ [1].",
            ]
            result: dict[str, Any] = workflow.build_graph().invoke({"question": "Tình huống của tôi?"})
        self.assertEqual(result["retry_count"], 2)
        self.assertEqual(package.retriever.query.call_count, 3)
        self.assertIn("chưa đủ", result["answer"])
        self.assertEqual(result["question"], "Tình huống của tôi?")
        self.assertEqual(factory.call_args_list[-1].args[0], workflow.SIT_ANSWER_PROMPT)


if __name__ == "__main__":
    unittest.main()

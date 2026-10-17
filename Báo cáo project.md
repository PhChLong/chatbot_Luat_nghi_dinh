
# 8.  Workflow mục tiêu

## 8.1. Dữ liệu cần chuẩn bị trước

- **Bảng quan hệ văn bản** (ngoài Chroma): sửa đổi bổ sung, thay thế, bãi bỏ, căn cứ, hướng dẫn thi hành.
- **Bảng sửa đổi cấp Điều:** trích bằng regex từ câu "Sửa đổi, bổ sung Điều N ... như sau" trong văn bản sửa đổi. Đây là heuristic, cần kiểm tra thủ công trên mẫu; phần không bắt được dùng cảnh báo cấp văn bản làm dự phòng.

## 8.2. Tools

| Tool                              | Chức năng                                                                                                                             |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `search(query, filters)`          | Lấy 20 chunk → rerank chọn 5; filter tùy chọn theo số hiệu, loại văn bản, Điều; filter hiệu lực luôn bật **[có]** phần query + rerank |
| `get_article(so_hieu, dieu)`      | Lấy chính xác một Điều, không dùng embedding                                                                                          |
| `expand(chunk_id)`                | Lấy cả Điều hoặc chunk lân cận                                                                                                        |
| `get_relations`, `get_amendments` | Tra bảng quan hệ và bảng sửa đổi                                                                                                      |
| `get_references(chunk_id)`        | Lấy phần được tham chiếu ("Điều 10 Nghị định này")                                                                                    |

## 8.4. Node và vai trò của LLM

| Node                              | LLM?  | Vai trò                                                                |
| --------------------------------- | ----- | ---------------------------------------------------------------------- |
| Router                            | Có    | Phân loại: pháp luật / chitchat / ngoài phạm vi / cần hỏi lại          |
| Rewrite + decompose               | Có    | Viết lại thành câu độc lập, tách câu hỏi nhiều vế                      |
| **Planner (main agent)**          | Có    | Chọn `search` hay `get_article` và filter cho từng sub-query           |
| Retrieve, Expand, Amendment check | Không | Gọi tool, gộp chunk, kéo nội dung đã sửa vào context                   |
| **Sufficiency check (sub-agent)** | Có    | Trả `{sufficient, missing}`; `missing` đưa vào lần rewrite sau         |
| Answer                            | Có    | Trả lời chỉ từ context, citation bắt buộc, được phép "không đủ căn cứ" |
| Verify citation                   | Không | Mọi citation phải nằm trong chunk đã retrieve                          |

Agent chỉ dùng ở hai chỗ: Planner (chọn cách tra cứu) và Sufficiency check (quyết định có tìm thêm không). Sufficiency check là điểm yếu nhất với model 4B, nên giới hạn 2–3 vòng, lưu query đã thử, và thiết kế như node có prompt hẹp.

## 8.5. Luồng xử lý

```text
question
  → Router ──► ngoài phạm vi / chitchat / cần hỏi lại → kết thúc
  → Rewrite + decompose → sub_queries
  → ┌ vòng lặp tối đa 2–3 lần ─────────────────────────────────────┐
    │ Planner → Retrieve → Expand + Amendment check → Sufficiency  │
    │   sufficient = false → quay lại Rewrite với `missing`        │
    └──────────────────────────────────────────────────────────────┘
  → Answer (citation bắt buộc) → Verify citation → trả lời
```

**Xử lý hiệu lực:** filter loại văn bản hết hiệu lực khi retrieve. Ở bước Amendment check, Điều bị bãi bỏ bị loại khỏi context, Điều bị sửa thì thêm nội dung sửa kèm nguồn; nếu không có dữ liệu cấp Điều nhưng văn bản có văn bản sửa đổi thì gắn cảnh báo vào câu trả lời. Khi hai văn bản mâu thuẫn, code sắp xếp theo thứ bậc (luật > nghị định > thông tư; cùng cấp thì văn bản mới hơn).

## 8.6. Đánh giá và thứ tự triển khai

Hiện chưa có evaluation. Cần bộ 30–50 câu hỏi kèm đáp án chuẩn (văn bản nào, Điều nào), chạy baseline query + rerank thuần rồi thêm từng thành phần và đo lại bằng: Recall@5, citation accuracy, tỉ lệ trích văn bản hết hiệu lực, tỉ lệ từ chối đúng chỗ.

Thứ tự: (1) bộ đánh giá + baseline → (2) sửa metadata và ID → (3) `search` có filter + `get_article` → (4) node trả lời + verify citation → (5) bảng quan hệ/sửa đổi + amendment check → (6) `expand`, `get_references` → (7) router, rewrite → (8) planner + sufficiency check + vòng lặp → (9) hybrid search (BM25).

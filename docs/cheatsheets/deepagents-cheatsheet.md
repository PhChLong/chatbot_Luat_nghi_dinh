# Deep Agents cheatsheet cơ bản

> Repo hiện chưa khai báo package `deepagents`. Code dưới đây để hiểu cấu trúc, chưa được xác nhận chạy trong môi trường hiện tại.

## Deep Agents là gì?

Deep Agents hướng tới nhiệm vụ dài, nhiều bước, thường cần:

- Lập kế hoạch hoặc chia nhỏ nhiệm vụ.
- Gọi nhiều tool.
- Lưu/đọc file làm việc.
- Giao một phần việc cho subagent.
- Quản lý context có chọn lọc.

Pipeline cố định như `retrieval -> rerank -> answer` thường nên bắt đầu bằng code thường hoặc LangGraph đơn giản.

## Phân biệt nhanh

| Công cụ | Vai trò chính |
|---|---|
| LangChain | Model, message, prompt và tool |
| LangGraph | State và luồng node/edge do mình định nghĩa |
| Deep Agents | Khung agent cho nhiệm vụ dài, nhiều tool và nhiều bước |

## Hình dạng code cơ bản

API có thể thay đổi theo phiên bản package:

```python
from deepagents import create_deep_agent
from langchain_ollama import ChatOllama

model = ChatOllama(model="qwen3.5:4b", temperature=0.1)

def search_legal_documents(query: str) -> str:
    """Tìm nội dung liên quan trong kho văn bản pháp luật."""
    return f"Kết quả minh họa cho: {query}"

agent = create_deep_agent(
    model=model,
    tools=[search_legal_documents],
    system_prompt=(
        "Chỉ trả lời từ nguồn do tool cung cấp. "
        "Nếu thiếu căn cứ, phải nói rõ."
    ),
)
```

Ba phần cốt lõi:

- `model`: LLM ra quyết định và tạo nội dung.
- `tools`: các thao tác agent được phép gọi.
- `system_prompt`: nguyên tắc làm việc.

## Viết tool

```python
def retrieve_law(query: str, top_k: int = 5) -> str:
    """Tìm tối đa top_k đoạn pháp luật liên quan đến query."""
    ...
```

Tên hàm, type hint và docstring giúp model biết khi nào gọi tool và truyền gì. Một tool nên làm một việc rõ ràng.

## Khi nào repo này có thể cần Deep Agents?

Khi một yêu cầu cần tự thực hiện nhiều bước như:

1. Tìm nhiều văn bản liên quan.
2. Kiểm tra văn bản sửa đổi hoặc thay thế.
3. Đối chiếu các phiên bản.
4. Tổng hợp có trích dẫn.
5. Tự kiểm tra lại nguồn.

Nếu chỉ lấy vài chunk rồi trả lời một câu hỏi, Deep Agents có thể phức tạp hơn mức cần thiết.

## Lỗi và rủi ro

- **Retrieval rỗng nhưng agent vẫn trả lời:** prompt không bảo đảm hết hallucination; code cần kiểm tra dữ liệu rỗng.
- **Tool bỏ metadata:** cần giữ số hiệu, điều/khoản, hiệu lực và nguồn để tạo citation.
- **Tool quá nhiều quyền:** tách rõ tool đọc và tool thay đổi dữ liệu.
- **Dùng agent cho workflow cố định:** graph cố định dễ kiểm tra hơn nếu thứ tự bước không đổi.
- **Cho rằng package đã dùng được:** cần cài/khóa phiên bản và kiểm tra API trước khi triển khai.

## Nhớ nhanh

```text
Ít bước, luồng cố định           -> code thường
Có state và rẽ nhánh kiểm soát  -> LangGraph
Nhiệm vụ dài, nhiều tool        -> cân nhắc Deep Agents
```

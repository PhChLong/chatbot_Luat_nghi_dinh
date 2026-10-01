# LangChain Ollama cheatsheet cơ bản

Repo đang dùng `ChatOllama` với model local `qwen3.5:4b`.

## Điều kiện chạy

LangChain không tự cung cấp model. Ollama phải chạy và máy phải có model:

```powershell
ollama list
ollama pull qwen3.5:4b
```

Chỉ cần `pull` nếu máy chưa có model.

## Gọi model

```python
from langchain_ollama import ChatOllama

model = ChatOllama(model="qwen3.5:4b", temperature=0.1)
response = model.invoke("Giải thích RAG trong 3 câu")
print(response.content)
```

`invoke()` trả một message object; text chính nằm trong `response.content`.

## Dùng messages

```python
from langchain_core.messages import HumanMessage, SystemMessage

messages = [
    SystemMessage(content=(
        "Bạn hỗ trợ tra cứu pháp luật. "
        "Nếu context không đủ, phải nói rõ."
    )),
    HumanMessage(content="Nghị định là gì?"),
]

response = model.invoke(messages)
print(response.content)
```

- `SystemMessage`: quy tắc chung.
- `HumanMessage`: yêu cầu người dùng.
- `AIMessage`: phản hồi model.

## Prompt RAG tối thiểu

```python
prompt = f"""
Chỉ trả lời dựa trên context dưới đây.
Nếu context không đủ, trả lời: Chưa đủ căn cứ.

CONTEXT:
{context}

QUESTION:
{question}
"""

response = model.invoke(prompt)
```

Prompt chỉ định hướng model. Code vẫn phải retrieval đúng và giữ metadata nguồn.

## Streaming

```python
for chunk in model.stream("Giải thích embedding thật ngắn"):
    print(chunk.content, end="", flush=True)
```

Streaming chỉ hiển thị dần; nó không làm câu trả lời chính xác hơn.

## Structured output

```python
from pydantic import BaseModel, Field

class LegalAnswer(BaseModel):
    answer: str = Field(description="Câu trả lời ngắn")
    source: str | None = None
    sufficient_context: bool

structured_model = model.with_structured_output(LegalAnswer)
result = structured_model.invoke("Context: Hiệu lực từ 01/01/2026")
print(result.answer)
```

Schema kiểm soát hình dạng dữ liệu, không tự kiểm chứng tính đúng của nội dung. Khả năng tuân thủ schema còn phụ thuộc model; cần test bằng input đại diện.

## Tham số cơ bản

```python
model = ChatOllama(
    model="qwen3.5:4b",
    temperature=0.1,
    num_ctx=8192,
)
```

- `model`: phải khớp `ollama list`.
- `temperature`: thấp thường ổn định hơn, không bảo đảm chính xác.
- `num_ctx`: context lớn hơn tốn thêm RAM/VRAM.

## Lỗi thường gặp

- **Không kết nối được:** Ollama chưa chạy hoặc sai địa chỉ server.
- **Model not found:** tên model không khớp model đã pull.
- **In ra object khó đọc:** dùng `response.content`.
- **Context quá dài:** retrieval một số chunk, không nhét cả corpus vào prompt.
- **Tin structured output là nội dung đúng:** schema chỉ bảo đảm cấu trúc.

# Schema cheatsheet cơ bản

## Schema là gì?

Schema mô tả dữ liệu có field nào và mỗi field có kiểu gì.

| Loại | Dùng khi | Validation runtime? |
|---|---|---|
| `dict` | Thử nhanh, dữ liệu nhỏ | Không |
| `TypedDict` | State/dict cần type hint | Không |
| `dataclass` | Object dữ liệu hoặc cấu hình | Cơ bản |
| Pydantic `BaseModel` | Parse và validate input/output | Có |

Quy tắc đơn giản:

- LangGraph state: bắt đầu bằng `TypedDict`.
- Structured output: dùng Pydantic `BaseModel`.
- Cấu hình nội bộ như `Level` trong `chunking.py`: dùng `dataclass`.

## `dict`

```python
result = {"answer": "...", "sufficient_context": True}
```

Nhanh nhưng typo không được phát hiện sớm: `result["anwser"]` tạo một key khác.

## `TypedDict`

```python
from typing import TypedDict

class RAGState(TypedDict):
    question: str
    retrieved_docs: list[dict]
    answer: str
```

Nó hỗ trợ IDE/static checker nhưng khi chạy vẫn chỉ là dict.

Field có thể không tồn tại:

```python
from typing import NotRequired, TypedDict

class RAGState(TypedDict):
    question: str
    answer: NotRequired[str]
```

## `dataclass`

Repo đang dùng kiểu này cho cấu hình chunking:

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Level:
    boundaries: frozenset[str]
    boundary_key: str
    extra: dict[str, str] = field(default_factory=dict)
```

- Tự tạo constructor và biểu diễn object.
- `frozen=True` ngăn gán lại field.
- `default_factory=dict` tạo dict riêng cho mỗi instance.

Không dùng mutable default kiểu `extra: dict = {}`.

## Pydantic `BaseModel`

```python
from pydantic import BaseModel, Field

class Citation(BaseModel):
    document_number: str
    article: str | None = None
    source_url: str | None = None

class LegalAnswer(BaseModel):
    answer: str
    citations: list[Citation]
    sufficient_context: bool
```

```python
result = LegalAnswer(
    answer="Chưa đủ căn cứ.",
    citations=[],
    sufficient_context=False,
)
print(result.model_dump())
```

Dữ liệu thiếu field bắt buộc hoặc sai kiểu sẽ gây validation error.

## Dùng với structured output

```python
structured_model = model.with_structured_output(LegalAnswer)
result = structured_model.invoke(prompt)
print(result.answer)
```

Schema làm output ổn định hơn, không làm câu trả lời pháp lý tự động đúng.

## Metadata pháp luật tối thiểu

```python
class LegalDocumentMetadata(BaseModel):
    document_type: str
    document_number: str
    issuing_authority: str | None = None
    issue_date: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    status: str | None = None
    article: str | None = None
    source_url: str | None = None
```

Trong production, ngày tháng cần định dạng thống nhất và tình trạng hiệu lực phải đến từ nguồn kiểm chứng được.

## Lỗi thường gặp

- **Nhầm type hint với validation:** `TypedDict` không chặn dữ liệu sai lúc runtime.
- **Bắt buộc field mà corpus thường thiếu:** ingestion sẽ lỗi; xác định rõ field nào thực sự optional.
- **Schema quá sâu:** chỉ bắt đầu với field chương trình thật sự sử dụng.
- **Ngày tháng là `str` nhưng không thống nhất:** nên dùng một định dạng như `YYYY-MM-DD`.

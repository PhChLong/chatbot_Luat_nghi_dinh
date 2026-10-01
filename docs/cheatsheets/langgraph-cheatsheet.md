# LangGraph cheatsheet cơ bản

## Ý tưởng chính

LangGraph tổ chức chương trình AI thành một **đồ thị có trạng thái**:

- **State**: dữ liệu đi xuyên suốt chương trình.
- **Node**: hàm nhận state và trả về phần cần cập nhật.
- **Edge**: đường đi giữa các node.
- **Conditional edge**: chọn đường đi dựa trên state.

Hãy hình dung nó như một flowchart chạy được.

## Graph nhỏ nhất

```python
from typing import TypedDict
from langgraph.graph import END, START, StateGraph

class ChatState(TypedDict):
    question: str
    answer: str

def answer_question(state: ChatState) -> dict[str, str]:
    return {"answer": f"Câu hỏi nhận được: {state['question']}"}

builder = StateGraph(ChatState)
builder.add_node("answer", answer_question)
builder.add_edge(START, "answer")
builder.add_edge("answer", END)

graph = builder.compile()
result = graph.invoke({"question": "RAG là gì?", "answer": ""})
print(result["answer"])
```

Luồng: `START -> answer -> END`.

`compile()` tạo graph có thể chạy. `invoke()` chạy một lần và trả về state cuối.

## Rẽ nhánh

```python
from typing import Literal

def classify(state: ChatState) -> dict[str, str]:
    route = "legal" if "nghị định" in state["question"].lower() else "general"
    return {"route": route}

def choose_route(state) -> Literal["legal", "general"]:
    return "legal" if state["route"] == "legal" else "general"

builder.add_conditional_edges("classify", choose_route)
```

Hàm route chỉ trả tên node tiếp theo; công việc thực tế nên nằm trong node.

## Áp dụng vào repo này

```python
class RAGState(TypedDict):
    question: str
    retrieved_docs: list[dict]
    answer: str
```

Luồng tối thiểu:

```text
START -> retrieve -> generate_answer -> END
```

- `retrieve`: gọi `RAGRetrieval.query()`.
- `generate_answer`: đưa question và retrieved docs vào `ChatOllama`.

Đây là cấu trúc minh họa; repo hiện chưa nối pipeline RAG bằng LangGraph.

## Lỗi thường gặp

- **Node trả sai key:** schema có `answer` nhưng node trả `response`.
- **Quên `compile()`:** `StateGraph` mới chỉ là builder.
- **State quá lớn:** không nhét model, database client hoặc corpus vào state.
- **Route làm quá nhiều việc:** hàm route chỉ nên chọn đường đi.
- **Tưởng type hint là validation:** `TypedDict` không tự kiểm tra dữ liệu lúc runtime.

## Nhớ nhanh

```text
StateGraph(Schema)
  -> add_node(...)
  -> add_edge(...) / add_conditional_edges(...)
  -> compile()
  -> invoke(initial_state)
```

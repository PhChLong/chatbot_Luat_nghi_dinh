from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class ChatState(TypedDict):
    question: str
    route: str
    answer: str


# Node phân loại: trả về phần cập nhật state.
def classify(state: ChatState) -> dict[str, str]:
    question = state["question"].lower()
    route = "legal" if "nghị định" in question else "general"
    return {"route": route}


# Hàm chọn nhánh: trả về tên node tiếp theo.
def choose_route(state: ChatState) -> Literal["legal", "general"]:
    return "legal" if state["route"] == "legal" else "general"


# Node xử lý nhánh pháp luật.
def answer_legal(state: ChatState) -> dict[str, str]:
    return {
        "answer": f"Nhánh pháp luật nhận câu hỏi: {state['question']}"
    }


# Node xử lý nhánh thông thường.
def answer_general(state: ChatState) -> dict[str, str]:
    return {
        "answer": f"Nhánh thông thường nhận câu hỏi: {state['question']}"
    }


# 1. Tạo builder và đăng ký các node.
builder = StateGraph(ChatState)

builder.add_node("classify", classify)
builder.add_node("legal", answer_legal)
builder.add_node("general", answer_general)

# 2. Khai báo luồng chạy.
builder.add_edge(START, "classify")
builder.add_conditional_edges("classify", choose_route)
builder.add_edge("legal", END)
builder.add_edge("general", END)

# 3. Tạo graph có thể chạy.
graph = builder.compile()

# 4. Chạy thử hai câu hỏi.
questions = [
    "Nghị định này quy định những gì?",
    "Xin chào bạn!",
]

for question in questions:
    result = graph.invoke({
        "question": question,
        "route": "",
        "answer": "",
    })
    print(result["answer"])
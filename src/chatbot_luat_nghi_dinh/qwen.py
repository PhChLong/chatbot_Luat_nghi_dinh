import ollama

SYSTEM = (
    "Bạn là trợ lý tra cứu văn bản pháp luật Việt Nam. "
    "Chỉ trả lời dựa trên phần NGỮ CẢNH được cung cấp. "
    "Trích dẫn nguồn theo dạng [Nghị định, Điều, Khoản]. "
    "Nếu ngữ cảnh không đủ thông tin, hãy nói rõ là không tìm thấy, không được suy đoán."
)

def answer(question: str, chunks: list[tuple[str, dict]]) -> str:
    context = "\n\n".join(
        f"[{m['nghi_dinh']} - Điều {m['dieu']}]\n{text}" for text, m in chunks
    )
    resp = ollama.chat(
        model="qwen3.5:4b",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"NGỮ CẢNH:\n{context}\n\nCÂU HỎI: {question}"},
        ],
        think=False,
        options={"temperature": 0, "num_ctx": 4096},
    )
    return resp["message"]["content"]
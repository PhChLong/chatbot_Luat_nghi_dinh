# RAG basics cheatsheet

## RAG là gì?

RAG có hai phần:

1. **Retrieval**: tìm các đoạn liên quan.
2. **Generation**: đưa chúng cho LLM để tạo câu trả lời.

Pipeline của repo:

```text
Markdown -> Document -> section/chunk -> embedding
         -> ChromaDB -> retrieval -> prompt -> ChatOllama
```

Repo đã có xử lý tài liệu, embedding, vector DB và retrieval. Việc nối retrieval vào prompt trả lời vẫn cần triển khai/kiểm chứng riêng.

## `Document`

```python
from langchain_core.documents import Document

doc = Document(
    page_content="Điều 1. Phạm vi điều chỉnh...",
    metadata={
        "document_type": "Nghị định",
        "status": "Còn hiệu lực",
        "article": "Điều 1",
    },
)
```

- `page_content`: nội dung để embedding và đưa vào prompt.
- `metadata`: dữ liệu để lọc, citation và truy nguồn.

## Chunking

Repo dùng:

```python
RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    separators=["\n\n", "\n", " ", ""],
    length_function=len,
)
```

- `chunk_size`: kích thước tối đa gần đúng.
- `chunk_overlap`: phần lặp giữa hai chunk.
- `len`: đang đo ký tự, không phải token.

Với luật, nên tách chương/điều/khoản trước rồi mới chia theo kích thước. Repo đang đi theo hướng này.

## Embedding

Embedding biến text thành vector. Nội dung gần nghĩa thường có vector gần nhau.

Lúc index và lúc query phải dùng **cùng embedding model** và cùng cách tiền xử lý. Đổi model thường đồng nghĩa phải tạo lại index.

## ChromaDB

Tên collection chỉ dùng chữ ASCII, số, `.`, `_`, `-`; bắt đầu/kết thúc bằng chữ hoặc số.

```python
# Hợp lệ
collection_name = "luat-nghi-dinh"

# Không hợp lệ
collection_name = "luật nghị định"
```

Text và metadata vẫn có thể chứa tiếng Việt.

## Retrieval

```python
result = collection.query(
    query_embeddings=[embedded_question],
    n_results=5,
)
```

`top_k` lớn có thể tăng khả năng tìm thấy nguồn nhưng cũng đưa thêm nhiễu vào prompt.

Kết quả là list lồng vì API hỗ trợ nhiều query:

```python
documents = result["documents"][0]
metadatas = result["metadatas"][0]
distances = result["distances"][0]
```

## Distance không luôn là similarity

Repo hiện dùng `similarity = 1 - distance`. Công thức này chỉ đúng khi metric và miền giá trị phù hợp.

Ở giai đoạn đầu nên:

- Giữ tên `distance`.
- Hiểu distance nhỏ hơn là gần hơn theo metric cấu hình.
- Chỉ đổi sang similarity sau khi xác định metric và công thức.

## Tạo context

```python
def format_context(docs: list[dict]) -> str:
    blocks = []
    for doc in docs:
        meta = doc["metadata"]
        blocks.append("\n".join([
            f"Văn bản: {meta.get('name', 'Không rõ')}",
            f"Điều: {meta.get('article', 'Không rõ')}",
            f"Tình trạng: {meta.get('status', 'Chưa xác định')}",
            f"Nội dung: {doc['content']}",
        ]))
    return "\n\n---\n\n".join(blocks)
```

Prompt nên yêu cầu chỉ dùng context, nêu nguồn và nói rõ khi chưa đủ căn cứ. Prompt không thay thế kiểm tra nguồn bằng code.

## Metadata pháp luật quan trọng

- Loại và số hiệu văn bản.
- Cơ quan, ngày ban hành.
- Ngày bắt đầu/kết thúc hiệu lực.
- Tình trạng hiệu lực.
- Chương, điều, khoản, điểm.
- URL/định danh nguồn và phiên bản.

Thiếu metadata có thể khiến chatbot tìm đúng câu chữ nhưng viện dẫn sai phiên bản hoặc văn bản hết hiệu lực.

## Lỗi thường gặp

- Có retrieval result không có nghĩa câu trả lời đúng.
- Bỏ metadata khiến citation không truy ngược được.
- Chunk quá nhỏ làm mất điều kiện/ngoại lệ.
- Chunk quá lớn làm embedding kém tập trung.
- Trộn hai embedding model làm khoảng cách mất ý nghĩa.
- Một vài câu hỏi chạy đúng không thay thế RAG evaluation.

## Nhớ nhanh

```text
Retrieval tốt chưa đủ để generation đúng.
Generation hay chưa chứng minh citation đúng.
Schema đúng chưa chứng minh nội dung đúng.
Một lần chạy thành công chưa phải RAG evaluation.
```

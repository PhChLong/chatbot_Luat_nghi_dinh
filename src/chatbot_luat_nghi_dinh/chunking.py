
import re
from dataclasses import dataclass, field
from pathlib import Path

from langchain_community.document_loaders import (
    TextLoader,
)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

MARKER_RE = re.compile(r"^[A-Z][A-Z_\-]+$")
WANTED = {
    "DOCUMENT_TYPE": "document_type",
    "DOCUMENT_TITLE": "document_title",
    "PREAMBLE": "preamble",
}

#@ Lấy loại, tiêu đề và phần căn cứ từ các marker của văn bản Markdown.
def extract_sections(text: str) -> dict[str, str]:
    sections : dict[str, list[str]]= {}
    current : str|None= None  #? Khóa metadata của section đang mở.

    for raw in text.splitlines():
        line = raw.strip()

        #? Marker mới thay section đang mở; chỉ giữ các loại trong WANTED.
        if MARKER_RE.match(line):
            current = WANTED.get(line)
            if current:
                sections[current] = []
            continue

        #? Chỉ thu thập dòng có nội dung trong section cần lấy.
        if current and line:
            sections[current].append(line)

    return {
        "document_type": " ".join(sections.get("document_type", [])),
        #? Tiêu đề bị ngắt dòng giữa câu nên nối bằng khoảng trắng.
        "document_title": " ".join(sections.get("document_title", [])),
        #? Giữ xuống dòng giữa các căn cứ trong phần mở đầu.
        "preamble": "\n".join(sections.get("preamble", [])),
    }

#@ Đọc các file Markdown và tạo Document kèm metadata từ YAML đầu file.
def turn_files_into_documents(data_path:Path = Path("../../data/md")) -> list[Document]:
    all_documents :list[Document] = []
    for path in data_path.glob("*.md"):
        with open(path, "r", encoding="utf-8") as f:
            f.readline()
            status = f.readline().split(":", 1)[1].strip()
            issue_date = f.readline().split(":", 1)[1].strip().strip("'")
            eff_from = f.readline().split(":", 1)[1].strip().strip("'")
            eff_to = f.readline().split(":", 1)[1].strip().strip("'")

        loader = TextLoader(file_path=path, encoding="utf-8")
        doc : Document = loader.load()[0]

        doc.metadata.update({
            "name": path.stem,
            "status": status,
            "issue_date": issue_date,
            "eff_from": eff_from,
            "eff_to": eff_to,
            **extract_sections(doc.page_content),
        })
        all_documents.append(doc)
    return all_documents

@dataclass(frozen=True)
class Level:  #? Cấu hình marker và khóa metadata cho một tầng tách văn bản.
    boundaries: frozenset[str]            #? Các marker dùng để cắt ở tầng này.
    boundary_key: str                     #? Khóa metadata lấy từ dòng có nội dung sau marker.
    extra: dict[str, str] = field(default_factory=dict)  #? Ánh xạ khóa metadata sang marker bổ sung.


LEVELS: list[Level] = [
    Level(
        boundaries=frozenset({"PROV_CHAPTER", "PROV_APPENDIX"}),
        boundary_key="chapter",
        extra={"chapter_title": "PROV_CHAPTER_TITLE"},
    ),
    Level(
        boundaries=frozenset({"PROV-ARTICLE"}),
        boundary_key="article",
    ),
]


#@ Lấy dòng có nội dung đầu tiên sau marker, hoặc từ đầu nếu không có marker.
def _line_below(lines: list[str], marker: str | None = None) -> str | None:
    """Dòng non-empty đầu tiên ngay dưới `marker`. marker=None thì lấy từ đầu."""
    start = 0
    if marker is not None:
        for i, raw in enumerate(lines):
            if raw.strip() == marker:
                start = i + 1
                break
        else:
            return None
    for raw in lines[start:]:
        if raw.strip():
            return raw.strip()
    return None


#@ Cắt văn bản theo các marker ranh giới thành cặp marker và nội dung.
def _cut(text: str, boundaries: frozenset[str]) -> list[tuple[str, str]]:
    """Cắt text thành [(marker, content)], bỏ phần trước boundary đầu tiên."""
    parts: list[tuple[str, str]] = []
    kind: str | None = None
    buf: list[str] = []

    for raw in text.splitlines():
        if raw.strip() in boundaries:
            if kind is not None:
                parts.append((kind, "\n".join(buf).strip()))
            kind, buf = raw.strip(), []
        elif kind is not None:
            buf.append(raw.rstrip())

    if kind is not None:
        parts.append((kind, "\n".join(buf).strip()))
    return parts


#@ Tách Document lần lượt theo các tầng và chuyển thông tin section vào metadata.
def split_document(documents: list[Document], levels: list[Level] = LEVELS) -> list[Document]:
    #? Hết tầng thì trả lại danh sách hiện có.
    if not levels:
        return documents

    level, rest = levels[0], levels[1:]
    next_docs: list[Document] = []

    for d in documents:
        parts = _cut(d.page_content, level.boundaries)

        #? Giữ nguyên Document không có boundary để tầng sau tiếp tục xử lý.
        if not parts:
            next_docs.append(d)
            continue

        for kind, content in parts:
            lines = content.splitlines()
            meta = {**d.metadata, "section_kind": kind}

            if (v := _line_below(lines)) is not None:
                meta[level.boundary_key] = v
            for key, marker in level.extra.items():
                if (v := _line_below(lines, marker)) is not None:
                    meta[key] = v

            next_docs.append(Document(page_content=content, metadata=meta))

    #? Đưa toàn bộ kết quả của tầng này qua tầng kế tiếp.
    return split_document(next_docs, rest)

#@ Chia các section thành chunk văn bản có chồng lấn để phục vụ retrieval.
def chunk_documents(
        sections_from_all_documents:list[Document],
        chunk_size: int = 1000,
        chunk_overlap:int = 200,
        ) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size = chunk_size,
        chunk_overlap = chunk_overlap,
        separators = ["\n\n", "\n", " ", ""],
        length_function = len,
    )
    chunks : list[Document] = splitter.split_documents(sections_from_all_documents)
    return chunks

#@ Chạy lần lượt bước đọc file, tách section và chia chunk.
def process_all(
        path:Path =  Path("../../data/md"),
        chunk_size: int = 1000,
        chunk_overlap:int = 200,
        ) -> list[Document]:
    all_documents :list[Document] = turn_files_into_documents(path)
    sections_from_all_documents:list[Document] = split_document(all_documents)
    chunks_from_all_documents:list[Document] =  chunk_documents(sections_from_all_documents, chunk_size, chunk_overlap)
    return chunks_from_all_documents

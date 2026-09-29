
from pathlib import Path
from langchain_community.document_loaders import (
    TextLoader,
)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from dataclasses import dataclass, field
import re

MARKER_RE = re.compile(r"^[A-Z][A-Z_\-]+$")
WANTED = {
    "DOCUMENT_TYPE": "document_type",
    "DOCUMENT_TITLE": "document_title",
    "PREAMBLE": "preamble",
}

def extract_sections(text: str) -> dict[str, str]:
    sections : dict[str, list[str]]= {}
    current : str|None= None  # key metadata của section đang mở

    for raw in text.splitlines():
        line = raw.strip()

        # Gặp marker: đóng section cũ, mở section mới nếu nằm trong WANTED
        if MARKER_RE.match(line):
            current = WANTED.get(line)
            if current:
                sections[current] = []
            continue

        # Đang trong section cần lấy và dòng không rỗng thì thu thập
        if current and line:
            sections[current].append(line)

    return {
        "document_type": " ".join(sections.get("document_type", [])),
        # Title bị ngắt dòng giữa câu nên nối bằng khoảng trắng
        "document_title": " ".join(sections.get("document_title", [])),
        # Preamble mỗi dòng là một "Căn cứ ..." nên giữ xuống dòng
        "preamble": "\n".join(sections.get("preamble", [])),
    }

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
class Level:
    boundaries: frozenset[str]            # marker dùng để cắt ở tầng này
    boundary_key: str                     # metadata key = dòng non-empty ngay dưới marker cắt
    extra: dict[str, str] = field(default_factory=lambda: {})  # metadata key -> marker khác bên trong section


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


def split_document(documents: list[Document], levels: list[Level] = LEVELS) -> list[Document]:
    # Hết tầng: trả nguyên list
    if not levels:
        return documents

    level, rest = levels[0], levels[1:]
    next_docs: list[Document] = []

    for d in documents:
        parts = _cut(d.page_content, level.boundaries)

        # Tầng này không có boundary: giữ nguyên doc, để tầng sau xử lý
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

    # Đệ quy 1 lần cho toàn bộ list xuống tầng kế
    return split_document(next_docs, rest)

def chunk_documents(sections_from_all_documents:list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size = 1000,
        chunk_overlap = 200,
        separators = ["\n\n", "\n", " ", ""],
        length_function = len,
    )
    chunks : list[Document] = splitter.split_documents(sections_from_all_documents)
    return chunks

def process_all() -> list[Document]:
    all_documents :list[Document] = turn_files_into_documents()
    sections_from_all_documents:list[Document] = split_document(all_documents)
    chunks_from_all_documents:list[Document] =  chunk_documents(sections_from_all_documents)
    return chunks_from_all_documents

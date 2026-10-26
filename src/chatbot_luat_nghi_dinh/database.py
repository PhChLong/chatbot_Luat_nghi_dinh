import json
import os
import re
import sqlite3
import tempfile
import unicodedata
from pathlib import Path
from threading import Lock
from typing import Literal, TypedDict

from bs4 import BeautifulSoup, Tag


_MANIFEST_LOCK = Lock()


class ParsedUnit(TypedDict):
    """Một đơn vị đã parse, chưa được cấp id trong SQLite."""

    local_id: int
    parent_local_id: int | None
    unit_type: Literal["article", "clause", "point"]
    label: str
    article_label: str
    clause_label: str | None
    title: str | None
    body: str


class ParsedArticle(TypedDict):
    """Các đoạn nguyên văn theo thứ tự, dùng để chunk toàn bộ một điều."""

    label: str
    title: str
    parts: list[str]


class ParsedDocument(TypedDict):
    units: list[ParsedUnit]
    articles: list[ParsedArticle]
    document_type: str
    document_title: str
    preamble: str


def create_database(database_path: str | Path = "legal_units.db") -> None:
    """Tạo bảng legal_units trong legal_units.db.

    Ý nghĩa các field:
    - id: khóa chính riêng của mỗi đơn vị điều/khoản/điểm.
    - document_id: ID nghị định/phiên bản nguồn, tương ứng metadata.document_id.
    - parent_id: id của đơn vị cha; NULL khi không có đơn vị cha được lưu.
    - unit_type: loại đơn vị, lưu article (điều), clause (khoản), point (điểm).
    - label: nhãn của chính đơn vị, ví dụ '5', '1', 'a'.
    - article_label: nhãn điều chứa đơn vị; với hàng điều, bằng label của nó.
    - clause_label: nhãn khoản chứa đơn vị; với hàng khoản, bằng label của nó;
      với hàng điều, để NULL.
    - title: tiêu đề của đơn vị nếu có, không gồm nhãn điều/khoản/điểm.
    - body: nội dung trực tiếp của đơn vị, không lặp nội dung các đơn vị con.

    Ví dụ điểm a khoản 1 Điều 5: label='a', article_label='5', clause_label='1'.
    Khi nạp dữ liệu, hai nhãn địa chỉ phải nhất quán với quan hệ parent_id.
    CREATE TABLE IF NOT EXISTS không cập nhật schema của bảng đã tồn tại.
    """
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_units (
                id INTEGER PRIMARY KEY,
                document_id INTEGER NOT NULL,
                parent_id INTEGER REFERENCES legal_units(id),
                unit_type TEXT NOT NULL,
                label TEXT NOT NULL,
                article_label TEXT,
                clause_label TEXT,
                title TEXT,
                body TEXT
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def create_metadata_table(database_path: str | Path = "legal_units.db") -> None:
    """Tạo bảng metadata cấp văn bản trong legal_units.db.

    Ý nghĩa các field:
    - document_id: khóa chính xác định nghị định/phiên bản nguồn được lưu.
    - name: tên file nguồn không gồm đuôi .html, dùng khi tra document_name.
    - source: đường dẫn file nguồn.
    - status: tình trạng hiệu lực lấy từ nguồn.
    - issue_date: ngày ban hành.
    - eff_from: ngày bắt đầu hiệu lực.
    - eff_to: ngày hết hiệu lực nếu có.
    - document_type: loại văn bản.
    - document_title: tiêu đề văn bản.
    - preamble: phần căn cứ/mở đầu của văn bản.
    """
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                document_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                source TEXT,
                status TEXT,
                issue_date TEXT,
                eff_from TEXT,
                eff_to TEXT,
                document_type TEXT,
                document_title TEXT,
                preamble TEXT
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


#@ Lấy metadata theo tên nguồn; trả None nếu không có, báo lỗi nếu tên không duy nhất.
def query_metadata(
    document_name: str,
    database_path: str | Path = "legal_units.db",
) -> dict[str, str | int | None] | None:
    #? Chỉ mở database đã tồn tại để truy vấn không tạo nhầm file rỗng.
    database_uri: str = Path(database_path).resolve().as_uri() + "?mode=ro"
    connection: sqlite3.Connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows: list[sqlite3.Row] = connection.execute(
            "SELECT * FROM metadata WHERE name = ? LIMIT 2", (document_name,)
        ).fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            raise ValueError(
                f"Tên {document_name} khớp nhiều bản ghi metadata; chưa thể chọn văn bản."
            )
        return dict(rows[0])
    finally:
        connection.close()


def query_content(
    document_name: str,
    unit_type: str,
    label: str,
    article_label: str | None = None,
    clause_label: str | None = None,
) -> list[dict]:
    """Lấy một đơn vị và mọi con cháu; báo lỗi nếu địa chỉ không duy nhất.

    unit_type nhận "điều", "khoản" hoặc "điểm", tương ứng với các giá trị
    article, clause, point lưu trong legal_units. Hai nhãn địa chỉ được lọc
    trực tiếp trên các cột article_label và clause_label khi được truyền vào.
    Kết quả gồm chín field của legal_units, sắp theo id.
    Không tìm thấy thì trả về danh sách rỗng. Hai bảng phải được tạo trước.
    """
    unit_types = {"điều": "article", "khoản": "clause", "điểm": "point"}
    if unit_type not in unit_types:
        raise ValueError('unit_type phải là "điều", "khoản" hoặc "điểm".')

    connection = sqlite3.connect("legal_units.db")
    connection.row_factory = sqlite3.Row
    try:
        matches = connection.execute(
            """
            SELECT u.id, u.document_id
            FROM legal_units AS u
            JOIN metadata AS m ON m.document_id = u.document_id
            WHERE m.name = ? AND u.unit_type = ? AND u.label = ?
              AND (? IS NULL OR u.article_label = ?)
              AND (? IS NULL OR u.clause_label = ?)
            """,
            (
                document_name,
                unit_types[unit_type],
                label,
                article_label,
                article_label,
                clause_label,
                clause_label,
            ),
        ).fetchall()

        if not matches:
            return []
        if len(matches) > 1:
            raise ValueError(
                "Địa chỉ khớp nhiều đơn vị. Hãy bổ sung article_label, "
                "clause_label hoặc kiểm tra tên và phiên bản văn bản."
            )

        root = matches[0]
        rows = connection.execute(
            """
            WITH RECURSIVE subtree(id) AS (
                SELECT ?
                UNION
                SELECT child.id
                FROM legal_units AS child
                JOIN subtree AS parent ON child.parent_id = parent.id
                WHERE child.document_id = ?
            )
            SELECT u.id, u.document_id, u.parent_id, u.unit_type,
                   u.label, u.article_label, u.clause_label, u.title, u.body
            FROM legal_units AS u
            JOIN subtree AS s ON s.id = u.id
            ORDER BY u.id
            """,
            (root["id"], root["document_id"]),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def read_metadata(metadata_path: str | Path = "data/metadata.json") -> list[dict]:
    """Đọc danh sách metadata; sync[0] là SQLite, sync[1] là Chroma.

    Khóa dùng trong một tiến trình sync; không chạy crawler hoặc tiến trình
    sync khác đồng thời trên cùng file JSON.
    """
    with _MANIFEST_LOCK:
        records = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    ids, names = set(), set()
    for record in records:
        document_id, name = record["document_id"], record["name"]
        if type(document_id) is not int or document_id <= 0:
            raise ValueError("document_id phải là số nguyên dương.")
        if not isinstance(name, str) or not name or any(c in name for c in "/\\"):
            raise ValueError("name phải là tên file, không gồm đường dẫn.")
        if document_id in ids or name in names:
            raise ValueError("Metadata bị trùng document_id hoặc name.")
        ids.add(document_id)
        names.add(name)
        flags = record["sync"]
        if not isinstance(flags, list) or len(flags) != 2 or any(type(x) is not bool for x in flags):
            raise ValueError("sync phải là danh sách gồm hai boolean.")
    return records


def mark_synced(metadata_path: str | Path, document_id: int, branch: int) -> None:
    """Đọc lại JSON dưới khóa, chỉ đổi cờ của nhánh đã ghi dữ liệu thành công."""
    if branch not in (0, 1):
        raise ValueError("branch phải là 0 (SQLite) hoặc 1 (Chroma).")
    path = Path(metadata_path)
    with _MANIFEST_LOCK:
        records = json.loads(path.read_text(encoding="utf-8"))
        record = next((r for r in records if r["document_id"] == document_id), None)
        if record is None:
            raise ValueError(f"Không còn metadata cho document_id={document_id}.")
        record["sync"][branch] = True
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, delete=False,
                prefix=path.name + ".", suffix=".tmp",
            ) as stream:
                temporary = Path(stream.name)
                json.dump(records, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def parse_html(html_path: str | Path) -> ParsedDocument:
    """Đọc class HTML một lần cho cả SQLite và chunking theo điều.

    prov-content và bảng được nối vào đơn vị đang mở; chưa suy luận lại
    quan hệ cho các đoạn nội dung tự do. ID tạm chỉ dùng để nối cha khi insert.
    """
    soup = BeautifulSoup(Path(html_path).read_text(encoding="utf-8"), "html.parser")
    content = soup.select_one("article.docx-page") or soup.body or soup
    for tag in content.find_all(["script", "style"]):
        if isinstance(tag, Tag):
            tag.decompose()
    units: list[ParsedUnit] = []
    articles: list[ParsedArticle] = []
    article: ParsedUnit | None = None
    clause: ParsedUnit | None = None
    point: ParsedUnit | None = None
    current_article: ParsedArticle | None = None
    node: ParsedUnit
    document_type = ""
    titles: list[str] = []
    preamble: list[str] = []
    phase = "header"
    types = {"NGHỊ ĐỊNH", "THÔNG TƯ", "THÔNG TƯ LIÊN TỊCH", "LUẬT", "BỘ LUẬT",
             "QUYẾT ĐỊNH", "NGHỊ QUYẾT", "PHÁP LỆNH"}
    patterns = {
        "prov-article": re.compile(r"^Điều\s+(\d+[a-zđ]*)\s*[.:]?\s*(.*)$", re.I),
        "prov-clause": re.compile(r"^(\d+[a-zđ]*)\s*[.)]\s*(.*)$", re.I),
        "prov-item": re.compile(r"^([a-zđ]+)\s*[.)]\s*(.*)$", re.I),
    }
    tags = [
        t for t in content.find_all(["p", "table"])
        if isinstance(t, Tag) and t.find_parent("table") is None
    ]
    for tag in tags:
        if tag.name == "table":
            text = "\n".join(
                "\t".join(" ".join(cell.get_text(" ", strip=True).split())
                          for cell in row.find_all(["td", "th"], recursive=False)
                          if isinstance(cell, Tag))
                for row in tag.find_all("tr") if isinstance(row, Tag)
            ).strip()
        else:
            text = " ".join(tag.get_text(" ", strip=True).split())
        text = unicodedata.normalize("NFC", text)
        if not text:
            continue
        raw_classes = tag.get("class")
        classes: list[str]
        if isinstance(raw_classes, str):
            classes = raw_classes.split()
        elif isinstance(raw_classes, list):
            classes = [str(value) for value in raw_classes]
        else:
            classes = []
        if "prov-chapter" in classes or "prov-section" in classes:
            article = clause = point = None
            current_article = None
            phase = "body"
            continue
        kind = next((k for k in patterns if k in classes), None)
        if kind:
            match = patterns[kind].match(text)
            if match is None:
                raise ValueError(f"{html_path}: không đọc được nhãn {kind}: {text[:100]}")
            label, remainder = match.group(1), match.group(2)
            local_id = len(units)
            if kind == "prov-article":
                phase = "body"
                node = ParsedUnit(local_id=local_id, parent_local_id=None, unit_type="article",
                            label=label, article_label=label, clause_label=None,
                            title=remainder or None, body="")
                article, clause, point = node, None, None
                current_article = ParsedArticle(label=label, title=remainder, parts=[])
                articles.append(current_article)
            elif kind == "prov-clause":
                if article is None:
                    raise ValueError(f"{html_path}: khoản {label} không có điều cha.")
                node = ParsedUnit(local_id=local_id, parent_local_id=article["local_id"],
                            unit_type="clause", label=label, article_label=article["label"],
                            clause_label=label, title=None, body=remainder)
                clause, point = node, None
            else:
                if article is None or clause is None:
                    raise ValueError(f"{html_path}: điểm {label} không có điều hoặc khoản cha.")
                node = ParsedUnit(local_id=local_id, parent_local_id=clause["local_id"],
                            unit_type="point", label=label, article_label=article["label"],
                            clause_label=clause["label"], title=None, body=remainder)
                point = node
            units.append(node)
        elif article is not None:
            node = point if point is not None else clause if clause is not None else article
            node["body"] = "\n".join(part for part in (node["body"], text) if part)
        elif phase == "header" and tag.name != "table" and text.upper() in types:
            document_type, phase = text, "title"
        elif phase in ("title", "preamble") and tag.name != "table":
            if text.casefold().startswith(("căn cứ ", "theo đề nghị ")):
                phase = "preamble"
            (preamble if phase == "preamble" else titles).append(text)
        if current_article is not None:
            current_article["parts"].append(text)
    if not articles:
        raise ValueError(f"{html_path}: không tìm thấy prov-article.")
    return {"units": units, "articles": articles, "document_type": document_type,
            "document_title": " ".join(titles), "preamble": "\n".join(preamble)}


def insert_metadata(connection: sqlite3.Connection, metadata: dict, parsed: ParsedDocument, source: str) -> None:
    """Insert metadata; transaction và commit do hàm gọi quản lý."""
    connection.execute(
        """INSERT INTO metadata (
            document_id, name, source, status, issue_date, eff_from, eff_to,
            document_type, document_title, preamble
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (metadata["document_id"], metadata["name"], source, metadata["status"],
         metadata["issue_date"], metadata["effective_from"], metadata["effective_to"],
         parsed["document_type"], parsed["document_title"], parsed["preamble"]),
    )


def insert_unit(connection: sqlite3.Connection, document_id: int, parent_id: int | None, unit: ParsedUnit) -> int:
    """Insert một đơn vị, trả id để các đơn vị con dùng làm parent_id."""
    cursor = connection.execute(
        """INSERT INTO legal_units (
            document_id, parent_id, unit_type, label, article_label, clause_label, title, body
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (document_id, parent_id, unit["unit_type"], unit["label"], unit["article_label"],
         unit["clause_label"], unit["title"], unit["body"]),
    )
    unit_id = cursor.lastrowid
    if unit_id is None:
        raise RuntimeError("SQLite không trả về id của đơn vị vừa insert.")
    return unit_id


def sync_database(
    metadata_path: str | Path = "data/metadata.json",
    html_path: str | Path = "data/html",
    database_path: str | Path = "legal_units.db",
) -> dict:
    """Insert các văn bản có sync[0]=false; commit xong mới đổi cờ JSON.

    Một transaction cho mỗi văn bản. Văn bản đã commit được bỏ qua khi thử lại
    sau lỗi ghi JSON. Chưa hỗ trợ cập nhật nội dung văn bản đã insert.
    """
    pending = [r for r in read_metadata(metadata_path) if not r["sync"][0]]
    result = {"synced": [], "errors": []}
    if not pending:
        return result
    create_database(database_path)
    create_metadata_table(database_path)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        for record in pending:
            document_id = record["document_id"]
            try:
                source = Path(html_path) / (record["name"] + ".html")
                with connection:
                    existing = connection.execute(
                        "SELECT name FROM metadata WHERE document_id = ?", (document_id,)
                    ).fetchone()
                    if existing is not None:
                        if existing[0] != record["name"]:
                            raise ValueError("document_id đã thuộc văn bản khác trong SQLite.")
                        if not connection.execute(
                            "SELECT 1 FROM legal_units WHERE document_id = ? LIMIT 1", (document_id,)
                        ).fetchone():
                            raise ValueError("Metadata đã tồn tại nhưng chưa có nội dung; cần kiểm tra dữ liệu.")
                    else:
                        parsed = parse_html(source)
                        insert_metadata(connection, record, parsed, str(source))
                        ids = {}
                        for unit in parsed["units"]:
                            parent = unit["parent_local_id"]
                            ids[unit["local_id"]] = insert_unit(
                                connection, document_id, ids[parent] if parent is not None else None, unit
                            )
                mark_synced(metadata_path, document_id, 0)
                result["synced"].append(document_id)
            except Exception as exc:
                result["errors"].append({"document_id": document_id, "name": record["name"], "error": str(exc)})
    finally:
        connection.close()
    return result

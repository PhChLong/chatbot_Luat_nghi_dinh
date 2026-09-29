import requests
import json
from bs4 import BeautifulSoup
import re
from pathlib import Path
import yaml

def build_body(page_number, page_size=10):
    # Bám sát payload bạn đã copy; "$undefined" là chuỗi đúng nghĩa đen
    payload = {
        "administrativeUnit": "$undefined",
        "agencyIds": "$undefined",
        "agencyLevel": "TRUNG_UONG",
        "docNum": "$undefined",
        "docType": "$undefined",
        "documentName": "$undefined",
        "documentType": "$undefined",
        "effFromBegin": "$undefined",
        "effFromEnd": "$undefined",
        "effStatus": "$undefined",
        "effToEnd": "$undefined",
        "effToFrom": "$undefined",
        "fieldTypeIds": "$undefined",
        "groupVbpl": True,
        "issueDateFrom": "$undefined",
        "issueDateTo": "$undefined",
        "keyword": "$undefined",
        "majorTypeIds": "$undefined",
        "matchMode": "all_words",
        "optionDoc": "all",
        "pageNumber": page_number,
        "pageSize": page_size,
        "sortBy": "issueDate",
        "sortDirection": "desc",
        "status": "$undefined",
        "useMb25": "$undefined",
    }
    return json.dumps([payload])   # body là MẢNG chứa 1 object

def parse_flight(text):
    # Tìm dòng bắt đầu bằng "1:" và parse phần sau nó
    for line in text.splitlines():
        if line.startswith("1:"):
            return json.loads(line[2:])
    return None

def build_header_body(url):
    uuid = url.split("/")[-1]
    next_router_state_tree = "%5B%22%22%2C%7B%22children%22%3A%5B%5B%22locale%22%2C%22vi%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22van-ban%22%2C%7B%22children%22%3A%5B%5B%22category%22%2C%22chi-tiet%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%5B%22id%22%2C%22" + uuid + "%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
    headers = {
    "User-Agent": "Mozilla/5.0 (hoc-crawl-cho-mon-hoc)",
    "Content-Type": "text/plain;charset=UTF-8",
    "Next-Action": "0fb12b3561faa05adec51a82efb3e4f4f427f07b",
    "Accept": "text/x-component",
    "Accept-Language": "vi,en;q=0.9",
    "Origin": "https://vbpl.vn",
    "Referer": url,
    "Next-Router-State-Tree": next_router_state_tree,
}
    body = json.dumps([uuid])
    return headers, body


def extract_html_chunk(content: bytes, chunk_id: str = "2") -> str | None:
    """Tách mảnh HTML dạng 'T' (text chunk) khỏi response flight.

    Định dạng giả định (suy từ quan sát): <id>:T<độ dài hex>,<nội dung>
    Độ dài đếm bằng BYTE, nên phải cắt trên bytes rồi mới decode.
    """
    # Bắt đầu mảnh phải nằm ở đầu dòng, nên gắn (^|\n) để không khớp nhầm giữa nội dung
    pattern = re.compile(rb"(?:^|\n)" + chunk_id.encode() + rb":T([0-9a-fA-F]+),")
    m = pattern.search(content)
    if m is None:
        return None

    length = int(m.group(1), 16)          # số byte của phần nội dung
    start = m.end()                        # HTML bắt đầu ngay sau dấu phẩy
    raw = content[start:start + length]

    if len(raw) < length:                  # response bị cụt so với độ dài khai báo
        print(f"CẢNH BÁO: khai báo {length} byte nhưng chỉ có {len(raw)}")
    return raw.decode("utf-8")

from bs4 import BeautifulSoup


#@ Lấy text, chuẩn hóa khoảng trắng và nối các dòng.
def clean_text(node, separator=" "):
    lines = [" ".join(line.split()) for line in node.get_text().splitlines()]
    return separator.join(line for line in lines if line)


#@ Chuyển HTML thành Markdown và đánh dấu các phần của văn bản.
def html_to_md(state:dict, html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("article.docx-page") or soup.body or soup

    for tag in content.find_all(["script", "style"]):
        tag.decompose()

    for br in content.find_all("br"):
        br.replace_with("\n")
    for paragraph in content.find_all("p"):
        paragraph.append("\n")

    #? Bảng được xử lý nguyên khối, không lấy lại các đoạn bên trong.
    tags = [
        tag
        for tag in content.find_all(["p", "table"])
        if tag.find_parent("table") is None
    ]

    if not tags:
        raise ValueError(
            "Không tìm thấy <p> hoặc <table>; kiểm tra lại dữ liệu đầu vào."
        )

    document_types = {
        "THÔNG TƯ",
        "THÔNG TƯ LIÊN TỊCH",
        "NGHỊ ĐỊNH",
        "QUYẾT ĐỊNH",
        "NGHỊ QUYẾT",
        "LUẬT",
        "BỘ LUẬT",
        "PHÁP LỆNH",
    }

    blocks = []
    phase = "header"
    last_marker = None

    #? Các phần này có thể trải qua nhiều đoạn nhưng chỉ cần một marker.
    grouped = {"DOCUMENT_TITLE", "PREAMBLE", "PROV_CHAPTER_TITLE"}

    for tag in tags:
        if tag.name == "table":
            rows = []

            for tr in tag.find_all("tr"):
                row = []

                for cell in tr.find_all(["td", "th"], recursive=False):
                    text = clean_text(cell, separator="<br>")
                    text = text.replace("|", r"\|")
                    row.append(text)

                    colspan = int(cell.get("colspan", 1))
                    row.extend([""] * (colspan - 1))

                if row:
                    rows.append(row)

            if not rows:
                continue

            width = max(len(row) for row in rows)

            #? Header trống chỉ phục vụ Markdown, không phải header dữ liệu.
            table_lines = [
                "| " + " | ".join([""] * width) + " |",
                "| " + " | ".join(["---"] * width) + " |",
            ]

            for row in rows:
                row.extend([""] * (width - len(row)))
                table_lines.append("| " + " | ".join(row) + " |")

            blocks.extend(["PROV_TABLE", "\n".join(table_lines)])
            last_marker = "PROV_TABLE"
            continue

        text = clean_text(tag)

        #? Bỏ đoạn rỗng và các đường kẻ trang trí.
        if not text or not text.strip("_-—– "):
            continue

        classes = tag.get("class", [])
        lines = clean_text(tag, separator="\n").splitlines()

        #? Loại và tên văn bản có thể chung một đoạn, ngăn bằng <br>.
        if phase == "header" and lines[0].upper() in document_types:
            blocks.extend(["DOCUMENT_TYPE", lines[0]])
            phase = "title"
            last_marker = "DOCUMENT_TYPE"

            text = " ".join(lines[1:])
            if not text:
                continue

        if "prov-chapter" in classes:
            phase = "body"

            #? Tách số Chương khỏi tên nếu chúng nằm chung một đoạn.
            chapter = re.match(
                r"^(Chương\s+(?:[IVXLCDM]+|\d+))\b(.*)$",
                text,
                re.I,
            )

            if chapter:
                blocks.extend(["PROV_CHAPTER", chapter.group(1)])
                last_marker = "PROV_CHAPTER"

                text = chapter.group(2).strip()
                if not text:
                    continue

            marker = "PROV_CHAPTER_TITLE"

        elif "prov-article" in classes:
            phase, marker = "body", "PROV-ARTICLE"

        elif "prov-section" in classes:
            phase, marker = "body", "PROV_SECTION"

        elif re.fullmatch(r"Phụ lục\s+(?:[IVXLCDM]+|\d+)", text, re.I):
            phase, marker = "body", "PROV_APPENDIX"

        elif phase in {"title", "preamble"}:
            #! Đây là quy tắc theo text, không phải class có sẵn của HTML.
            if text.casefold().startswith(("căn cứ ", "theo đề nghị ")):
                phase = "preamble"

            marker = (
                "DOCUMENT_TITLE" if phase == "title" else "PREAMBLE"
            )

        elif phase == "header":
            marker = "DOCUMENT_HEADER"

        else:
            marker = "PROV_CONTENT"

        if marker != "PROV_CONTENT":
            if marker != last_marker or marker not in grouped:
                blocks.append(marker)

        blocks.append(text)
        last_marker = marker

    #? Chuyển metadata thành YAML, giữ tiếng Việt và thứ tự các key.
    metadata = yaml.safe_dump(
        state,
        allow_unicode=True,
        sort_keys=False,
    ).strip()

    markdown = "\n\n".join(blocks)

    return f"---\n{metadata}\n---\n\n{markdown}"
    
def crawl(URL, HEADERS, page_number, debug = False):
    all_urls = []

    resp = requests.post(URL, headers=HEADERS, data=build_body(page_number), timeout=15)
    resp.encoding = "utf-8"          # tránh lỗi "Nghá»‹..."
    if debug:
        print(resp.status_code)

    data = parse_flight(resp.text)
    if data is None:
        print(resp.text[:500])       # không thấy dòng "1:" -> in ra xem có gì
    else:
        print("total:", data["total"])
        for it in data["items"]:
            if debug:
                print( it["docNum"],
                    "|", it["effStatus"]["name"],
                    "|", it["issueDate"],
                    "|", it["effFrom"],
                    "|", it["document_url"]
                )
            state = {
                    "status": it["effStatus"]["name"],
                    "issue date": it["issueDate"][:10],
                    "effective from": it['effFrom'][:10]
                }   
            all_urls.append((it["docNum"], state, it["document_url"]))

    for doc_num, state, url in all_urls:
        file_name = "-".join(doc_num.split("/"))

        header, body = build_header_body(url)
        resp = requests.post(url, headers=header, data=body, timeout=15)
        html = extract_html_chunk(resp.content)

        if html is None:
            print("Không thấy mảnh '2:T...'. In 300 byte đầu để xem:")
            print(resp.content[:300])
        else:
            if debug:
                print("độ dài (ký tự):", len(html))
                print("kết thúc bằng </html>?", html.rstrip().endswith("</html>"))

            with open(f"data/html/{file_name}.html", "w", encoding="utf-8") as f:
                f.write(html)

            html_path = Path(f"data/html/{file_name}.html")
            html = html_path.read_text(encoding="utf-8")

            markdown = html_to_md(state, html)
            md_path = Path(f"data/md/{file_name}.md")
            md_path.write_text(markdown, encoding="utf-8")
        print()
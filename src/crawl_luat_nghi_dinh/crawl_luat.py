import json
import os
import re
from pathlib import Path

import requests


# @ Tạo JSON body tìm kiếm cho trang và kích thước trang được yêu cầu.
def build_body(page_number, page_size=10):
    # ? "$undefined" là chuỗi literal trong payload đã quan sát.
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
    return json.dumps([payload])  # ? Body là mảng chứa một object.


# @ Đọc dòng dữ liệu "1:" trong phản hồi Flight và trả về JSON đã giải mã.
def parse_flight(text):
    # ? Dữ liệu cần lấy nằm sau tiền tố "1:".
    for line in text.splitlines():
        if line.startswith("1:"):
            return json.loads(line[2:])
    return None


# @ Tạo header và body cho request lấy nội dung từ URL văn bản.
def build_header_body(url):
    uuid = url.split("/")[-1]
    next_router_state_tree = (
        "%5B%22%22%2C%7B%22children%22%3A%5B%5B%22locale%22%2C%22vi%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22van-ban%22%2C%7B%22children%22%3A%5B%5B%22category%22%2C%22chi-tiet%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%5B%22id%22%2C%22"
        + uuid
        + "%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
    )
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


# @ Tách HTML theo chunk ID từ phản hồi Flight; trả về None nếu không thấy.
def extract_html_chunk(content: bytes, chunk_id: str = "2") -> str | None:
    """Tách mảnh HTML dạng 'T' (text chunk) khỏi response flight.

    Định dạng giả định (suy từ quan sát): <id>:T<độ dài hex>,<nội dung>
    Độ dài đếm bằng BYTE, nên phải cắt trên bytes rồi mới decode.
    """
    # ? Neo đầu dòng để tránh khớp nhầm chuỗi giống marker trong nội dung.
    pattern = re.compile(rb"(?:^|\n)" + chunk_id.encode() + rb":T([0-9a-fA-F]+),")
    m = pattern.search(content)
    if m is None:
        return None

    length = int(m.group(1), 16)  # ? Độ dài nội dung tính bằng byte.
    start = m.end()  # ? HTML bắt đầu ngay sau dấu phẩy.
    raw = content[start : start + length]

    if len(raw) < length:  #! Phản hồi bị cụt so với độ dài khai báo.
        raise ValueError(f"HTML bị cụt: khai báo {length} byte nhưng chỉ có {len(raw)}")
    return raw.decode("utf-8")


# @ Giữ HTML gốc và một manifest metadata dùng cho hai nhánh sync.
def crawl(URL, HEADERS, page_number, debug=False):
    """Crawl văn bản mới, không tạo Markdown và không refresh văn bản đã lưu.

    data/metadata.json chứa ID số nguyên ổn định theo name.
    sync[0] dành cho SQLite, sync[1] dành cho Chroma; ban đầu đều false.
    Không chạy crawler đồng thời với sync trên cùng manifest.
    """
    html_dir = Path("data/html")
    html_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = Path("data/metadata.json")
    records = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else []
    by_name = {record["name"]: record for record in records}
    next_id = max((record["document_id"] for record in records), default=0) + 1
    resp = requests.post(URL, headers=HEADERS, data=build_body(page_number), timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    data = parse_flight(resp.text)
    if data is None:
        raise ValueError("Không đọc được danh sách văn bản từ phản hồi Flight.")

    for item in data["items"]:
        name = "-".join(item["docNum"].split("/"))
        if not name or any(c in name for c in "/\\"):
            raise ValueError("Số hiệu không thể dùng làm tên file.")
        source = html_dir / (name + ".html")
        if name in by_name and source.exists():
            if debug:
                print(f"[SKIP] Đã lưu {name}")
            continue
        url = item["document_url"]
        headers, body = build_header_body(url)
        response = requests.post(url, headers=headers, data=body, timeout=15)
        response.raise_for_status()
        html = extract_html_chunk(response.content)
        if html is None:
            print(f"[ERROR] {name}: không tìm thấy HTML, chưa ghi metadata.")
            continue
        temporary_html = source.with_suffix(".html.tmp")
        temporary_html.write_text(html, encoding="utf-8")
        os.replace(temporary_html, source)
        if name not in by_name:
            record = {
                "document_id": next_id,
                "name": name,
                "status": item["effStatus"]["name"],
                "issue_date": item["issueDate"][:10] if item.get("issueDate") else None,
                "effective_from": item["effFrom"][:10] if item.get("effFrom") else None,
                "effective_to": item["effTo"][:10] if item.get("effTo") else None,
                "sync": [False, False],
            }
            records.append(record)
            by_name[name] = record
            next_id += 1
        temporary_json = metadata_path.with_suffix(".json.tmp")
        temporary_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary_json, metadata_path)
        if debug:
            print(f"[CRAWLED] {name}")

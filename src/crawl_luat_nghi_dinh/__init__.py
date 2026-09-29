from .crawl_luat import *
URL = "https://vbpl.vn/van-ban/trung-uong"

# Copy từ DevTools -> Headers -> Request headers của request POST đó
HEADERS = {
    "User-Agent": "Mozilla/5.0 (hoc-crawl-cho-mon-hoc)",
    "Content-Type": "text/plain;charset=UTF-8",  # kiểm tra lại đúng giá trị trong DevTools
    "Next-Action": "c529d164f28418e5898a834422629e64c6816af1",
    "Accept": "text/x-component",                # kiểm tra lại
    "Origin": "https://vbpl.vn",
    "Referer": URL,
}

def main() -> None:
    for page_number in range(2):
        crawl(URL, HEADERS, page_number)

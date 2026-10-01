from .crawl_luat import *

URL = "https://vbpl.vn/van-ban/trung-uong"

#? Các header này được lấy từ request POST trong DevTools.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (hoc-crawl-cho-mon-hoc)",
    "Content-Type": "text/plain;charset=UTF-8",  #? Giá trị lấy từ DevTools.
    "Next-Action": "c529d164f28418e5898a834422629e64c6816af1",
    "Accept": "text/x-component",                #? Giá trị lấy từ DevTools.
    "Origin": "https://vbpl.vn",
    "Referer": URL,
}

#@ Duyệt năm trang kết quả và gọi crawler cho từng trang.
def main() -> None:
    for page_number in range(5):
        crawl(URL, HEADERS, page_number)

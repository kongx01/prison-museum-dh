from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

DEFAULT_URL = (
    "https://www.jalan.net/kankou/spt_01211cc3290031814/kuchikomi/"
    "?resultSort=pd&rootCd=7741&screenId=OUW2202"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

REQUEST_TIMEOUT = 30
RETRY = 3
RETRY_SLEEP = 5.0


def _preview(text: str, max_chars: int) -> str:
    t = text.replace("\n", "↵")
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 3] + "..."


def _debug_print(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def fetch_html(session: requests.Session, url: str) -> str:
    last_err: Optional[BaseException] = None
    for attempt in range(RETRY):
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            # Content-Type は Windows-31J（Shift_JIS 系）のことが多い
            return r.content.decode("cp932", errors="replace")
        except Exception as e:
            last_err = e
            if attempt + 1 < RETRY:
                time.sleep(RETRY_SLEEP)
    raise last_err  # type: ignore[misc]


def parse_total_and_per_page(soup: BeautifulSoup) -> tuple[Optional[int], int]:
    """例: 「1 - 10件（全1,471件中）」から総件数と1ページあたり件数を推定。"""
    text = soup.get_text(" ", strip=True)
    m = re.search(r"(\d+)\s*-\s*(\d+)\s*件.*?全\s*([\d,]+)\s*件", text)
    if not m:
        return None, 10
    start, end, total_s = m.groups()
    per_page = int(end) - int(start) + 1
    total = int(total_s.replace(",", ""))
    return total, per_page


def max_page_from_pager(soup: BeautifulSoup) -> Optional[int]:
    nums: List[int] = []
    for a in soup.select("div.pager a[href*='page_']"):
        m = re.search(r"/page_(\d+)/", a.get("href") or "")
        if m:
            nums.append(int(m.group(1)))
    return max(nums) if nums else None


def parse_review_blocks(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    ul = soup.select_one("ul.cassetteList-review.cassetteList-review-02")
    if not ul:
        return []
    rows: List[Dict[str, Any]] = []
    for li in ul.find_all("li", recursive=False):
        block = li.select_one(".item-listContents")
        if not block:
            continue
        title_a = block.select_one(".item-title a")
        title = title_a.get_text(strip=True) if title_a else ""
        detail_href = title_a.get("href", "") if title_a else ""
        m_id = re.search(r"/kuchikomi/(\d+)/?", detail_href)
        kuchikomi_id = m_id.group(1) if m_id else ""

        rp = block.select_one(".item-info .reviewPoint")
        rating = rp.get_text(strip=True) if rp else ""

        inner = block.select_one(".item-reviewTextInner")
        if inner:
            body = inner.get_text("\n", strip=True)
        else:
            body = ""

        detail_map: Dict[str, str] = {}
        for line_li in block.select(".item-reviewDetail li"):
            t = line_li.get_text(strip=True)
            if "：" in t:
                k, v = t.split("：", 1)
                detail_map[k.strip()] = v.strip()
            else:
                detail_map[t] = ""

        thumb_img = block.select_one(".item-userThumb img")
        thumb_alt = (thumb_img.get("alt") or "").strip() if thumb_img else ""

        name_el = block.select_one(".item-name a")
        user_name = name_el.get_text(strip=True) if name_el else ""
        if not user_name:
            user_name = thumb_alt

        profile_spans = [
            sp.get_text(strip=True)
            for sp in block.select(".item-name span")
            if "tsuuTag" not in (sp.get("class") or [])
        ]
        profile = profile_spans[0] if profile_spans else ""

        like_btn = block.select_one(".btnKuchiLike[data-kuchikomi-id]")
        if like_btn and not kuchikomi_id:
            kuchikomi_id = like_btn.get("data-kuchikomi-id") or ""

        rows.append(
            {
                "kuchikomi_id": kuchikomi_id,
                "title": title,
                "rating": rating,
                "body": body,
                "visit_period": detail_map.get("行った時期", ""),
                "post_date": detail_map.get("投稿日", ""),
                "user_name": user_name,
                "user_profile": profile,
                "detail_url": "https:" + detail_href
                if detail_href.startswith("//")
                else detail_href,
            }
        )
    return rows


def build_page_url(list_base: str, page: int, query: str) -> str:
    q = query.lstrip("?")
    if page <= 1:
        return f"{list_base}?{q}" if q else list_base.rstrip("/") + "/"
    return f"{list_base}page_{page}/?{q}" if q else f"{list_base}page_{page}/"


def split_base_and_query(start_url: str) -> tuple[str, str]:
    u = start_url.split("?", 1)
    base = u[0]
    if not base.endswith("/"):
        base += "/"
    query = u[1] if len(u) > 1 else ""
    return base, query


def run(
    start_url: str,
    out_csv: str,
    delay_sec: float,
    max_pages: Optional[int],
    *,
    debug: bool = False,
    debug_body_chars: int = 120,
) -> None:
    base, query = split_base_and_query(start_url)

    if debug:
        _debug_print("【调试】输入参数:")
        _debug_print(f"  start_url = {start_url!r}")
        _debug_print(f"  out_csv   = {out_csv!r}")
        _debug_print(f"  delay_sec = {delay_sec}")
        _debug_print(f"  max_pages = {max_pages!r}")
        _debug_print(f"  debug_body_chars = {debug_body_chars}")

    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.trust_env = False
    except AttributeError:
        session.proxies = {"http": None, "https": None}

    first_url = build_page_url(base, 1, query)
    if debug:
        _debug_print(f"【调试】list_base = {base!r}, query = {query!r}")
        _debug_print(f"【调试】第 1 页请求 URL = {first_url}")

    html = fetch_html(session, first_url)
    if debug:
        _debug_print(
            f"【调试】第 1 页 HTML 解码后长度 = {len(html)} 字符（cp932）"
        )

    soup = BeautifulSoup(html, "html.parser")

    total, per_page = parse_total_and_per_page(soup)
    last_link = max_page_from_pager(soup)

    if total and per_page:
        total_pages = (total + per_page - 1) // per_page
    elif last_link:
        total_pages = last_link
    else:
        total_pages = 1

    if max_pages is not None:
        total_pages = min(total_pages, max_pages)

    if debug:
        _debug_print(
            "【调试】解析结果: "
            f"总件数={total!r}, 每页约={per_page}, "
            f"分页链接最大页={last_link!r}, 将爬取页数={total_pages}"
        )

    fieldnames = [
        "page",
        "index_on_page",
        "kuchikomi_id",
        "title",
        "rating",
        "body",
        "visit_period",
        "post_date",
        "user_name",
        "user_profile",
        "detail_url",
    ]

    n_written = 0
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()

        for page in range(1, total_pages + 1):
            url = first_url if page == 1 else build_page_url(base, page, query)
            if page > 1:
                time.sleep(delay_sec)
                html = fetch_html(session, url)
                soup = BeautifulSoup(html, "html.parser")

            if debug and page > 1:
                _debug_print(f"【调试】第 {page} 页请求 URL = {url}")
                _debug_print(f"【调试】第 {page} 页 HTML 长度 = {len(html)}")

            rows = parse_review_blocks(soup)
            if debug:
                if not rows:
                    _debug_print(
                        f"【调试】第 {page} 页: 未解析到评论 "
                        "（ul.cassetteList-review 为空或结构变化）"
                    )
                else:
                    _debug_print(
                        f"【调试】第 {page} 页: 本页 {len(rows)} 条，摘要如下 ——"
                    )
                    for i, row in enumerate(rows, start=1):
                        _debug_print(
                            f"  [{i}] id={row.get('kuchikomi_id')} | "
                            f"★{row.get('rating')} | {row.get('title')!r} | "
                            f"行った={row.get('visit_period')!r} | "
                            f"投稿={row.get('post_date')!r}"
                        )
                        _debug_print(
                            f"      用户={row.get('user_name')!r} | "
                            f"属性={row.get('user_profile')!r} | "
                            f"url={row.get('detail_url')!r}"
                        )
                        _debug_print(
                            f"      正文预览: {_preview(row.get('body') or '', debug_body_chars)!r}"
                        )

            for i, row in enumerate(rows, start=1):
                row_out = {**row, "page": page, "index_on_page": i}
                w.writerow(row_out)
                n_written += 1

            print(f"page {page}/{total_pages}  (+{len(rows)} rows, cumulative {n_written})")

    print(f"Done. Wrote {n_written} rows to {out_csv}")
    if (
        total is not None
        and n_written != total
        and max_pages is None
    ):
        print(
            f"Warning: expected about {total} reviews but got {n_written}.",
            file=sys.stderr,
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="Scrape Jalan kuchikomi list to CSV.")
    ap.add_argument("--url", default=DEFAULT_URL, help="一覧ページの URL（1ページ目）")
    ap.add_argument(
        "--out",
        default="jalan_abashiri_kuchikomi.csv",
        help="出力 CSV パス",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="ページ間の待機秒数",
    )
    ap.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="デバッグ用: 最大ページ数で打ち切り",
    )
    ap.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="stderr に入力参数と各页每条クチコミの摘要（正文预览）を出力",
    )
    ap.add_argument(
        "--debug-body",
        type=int,
        default=120,
        metavar="N",
        help="--debug 时正文预览最大字符数（默认 120）",
    )
    args = ap.parse_args()
    run(
        args.url,
        args.out,
        args.delay,
        args.max_pages,
        debug=args.debug,
        debug_body_chars=args.debug_body,
    )


if __name__ == "__main__":
    main()

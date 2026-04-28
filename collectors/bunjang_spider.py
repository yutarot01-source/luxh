"""
번개장터 모바일 (https://m.bunjang.co.kr/search/products)

- Stealth: ``bunjang_auto_wait_fetch_kwargs`` → ``load_dom`` + ``network_idle`` +
  ``wait_selector`` (``a[href*='/products/']`` **visible**) + ``page_action`` 무한 스크롤.
- 기본 스크롤: **5회**, 라운드 간 **1000ms** (생성자 인자로 조절).
- 파싱: 상품 링크 ``a[href*='/products/']`` 중심, 부모 노드에서 가격·이미지 보강.
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ is None:
    import sys
    from pathlib import Path

    _ROOT = Path(__file__).resolve().parent.parent
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    __package__ = "collectors"

import json
import re

import httpx
from scrapling.engines.toolbelt.custom import Response

from .base_collector import BaseCollector, FetcherConfig
from .dynamic_wait import bunjang_auto_wait_fetch_kwargs
from .models import RawListing
from .text_utils import absolutize_url, extract_price_text, parse_price_krw, strip_html_to_description, utc_now_iso

_PRODUCT_HREF = re.compile(r"/products/(\d+)", re.I)


class BunjangSpider(BaseCollector):
    site_id = "bunjang"

    def __init__(
        self,
        *,
        stealth: bool = True,
        fetcher_cfg: FetcherConfig | None = None,
        scroll_rounds: int = 5,
        scroll_pause_ms: int = 1_000,
        use_auto_wait: bool = True,
    ) -> None:
        super().__init__(stealth=stealth, fetcher_cfg=fetcher_cfg)
        self._scroll_rounds = scroll_rounds
        self._scroll_pause_ms = scroll_pause_ms
        self._use_auto_wait = use_auto_wait

    @staticmethod
    def search_url(query: str) -> str:
        from urllib.parse import quote_plus

        return f"https://api.bunjang.co.kr/api/1/find_v2.json?q={quote_plus(query)}&order=date&n=30&page=0"

    def search(self, query: str, *, limit: int = 40) -> list[RawListing]:
        url = self.search_url(query)
        api_rows = self._search_api(url, limit=limit)
        if api_rows:
            return api_rows
        if self.stealth and self._use_auto_wait:
            aw = bunjang_auto_wait_fetch_kwargs(
                scroll_rounds=self._scroll_rounds,
                scroll_pause_ms=self._scroll_pause_ms,
            )
            resp = self.fetch(url, **aw)
        else:
            resp = self.fetch(
                url,
                wait_selector="a[href*='/products/']",
                wait_selector_state="visible",
                wait=1500,
            )
        return self.parse_search_response(resp, limit=limit)

    def _search_api(self, url: str, *, limit: int) -> list[RawListing]:
        try:
            with httpx.Client(timeout=12.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
                r = client.get(url)
                r.raise_for_status()
            payload = r.json()
        except Exception as exc:
            print(f"[bunjang] api error={exc}")
            return []
        return _rows_from_api_payload(payload, limit)

    def parse_search_response(self, resp: Response, *, limit: int = 40) -> list[RawListing]:
        api_rows = _parse_api_rows(resp, limit)
        if api_rows:
            return api_rows
        page_desc = self.response_description(resp)
        anchors = resp.css("a[href*='/products/']")
        seen: set[str] = set()
        rows: list[RawListing] = []
        for a in anchors:
            href = str(a.css("::attr(href)").get() or "").strip()
            m = _PRODUCT_HREF.search(href)
            if not m:
                continue
            pid = m.group(1)
            if pid in seen:
                continue
            seen.add(pid)
            listing_url = absolutize_url(resp.url, href)
            parent = getattr(a, "parent", None)
            card_scope = parent if parent is not None else a
            card_html = str(card_scope.get())
            title = _safe_anchor_text(a, card_html)[:400]
            price_text = extract_price_text(card_html) or extract_price_text(title)
            price_krw = parse_price_krw(price_text)
            img = str(a.css("img::attr(src)").get() or "").strip()
            if not img:
                img = str(card_scope.css("img::attr(src)").get() or "").strip()
            trade = _guess_trade_state(card_html + title)
            rows.append(
                RawListing(
                    source="bunjang",
                    model_name=title or f"product_{pid}",
                    price_krw=price_krw,
                    status_text=strip_html_to_description(card_html, max_chars=2000),
                    listing_url=listing_url,
                    image_url=absolutize_url(resp.url, img),
                    description_text=f"{title}\n\n--- card ---\n{strip_html_to_description(card_html)}\n\n--- page ---\n{page_desc}",
                    trade_state=trade,
                    price_text=price_text,
                    source_title=title,
                    fetched_at=utc_now_iso(),
                )
            )
            if len(rows) >= limit:
                break
        return rows

    def lowest_acceptable_price(self, query: str, *, limit: int = 25) -> tuple[int | None, RawListing | None]:
        items = [x for x in self.search(query, limit=limit) if _acceptable_for_market(x)]
        priced = [x for x in items if x.price_krw is not None]
        if not priced:
            return None, None
        best = min(priced, key=lambda z: z.price_krw or 0)
        return best.price_krw, best


def _guess_trade_state(blob: str) -> str | None:
    if "거래완료" in blob or "판매완료" in blob:
        return "거래완료"
    if "예약중" in blob or "예약" in blob:
        return "예약중"
    if "판매중" in blob or "판매 중" in blob:
        return "판매중"
    return None


def _safe_anchor_text(a: object, card_html: str) -> str:
    """
    Scrapling/Playwright 응답에서는 일부 노드가 직렬화 오류를 내는 경우가 있어
    XPath normalize-space에 의존하지 않고 안전한 텍스트를 추출한다.
    """
    try:
        # Scrapling css pseudo "::text"는 텍스트 노드 리스트를 준다.
        texts = getattr(a, "css")("::text").getall()  # type: ignore[operator]
        s = " ".join(str(x).strip() for x in texts if str(x).strip())
        if s:
            return s
    except Exception:
        pass
    try:
        s2 = str(getattr(a, "get")())
        if s2:
            return strip_html_to_description(s2, max_chars=400)
    except Exception:
        pass
    return strip_html_to_description(card_html, max_chars=400)


def _parse_api_rows(resp: Response, limit: int) -> list[RawListing]:
    text = str(resp.html_content)
    m = re.search(r"<p>([\s\S]*?)</p>", text, re.I)
    if m:
        text = m.group(1)
    try:
        payload = json.loads(text)
    except Exception:
        return []
    return _rows_from_api_payload(payload, limit)


def _rows_from_api_payload(payload: object, limit: int) -> list[RawListing]:
    items = payload.get("list") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    rows: list[RawListing] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("pid") or "").strip()
        title = str(item.get("name") or "").strip()
        if not pid or not title:
            continue
        raw_price = item.get("price")
        price_text = f"{raw_price}원" if raw_price not in (None, "") else ""
        price_krw = parse_price_krw(price_text)
        img = str(item.get("product_image") or "").replace("{res}", "400").strip()
        listing_url = f"https://m.bunjang.co.kr/products/{pid}"
        status = str(item.get("status") or "")
        trade_state = "판매중" if status == "0" else status or None
        rows.append(
            RawListing(
                source="bunjang",
                model_name=title[:400],
                price_krw=price_krw,
                status_text=str(item.get("location") or item.get("tag") or "")[:1000],
                listing_url=listing_url,
                image_url=img,
                description_text=json.dumps(item, ensure_ascii=False)[:4000],
                trade_state=trade_state,
                price_text=price_text,
                source_title=title[:400],
                fetched_at=utc_now_iso(),
            )
        )
        if len(rows) >= limit:
            break
    return rows


def _acceptable_for_market(item: RawListing) -> bool:
    s = f"{item.trade_state or ''} {item.status_text} {item.model_name}"
    if "예약중" in s or "예약 중" in s:
        return False
    if "거래완료" in s or "판매완료" in s or "판매중" in s or "판매 중" in s:
        return True
    return True


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="BunjangSpider standalone runner")
    ap.add_argument("query", nargs="?", default="샤넬", help="search query")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--stealth", action="store_true", help="use browser stealth fetch (requires patchright)")
    ap.add_argument("--scroll-rounds", type=int, default=5)
    ap.add_argument("--scroll-pause-ms", type=int, default=1000)
    args = ap.parse_args()

    sp = BunjangSpider(
        stealth=bool(args.stealth),
        use_auto_wait=bool(args.stealth),
        scroll_rounds=int(args.scroll_rounds),
        scroll_pause_ms=int(args.scroll_pause_ms),
    )
    rows = sp.search(args.query, limit=args.limit)
    print(f"[bunjang] query={args.query!r} rows={len(rows)}")
    for r in rows[: min(3, len(rows))]:
        print("-", r.model_name, r.price_krw, r.image_url, r.listing_url)

"""
필웨이 (https://www.feelway.com/search?q=…)

- ``feelway_auto_wait_fetch_kwargs``: ``load_dom`` + ``network_idle`` +
  필웨이 상품 ``a[href*='feelway.com']`` **visible** + ``page_action`` 무한 스크롤
  (기본 **5회 / 1000ms**, 조절 가능).
- 파싱: 스크롤 후 DOM에서 ``a[href*='feelway.com']`` 링크 단위로 모델명·가격·이미지.
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
from html import unescape

from scrapling.engines.toolbelt.custom import Response

from .base_collector import BaseCollector, FetcherConfig
from .dynamic_wait import feelway_auto_wait_fetch_kwargs
from .models import RawListing
from .text_utils import absolutize_url, extract_price_text, parse_price_krw, strip_html_to_description, utc_now_iso

_PRICE_CAND = re.compile(r"([\d,]{5,})\s*(?:원|$|\s)")


class FeelwaySpider(BaseCollector):
    site_id = "feelway"

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
    def search_url(query: str, *, page: int = 1) -> str:
        from urllib.parse import quote_plus

        page = max(1, int(page))
        suffix = f"&page={page}" if page > 1 else ""
        return f"https://www.feelway.com/search?q={quote_plus(query)}{suffix}"

    def search(self, query: str, *, limit: int = 30) -> list[RawListing]:
        return self.search_page(query, page=1, limit=limit)

    def search_page(self, query: str, *, page: int = 1, limit: int = 30) -> list[RawListing]:
        url = self.search_url(query, page=page)
        if self.stealth and self._use_auto_wait:
            aw = feelway_auto_wait_fetch_kwargs(
                scroll_rounds=self._scroll_rounds,
                scroll_pause_ms=self._scroll_pause_ms,
            )
            resp = self.fetch(url, **aw)
        else:
            resp = self.fetch(
                url,
                wait_selector="main, a[href*='feelway.com']",
                wait_selector_state="attached",
                wait=1600,
            )
        return self.parse_search_response(resp, limit=limit)

    def parse_search_response(self, resp: Response, *, limit: int = 30) -> list[RawListing]:
        props_rows = _parse_data_props_rows(resp, limit)
        if props_rows:
            return props_rows
        page_desc = self.response_description(resp)
        rows: list[RawListing] = []
        seen: set[str] = set()
        anchors = resp.css(
            "a[href*='feelway.com'][href*='goods'], "
            "a[href*='feelway.com'][href*='product'], "
            "a[href*='/goods/'], a[href*='/product/']"
        )
        for a in anchors:
            href = str(a.css("::attr(href)").get() or "").strip()
            if (
                not href
                or "/search" in href
                or "login" in href
                or "register" in href
                or "/event/" in href
                or "sloganVideo" in href
            ):
                continue
            if href in seen:
                continue
            seen.add(href)
            listing_url = absolutize_url(resp.url, href)
            scope = a.parent if getattr(a, "parent", None) is not None else a
            try:
                blob = str(scope.get())
            except Exception:
                blob = str(a.get())
            title = _safe_anchor_text(a, blob).strip()[:400]
            price_text = extract_price_text(blob) or extract_price_text(title)
            price_krw = parse_price_krw(price_text) or _best_price_from_snippet(blob)
            img = str(a.css("img::attr(src)").get() or "").strip()
            if not img:
                mimg = re.search(r"https://[^\s\"']+\.(?:jpg|jpeg|png|webp)", blob, re.I)
                img = mimg.group(0) if mimg else ""
            trade = _trade_from_text(title + blob)
            rows.append(
                RawListing(
                    source="feelway",
                    model_name=title[:300] or listing_url,
                    price_krw=price_krw,
                    status_text=strip_html_to_description(blob, max_chars=1500),
                    listing_url=listing_url,
                    image_url=absolutize_url(resp.url, img),
                    description_text=f"{title}\n\n--- card ---\n{strip_html_to_description(blob)}\n\n--- page ---\n{page_desc}",
                    trade_state=trade,
                    price_text=price_text,
                    source_title=title,
                    fetched_at=utc_now_iso(),
                )
            )
            if len(rows) >= limit:
                break
        if rows:
            return rows
        return _parse_fallback_blocks(resp, page_desc, limit)

    def lowest_acceptable_price(self, query: str, *, limit: int = 20) -> tuple[int | None, RawListing | None]:
        items = [x for x in self.search(query, limit=limit) if _acceptable(x)]
        priced = [x for x in items if x.price_krw]
        if not priced:
            return None, None
        best = min(priced, key=lambda z: z.price_krw or 0)
        return best.price_krw, best


def _acceptable(item: RawListing) -> bool:
    return "품절" not in f"{item.trade_state or ''} {item.model_name}"


def _trade_from_text(blob: str) -> str | None:
    if "거래완료" in blob or "판매완료" in blob:
        return "거래완료"
    if "판매중" in blob or "판매" in blob:
        return "판매중"
    return None


def _trade_from_item(item: dict) -> str | None:
    status_blob = " ".join(
        str(item.get(k) or "")
        for k in (
            "status",
            "trade_state",
            "state",
            "sale_state",
            "sale_status",
            "goods_status",
            "sold_out",
            "is_sold",
        )
    )
    trade = _trade_from_text(status_blob)
    if trade:
        return trade
    lowered = status_blob.lower()
    if any(k in lowered for k in ("sold", "soldout", "sold_out", "closed")):
        return "거래완료"
    if any(k in lowered for k in ("selling", "active", "open", "available")):
        return "판매중"
    return "판매중"


def _best_price_from_snippet(html: str) -> int | None:
    candidates: list[int] = []
    for m in _PRICE_CAND.finditer(html):
        n = int(m.group(1).replace(",", ""))
        if 10_000 <= n <= 500_000_000:
            candidates.append(n)
    return min(candidates) if candidates else None


def _parse_data_props_rows(resp: Response, limit: int) -> list[RawListing]:
    html = str(resp.html_content)
    items = None
    for m in re.finditer(r"data-props=(['\"])([\s\S]*?)\1", html, re.I):
        raw = unescape(m.group(2))
        if "searchResult" not in raw or "items" not in raw:
            continue
        try:
            props = json.loads(raw)
        except Exception:
            continue
        result = props.get("searchResult") if isinstance(props, dict) else None
        maybe_items = result.get("items") if isinstance(result, dict) else None
        if isinstance(maybe_items, list):
            items = maybe_items
            break
    if not isinstance(items, list):
        return []
    rows: list[RawListing] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        g_no = str(item.get("g_no") or "").strip()
        title = str(item.get("g_name") or "").strip()
        if not g_no or not title:
            continue
        price = item.get("special_price") or item.get("dp_basic_price") or item.get("g_price")
        try:
            price_krw = int(price)
        except (TypeError, ValueError):
            price_krw = parse_price_krw(f"{price}원")
        price_text = f"{price_krw}원" if price_krw is not None else ""
        photo = str(item.get("g_photo") or item.get("g_photo1") or "").strip()
        if photo and not photo.startswith("http"):
            photo = "https://cdn.feelway.com/" + photo.lstrip("/")
        brand = str(item.get("brand_name") or "").strip() or "item"
        listing_url = f"https://www.feelway.com/view_goods.php?g_no={g_no}"
        trade_state = _trade_from_item(item)
        rows.append(
            RawListing(
                source="feelway",
                model_name=title[:400],
                price_krw=price_krw,
                status_text=f"{trade_state or ''} {item.get('brand_name') or ''}".strip()[:1000],
                listing_url=listing_url,
                image_url=photo,
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


def _safe_anchor_text(a: object, blob_html: str) -> str:
    """Scrapling 노드 직렬화 오류를 피하는 안전 텍스트 추출."""
    try:
        texts = getattr(a, "css")("::text").getall()  # type: ignore[operator]
        s = " ".join(str(x).strip() for x in texts if str(x).strip())
        if s:
            return s
    except Exception:
        pass
    try:
        alt = getattr(a, "css")("img::attr(alt)").get()  # type: ignore[operator]
        if isinstance(alt, str) and alt.strip():
            return alt.strip()
    except Exception:
        pass
    return strip_html_to_description(blob_html, max_chars=400)


def _parse_fallback_blocks(resp: Response, page_desc: str, limit: int) -> list[RawListing]:
    """앵커 파싱 실패 시 블록 단위 휴리스틱."""
    rows: list[RawListing] = []
    for sel in ("li", "article", "div[class*='item']", "div[class*='product']"):
        for el in resp.css(sel):
            h = str(el.get())
            if len(h) < 80 or not re.search(_PRICE_CAND, h):
                continue
            m = re.search(r'href=["\']([^"\']+feelway[^"\']+)["\']', h, re.I)
            if not m:
                continue
            listing_url = absolutize_url(resp.url, m.group(1))
            title = strip_html_to_description(h, max_chars=400)
            rows.append(
                RawListing(
                    source="feelway",
                    model_name=title[:300] or listing_url,
                    price_krw=_best_price_from_snippet(h),
                    status_text=strip_html_to_description(h, max_chars=1500),
                    listing_url=listing_url,
                    image_url="",
                    description_text=f"{title}\n\n--- page ---\n{page_desc}",
                    trade_state=_trade_from_text(h),
                    price_text=extract_price_text(h),
                    source_title=title[:300],
                    fetched_at=utc_now_iso(),
                )
            )
            if len(rows) >= limit:
                return rows
    return rows


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="FeelwaySpider standalone runner")
    ap.add_argument("query", nargs="?", default="샤넬", help="search query")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--stealth", action="store_true", help="use browser stealth fetch (requires patchright)")
    ap.add_argument("--scroll-rounds", type=int, default=5)
    ap.add_argument("--scroll-pause-ms", type=int, default=1000)
    args = ap.parse_args()

    sp = FeelwaySpider(
        stealth=bool(args.stealth),
        use_auto_wait=bool(args.stealth),
        scroll_rounds=int(args.scroll_rounds),
        scroll_pause_ms=int(args.scroll_pause_ms),
    )
    rows = sp.search(args.query, limit=args.limit)
    print(f"[feelway] query={args.query!r} rows={len(rows)}")
    for r in rows[: min(3, len(rows))]:
        print("-", r.model_name, r.price_krw, r.image_url, r.listing_url)

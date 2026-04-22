"""
구구스 (https://www.gugus.co.kr / https://m.gugus.co.kr)

- ``gugus_auto_wait_fetch_kwargs``: ``load_dom`` + ``network_idle`` + 상품 앵커 **visible**.
- 모바일(``m.``) URL은 ``BaseCollector`` 가 모바일 UA를 자동 부착.
- 파싱: ``goodsView`` / ``goodsNo`` 링크와 카드(부모) 텍스트에서 모델명·가격.
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ is None:
    import sys
    from pathlib import Path

    _ROOT = Path(__file__).resolve().parent.parent
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    __package__ = "collectors"

import re
from urllib.parse import quote_plus

from scrapling.engines.toolbelt.custom import Response

from .base_collector import BaseCollector, FetcherConfig
from .dynamic_wait import gugus_auto_wait_fetch_kwargs
from .models import RawListing
from .text_utils import absolutize_url, parse_price_krw, strip_html_to_description

_GOODS_NO = re.compile(r"goodsNo[=](\d+)", re.I)
_GOODS_VIEW = re.compile(r"/goods/goodsView\.do", re.I)


class GugusSpider(BaseCollector):
    site_id = "gugus"

    def __init__(
        self,
        *,
        search_templates: tuple[str, ...] | None = None,
        stealth: bool = True,
        fetcher_cfg: FetcherConfig | None = None,
        use_auto_wait: bool = True,
    ) -> None:
        super().__init__(stealth=stealth, fetcher_cfg=fetcher_cfg)
        qph = "{q}"
        self._search_templates = search_templates or (
            f"https://m.gugus.co.kr/goods/goodsSearch.do?keyword={qph}",
            f"https://m.gugus.co.kr/goods/goodsSearch.do?searchText={qph}",
            f"https://www.gugus.co.kr/goods/goodsSearch.do?keyword={qph}",
            f"https://www.gugus.co.kr/goods/goodsSearch.do?searchText={qph}",
        )
        self._quote = quote_plus
        self._use_auto_wait = use_auto_wait

    def search_url_candidates(self, query: str) -> list[str]:
        enc = self._quote(query)
        return [t.replace("{q}", enc) for t in self._search_templates]

    def search(self, query: str, *, limit: int = 30) -> list[RawListing]:
        last: Response | None = None
        fetch_kw = gugus_auto_wait_fetch_kwargs() if (self.stealth and self._use_auto_wait) else {}
        for url in self.search_url_candidates(query):
            try:
                if fetch_kw:
                    resp = self.fetch(url, **fetch_kw)
                else:
                    resp = self.fetch(
                        url,
                        wait_selector="a[href*='goodsView'], a[href*='goodsNo']",
                        wait_selector_state="attached",
                        wait=1500,
                    )
            except Exception:
                continue
            if resp.status >= 400:
                continue
            last = resp
            rows = self.parse_search_response(resp, limit=limit)
            if rows:
                return rows
        if last is not None:
            return self.parse_search_response(last, limit=limit)
        return []

    def parse_search_response(self, resp: Response, *, limit: int = 30) -> list[RawListing]:
        page_desc = self.response_description(resp)
        anchors = resp.css(
            "a[href*='goodsView'], a[href*='goodsNo'], a[href*='/goods/goodsView']"
        )
        seen: set[str] = set()
        out: list[RawListing] = []
        for a in anchors:
            href = str(a.css("::attr(href)").get() or "").strip()
            if not href or not (_GOODS_VIEW.search(href) or "goodsNo" in href.lower()):
                continue
            m = _GOODS_NO.search(href)
            key = m.group(1) if m else href
            if key in seen:
                continue
            seen.add(key)
            listing_url = absolutize_url(resp.url, href)
            scope = a.parent if getattr(a, "parent", None) is not None else a
            try:
                blob = str(scope.get())
            except Exception:
                blob = str(a.get())
            # Playwright DOM 직렬화 이슈 회피
            try:
                texts = a.css("::text").getall()
                title = " ".join(str(x).strip() for x in texts if str(x).strip())[:400]
            except Exception:
                title = ""
            if len(title) < 2:
                title = strip_html_to_description(blob, max_chars=400)
            price_krw = _extract_gugus_price(title, blob)
            img = str(a.css("img::attr(src)").get() or "").strip()
            if not img:
                img = str(scope.css("img::attr(src)").get() or "").strip()
            out.append(
                RawListing(
                    source="gugus",
                    model_name=title or listing_url,
                    price_krw=price_krw,
                    status_text=strip_html_to_description(blob, max_chars=2000),
                    listing_url=listing_url,
                    image_url=absolutize_url(resp.url, img),
                    description_text=f"{title}\n\n--- card ---\n{strip_html_to_description(blob)}\n\n--- page ---\n{page_desc}",
                    trade_state=None,
                )
            )
            if len(out) >= limit:
                break
        return out

    def lowest_acceptable_price(self, query: str, *, limit: int = 20) -> tuple[int | None, RawListing | None]:
        items = [x for x in self.search(query, limit=limit) if x.price_krw]
        if not items:
            return None, None
        best = min(items, key=lambda z: z.price_krw or 0)
        return best.price_krw, best


def _extract_gugus_price(title: str, blob: str) -> int | None:
    for segment in (title, blob):
        p = parse_price_krw(segment)
        if p is not None:
            return p
    m = re.search(r"([\d,]{4,})\s*원", blob, re.I)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="GugusSpider standalone runner")
    ap.add_argument("query", nargs="?", default="샤넬", help="search query")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--stealth", action="store_true", help="use browser stealth fetch (requires patchright)")
    args = ap.parse_args()

    sp = GugusSpider(stealth=bool(args.stealth), use_auto_wait=bool(args.stealth))
    rows = sp.search(args.query, limit=args.limit)
    print(f"[gugus] query={args.query!r} rows={len(rows)}")
    for r in rows[: min(3, len(rows))]:
        print("-", r.model_name, r.price_krw, r.image_url, r.listing_url)

"""
당근마켓 중고거래 검색 (https://www.daangn.com/kr/)

파싱
----
1. ``__NEXT_DATA__`` 내 ``fleamarketArticles`` 가 있으면 우선 사용.
2. 없으면 ``article.flea-market-article`` 카드 단위로 고정 파싱:

   - 제목: ``h3``, ``img`` 의 ``alt``, 첫 ``a`` 텍스트 순
   - 가격: ``p.article-price``
   - 이미지: ``img::attr(src)``
   - 상세: ``a[href*='/buy-sell/']`` (없으면 첫 ``a``)

Stealth: ``daangn_auto_wait_fetch_kwargs`` → ``load_dom`` + ``network_idle`` + ``wait_selector``.

지역: 기본은 검색 URL에서 ``in`` 을 넣지 않아(웹 기준) 특정 동으로 고정하지 않습니다.
로컬만 보고 싶을 때는 ``LUXEFINDER_DAANGN_REGION`` 또는 ``DaangnSpider(region_in=...)``.
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ is None:
    import sys
    from pathlib import Path

    _ROOT = Path(__file__).resolve().parent.parent
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    __package__ = "collectors"

import os
import re
from typing import Any
from urllib.parse import urlencode

from scrapling.engines.toolbelt.custom import Response

from .base_collector import BaseCollector, FetcherConfig
from .dynamic_wait import daangn_auto_wait_fetch_kwargs
from .models import RawListing
from .text_utils import absolutize_url, parse_next_json_fleamarkets, parse_price_krw

_BUY_SELL_HREF = re.compile(r"/buy-sell/(\d+)", re.I)


class DaangnSpider(BaseCollector):
    site_id = "daangn"

    def __init__(
        self,
        *,
        region_in: str | None = None,
        stealth: bool = True,
        fetcher_cfg: FetcherConfig | None = None,
        use_auto_wait: bool = True,
    ) -> None:
        super().__init__(stealth=stealth, fetcher_cfg=fetcher_cfg)
        # ``in`` 생략 시 웹 검색은 지역 고정 없이(전국 후보) 동작하는 경우가 많음.
        # 특정 동만 보고 싶으면 ``region_in=...`` 또는 환경변수 ``LUXEFINDER_DAANGN_REGION``.
        if region_in is not None:
            self.region_in = region_in.strip()
        else:
            self.region_in = (os.environ.get("LUXEFINDER_DAANGN_REGION") or "").strip()
        self._use_auto_wait = use_auto_wait

    def search_url(self, query: str, *, only_on_sale: bool = True) -> str:
        base = "https://www.daangn.com/kr/buy-sell/"
        params: dict[str, str] = {"q": query, "only_on_sale": str(only_on_sale).lower()}
        if self.region_in:
            params["in"] = self.region_in
        return f"{base}?{urlencode(params)}"

    def search(self, query: str, *, only_on_sale: bool = True, limit: int = 40) -> list[RawListing]:
        url = self.search_url(query, only_on_sale=only_on_sale)
        if self.stealth and self._use_auto_wait:
            resp = self.fetch(url, **daangn_auto_wait_fetch_kwargs())
        else:
            resp = self.fetch(
                url,
                wait_selector="article.flea-market-article, script#__NEXT_DATA__",
                wait_selector_state="attached",
                wait=1200,
            )
        return self.parse_search_response(resp, limit=limit)

    def parse_search_response(self, resp: Response, *, limit: int = 40) -> list[RawListing]:
        html = str(resp.html_content)
        desc = self.response_description(resp)
        articles = parse_next_json_fleamarkets(html)
        if articles:
            return self._from_next_json(resp.url, articles, desc, limit)
        # 레거시(.flea-market-article) → 신형(앵커 기반) 순으로 시도
        legacy = self._from_flea_market_articles(resp, desc, limit)
        if legacy:
            return legacy
        return self._from_buy_sell_anchors(resp, desc, limit)

    def _from_next_json(
        self,
        page_url: str,
        articles: list[dict[str, Any]],
        page_desc: str,
        limit: int,
    ) -> list[RawListing]:
        out: list[RawListing] = []
        for row in articles[:limit]:
            # Next.js JSON 필드는 자주 바뀐다. 'thumbnail' 같은 잘못된 값이 title 로 들어오는 경우가 있어
            # 후보를 여러 개 두고, 의미 없는 값은 버린다.
            title_candidates: list[str] = []
            for k in (
                "title",
                "name",
                "subject",
                "articleTitle",
                "productName",
                "displayTitle",
            ):
                v = row.get(k)
                if isinstance(v, str) and v.strip():
                    title_candidates.append(v.strip())
            title = ""
            for cand in title_candidates:
                c = cand.strip()
                if not c:
                    continue
                if c.lower() in ("thumbnail", "image", "thumbnailurl"):
                    continue
                title = c
                break
            title = (title or "").strip()
            price = row.get("price")
            if isinstance(price, str):
                price_krw = parse_price_krw(price)
            elif isinstance(price, (int, float)):
                price_krw = int(price)
            else:
                price_krw = None
            href = row.get("href") or row.get("url") or ""
            listing_url = absolutize_url(page_url, href)
            img = ""
            for k in ("thumbnail", "image", "thumbnailUrl"):
                v = row.get(k)
                if isinstance(v, str):
                    img = v
                    break
            status = (row.get("content") or row.get("status") or "") or ""
            if isinstance(status, dict):
                status = str(status)
            trade = None
            for k in ("status", "badge", "saleStatus", "tradeStatus"):
                v = row.get(k)
                if isinstance(v, str):
                    trade = v
                    break
            # 브랜드 매칭/모델명 추정은 "매물 자체 텍스트"에서만 해야 한다.
            # page_desc(검색 페이지 전체 HTML 요약/URL 포함)를 섞으면 q=브랜드 키워드 때문에 오탐이 난다.
            row_desc = " ".join(x for x in (title, str(status), str(price)) if x)[:20_000]
            out.append(
                RawListing(
                    source="daangn",
                    model_name=title or "(제목 없음)",
                    price_krw=price_krw,
                    status_text=str(status)[:500] if status else "",
                    listing_url=listing_url or page_url,
                    image_url=absolutize_url(page_url, img) if img else "",
                    description_text=row_desc,
                    trade_state=trade,
                    raw_html_excerpt=page_desc[:12_000] if page_desc else None,
                )
            )
        return out

    def _from_flea_market_articles(self, resp: Response, page_desc: str, limit: int) -> list[RawListing]:
        """``.flea-market-article`` 고정 셀렉터 파싱."""
        out: list[RawListing] = []
        cards = resp.css("article.flea-market-article")
        for art in cards[:limit]:
            href = str(art.css("a[href*='/buy-sell/']::attr(href)").get() or "").strip()
            if not href:
                href = str(art.css("a::attr(href)").get() or "").strip()
            title = str(art.css("h3::text").get() or "").strip()
            if len(title) < 2:
                title = str(art.css("img::attr(alt)").get() or "").strip()
            if title.strip().lower() in ("thumbnail", "image", "thumbnailurl"):
                title = ""
            if len(title) < 2:
                title = str(art.xpath("normalize-space(.//a[1])").get() or "").strip()
            title = title[:400]
            price_krw = parse_price_krw(str(art.css("p.article-price::text").get() or ""))
            if price_krw is None:
                price_krw = parse_price_krw(str(art.get()))
            img = str(art.css("img::attr(src)").get() or "").strip()
            region = str(art.css("p.article-region-name::text").get() or "").strip()
            if not region:
                region = str(art.css(".article-region-name::text").get() or "").strip()
            listing_url = absolutize_url(resp.url, href)
            excerpt = str(art.get())[:12_000]
            out.append(
                RawListing(
                    source="daangn",
                    model_name=title or listing_url,
                    price_krw=price_krw,
                    status_text=region,
                    listing_url=listing_url or resp.url,
                    image_url=absolutize_url(resp.url, img),
                    description_text=f"{title} {region}".strip(),
                    trade_state=None,
                    raw_html_excerpt=(excerpt + ("\n\n--- page ---\n" + page_desc[:8_000] if page_desc else ""))[:12_000],
                )
            )
        return out

    def _from_buy_sell_anchors(self, resp: Response, page_desc: str, limit: int) -> list[RawListing]:
        """
        2026-04 기준 당근 검색 페이지는 JS 렌더링이 많아
        카드 전용 클래스가 고정되지 않을 수 있다. 상세 링크 앵커를 기준으로 파싱한다.
        """
        out: list[RawListing] = []
        seen: set[str] = set()
        anchors = resp.css("a[href*='/buy-sell/']")
        for a in anchors:
            href = str(a.css("::attr(href)").get() or "").strip()
            m = _BUY_SELL_HREF.search(href)
            if not m:
                continue
            key = m.group(1)
            if key in seen:
                continue
            seen.add(key)

            listing_url = absolutize_url(resp.url, href)
            scope = a.parent if getattr(a, "parent", None) is not None else a
            try:
                blob = str(scope.get())
            except Exception:
                blob = str(a.get())

            title = str(a.css("img::attr(alt)").get() or "").strip()
            if title.strip().lower() in ("thumbnail", "image", "thumbnailurl"):
                title = ""
            if len(title) < 2:
                try:
                    texts = a.css("::text").getall()
                    title = " ".join(str(x).strip() for x in texts if str(x).strip())
                except Exception:
                    title = ""
            title = (title or "").strip()[:400] or listing_url

            price_krw = parse_price_krw(title) or parse_price_krw(blob)
            img = str(a.css("img::attr(src)").get() or "").strip()
            if not img:
                img = str(scope.css("img::attr(src)").get() or "").strip()

            out.append(
                RawListing(
                    source="daangn",
                    model_name=title,
                    price_krw=price_krw,
                    status_text="",
                    listing_url=listing_url or resp.url,
                    image_url=absolutize_url(resp.url, img) if img else "",
                    description_text=title,
                    trade_state=None,
                    raw_html_excerpt=(blob[:8_000] + ("\n\n--- page ---\n" + page_desc[:8_000] if page_desc else ""))[:12_000],
                )
            )
            if len(out) >= limit:
                break
        return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="DaangnSpider standalone runner")
    ap.add_argument("query", nargs="?", default="샤넬", help="search query")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--stealth", action="store_true", help="use browser stealth fetch (requires patchright)")
    ap.add_argument(
        "--region",
        default="",
        metavar="IN",
        help="당근 ``in`` 지역 슬러그(예: 서울특별시-강남구-역삼동). 비우면 전국 검색(URL에서 in 생략)",
    )
    args = ap.parse_args()

    region_kw: str | None = (args.region.strip() or None) if args.region else None
    sp = DaangnSpider(region_in=region_kw, stealth=bool(args.stealth), use_auto_wait=bool(args.stealth))
    rows = sp.search(args.query, limit=args.limit)
    print(f"[daangn] query={args.query!r} rows={len(rows)}")
    for r in rows[: min(3, len(rows))]:
        print("-", r.model_name, r.price_krw, r.image_url, r.listing_url)

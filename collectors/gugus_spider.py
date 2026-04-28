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

import json
import re
from urllib.parse import quote_plus

import httpx
from scrapling.engines.toolbelt.custom import Response

from .base_collector import BaseCollector, FetcherConfig
from .dynamic_wait import gugus_auto_wait_fetch_kwargs
from .models import RawListing
from .text_utils import absolutize_url, extract_price_text, parse_price_krw, strip_html_to_description, utc_now_iso

_GOODS_NO = re.compile(r"goodsNo[=](\d+)", re.I)
_GOODS_VIEW = re.compile(r"/goods/goodsView\.do", re.I)
_BRAND_NO_BY_KEYWORD = {
    "샤넬": 16,
    "chanel": 16,
    "루이비통": 90,
    "louis": 90,
    "vuitton": 90,
    "구찌": 53,
    "gucci": 53,
}


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
            f"https://m.gugus.co.kr/search/result-view?searchTerm={qph}&inputSearchTermYn=N",
            f"https://www.gugus.co.kr/search/result-view?searchTerm={qph}&inputSearchTermYn=N",
        )
        self._quote = quote_plus
        self._use_auto_wait = use_auto_wait

    def search_url_candidates(self, query: str) -> list[str]:
        enc = self._quote(query)
        return [t.replace("{q}", enc) for t in self._search_templates]

    def search(self, query: str, *, limit: int = 30) -> list[RawListing]:
        ajax_rows = self._search_ajax(query, limit=limit)
        if ajax_rows:
            return self._enrich_detail_pages(ajax_rows, query=query, limit=limit)
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
                return self._enrich_detail_pages(rows, query=query, limit=limit)
        if last is not None:
            return self._enrich_detail_pages(self.parse_search_response(last, limit=limit), query=query, limit=limit)
        return []

    def _enrich_detail_pages(self, rows: list[RawListing], *, query: str, limit: int) -> list[RawListing]:
        if not rows:
            return rows
        out: list[RawListing] = []
        max_details = max(1, min(int(limit), len(rows), 20))
        for idx, row in enumerate(rows):
            if idx >= max_details:
                out.append(row)
                continue
            try:
                resp = self.fetch(row.listing_url, wait_selector="body", wait_selector_state="attached", wait=700)
                detail = self.response_description(resp)
                if detail:
                    row.description_text = f"{row.description_text}\n\n--- detail ---\n{detail[:4000]}"
                    row.status_text = f"{row.status_text}\n{detail[:1500]}".strip()
                title = _detail_title(resp)
                if title and len(title) > len(row.source_title or ""):
                    row.source_title = title[:400]
                    row.model_name = title[:400]
                price_text = extract_price_text(str(resp.html_content)) or row.price_text
                price_krw = parse_price_krw(price_text)
                if price_krw is not None:
                    row.price_text = price_text
                    row.price_krw = price_krw
            except Exception as exc:
                print(f"[gugus] detail enrich error query={query} url={row.listing_url} error={exc}")
            out.append(row)
        return out

    def _search_ajax(self, query: str, *, limit: int) -> list[RawListing]:
        brand_no = _brand_no_from_query(query)
        referer = self.search_url_candidates(query)[0]
        if brand_no is None:
            try:
                resp = self.fetch(referer, wait_selector="body", wait_selector_state="attached", wait=800)
                brand_no = _brand_no_from_html(str(resp.html_content))
            except Exception:
                brand_no = None
        if brand_no is None:
            return []
        body = {
            "perPage": max(20, min(max(int(limit) * 8, 60), 100)),
            "page": 1,
            "searchTerm": query,
            "inputSearchTerm": query,
            "inputSearchTermYn": "Y",
            "uperCategoryList": [],
            "categoryList": [],
            "brandList": [brand_no],
            "modelList": [],
            "gradeList": [],
            "propertyList": [],
            "shopList": [],
            "excludeTradingYn": "N",
            "purcvPsbYn": "N",
            "sortOrder": "",
        }
        try:
            with httpx.Client(timeout=15.0, headers={"User-Agent": "Mozilla/5.0", "Referer": referer}) as client:
                r = client.post("https://m.gugus.co.kr/goodsList/selectListGoodsBase", json=body)
                r.raise_for_status()
        except Exception as exc:
            print(f"[gugus] ajax error={exc}")
            return []
        return _parse_ajax_products(r.text, limit=limit, query=query)

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
            price_text = extract_price_text(blob) or extract_price_text(title)
            price_krw = parse_price_krw(price_text) or _extract_gugus_price(title, blob)
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
                    price_text=price_text,
                    source_title=title,
                    fetched_at=utc_now_iso(),
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


def _detail_title(resp: Response) -> str:
    for sel in ("h1::text", "h2::text", "title::text", "meta[property='og:title']::attr(content)"):
        try:
            value = str(resp.css(sel).get() or "").strip()
        except Exception:
            value = ""
        if value:
            return re.sub(r"\s+", " ", value)
    return ""


def _brand_no_from_query(query: str) -> int | None:
    q = (query or "").lower()
    for key, brand_no in _BRAND_NO_BY_KEYWORD.items():
        if key.lower() in q:
            return brand_no
    return None


def _brand_no_from_html(html: str) -> int | None:
    m = re.search(r'"brndNo"\s*:\s*(\d+)', html)
    if m:
        return int(m.group(1))
    m = re.search(r"fixBrndNo\s*=\s*(\d+)", html)
    if m:
        return int(m.group(1))
    return None


_QUERY_TERM_ALIASES = {
    "알마": ("알마", "alma"),
    "블랙": ("블랙", "black", "noir", "느와르", "누아르", "노아르"),
    "에피": ("에피", "에삐", "epi"),
    "모노그램": ("모노그램", "monogram"),
    "브라운": ("브라운", "brown", "marron"),
    "캐비어": ("캐비어", "caviar"),
    "램스킨": ("램스킨", "lambskin"),
    "은장": ("은장", "실버", "silver", "shw"),
    "금장": ("금장", "골드", "gold", "ghw"),
    "bb": ("bb",),
    "mm": ("mm",),
    "pm": ("pm",),
    "gm": ("gm",),
}


def _query_terms(query: str) -> list[str]:
    ignored = {"샤넬", "chanel", "루이비통", "louis", "vuitton", "구찌", "gucci", "가방", "핸드백"}
    terms = [t.strip().lower() for t in re.split(r"\s+", query or "") if t.strip()]
    return [t for t in terms if t not in ignored and len(t) >= 2]


def _query_groups(query: str) -> list[tuple[str, ...]]:
    groups: list[tuple[str, ...]] = []
    for term in _query_terms(query):
        groups.append(_QUERY_TERM_ALIASES.get(term, (term,)))
    return groups


def _has_group(text: str, group: tuple[str, ...]) -> bool:
    compact = text.replace(" ", "")
    for alias in group:
        a = alias.lower().strip()
        if not a:
            continue
        if re.fullmatch(r"[a-z0-9]{1,3}", a):
            if re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", text):
                return True
            continue
        if a in text or a.replace(" ", "") in compact:
            return True
    return False


def _parse_ajax_products(html: str, *, limit: int, query: str = "") -> list[RawListing]:
    m = re.search(r"var\s+products\s*=\s*(\[[\s\S]*?\]);", html)
    if not m:
        return []
    try:
        items = json.loads(m.group(1))
    except Exception:
        return []
    rows: list[RawListing] = []
    groups = _query_groups(query)
    wants_bag = any(k in (query or "") for k in ("가방", "핸드백", "백"))
    for item in items:
        if not isinstance(item, dict):
            continue
        gds_no = str(item.get("gdsNo") or "").strip()
        title = str(item.get("gdsNm") or "").strip()
        if not gds_no or not title:
            continue
        category_text = " ".join(
            str(item.get(k) or "")
            for k in ("oprtCtgrNm1", "oprtCtgrNm2", "oprtCtgrNm3", "mdlKorNm", "mdlEngNm")
        )
        bag_blob = f"{title} {category_text}"
        bag_words = ("가방", "핸드백", "숄더백", "크로스백", "토트백", "버킷백", "보이백", "플랩백", "체인백", "미니백", "bag", "handbag")
        if wants_bag and not any(k in bag_blob.lower() for k in bag_words):
            continue
        searchable = f"{title} {category_text} {item.get('gdsTag') or ''}".lower()
        # Do not enforce every query token at list level: Gugus often omits
        # color/material on list cards and only exposes it on the detail page.
        if groups and not any(_has_group(searchable, group) for group in groups):
            continue
        price = item.get("dcSalePrc") or item.get("prstSalePrc")
        try:
            price_krw = int(price)
        except (TypeError, ValueError):
            price_krw = parse_price_krw(f"{price}원")
        price_text = f"{price_krw}원" if price_krw is not None else ""
        img = str(item.get("gdsImgUrl") or "").strip()
        if img and not img.startswith("http"):
            img = "https://image.gugus.co.kr" + img
        listing_url = f"https://m.gugus.co.kr/goods/viewGoods?goodsNo={gds_no}"
        rows.append(
            RawListing(
                source="gugus",
                model_name=title[:400],
                price_krw=price_krw,
                status_text=str(item.get("saleStatNm") or item.get("saleMgmtStatNm") or "")[:1000],
                listing_url=listing_url,
                image_url=img,
                description_text=json.dumps(item, ensure_ascii=False)[:4000],
                trade_state=str(item.get("saleStatNm") or "") or None,
                price_text=price_text,
                source_title=title[:400],
                fetched_at=utc_now_iso(),
            )
        )
        if len(rows) >= limit:
            break
    return rows


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

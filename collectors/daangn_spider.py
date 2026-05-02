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
import hashlib
import json
from html import unescape
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

from scrapling.engines.toolbelt.custom import Response

from .base_collector import BaseCollector, FetcherConfig
from .dynamic_wait import daangn_auto_wait_fetch_kwargs
from .models import RawListing
from .text_utils import absolutize_url, extract_price_text, parse_price_krw, utc_now_iso

_DAANGN_BASE = "https://www.daangn.com"
_DETAIL_PATH_RE = re.compile(r"^/kr/buy-sell/(.+)-([a-z0-9]{8,})/?$", re.I)
_BUY_SELL_HREF = re.compile(r"/kr/buy-sell/([^/?#]+)", re.I)
_ARTICLE_HREF = re.compile(r"/articles/(\d+)", re.I)
_BAG_KEYWORDS = (
    "가방",
    "백",
    "핸드백",
    "숄더백",
    "토트백",
    "크로스백",
    "클러치",
    "백팩",
    "bag",
    "handbag",
    "shoulder",
    "tote",
    "crossbody",
)
_BRAND_KEYWORDS = {
    "샤넬": ("샤넬", "chanel"),
    "루이비통": ("루이비통", "루이 비통", "루이뷔통", "lv", "louis vuitton", "vuitton"),
    "구찌": ("구찌", "gucci"),
}
_NATIONWIDE_NOTICE_PRINTED = False


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _query_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        query = (params.get("search") or params.get("q") or [""])[0]
        if query:
            return query
        m = re.match(r"^/search/([^/?#]+)", parsed.path)
        return unquote(m.group(1)) if m else ""
    except Exception:
        return ""


def _debug_html_enabled() -> bool:
    return _env_bool("LUXEFINDER_DEBUG_HTML", default=False)


def _debug_daangn_enabled() -> bool:
    return _env_bool("LUXEFINDER_DEBUG_DAANGN", default=False)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _normalize_trade_state(value: object) -> str | None:
    text = _clean_text(str(value or ""))
    lower = text.lower()
    if lower in ("closed", "sold", "sold_out", "sold out") or "판매완료" in text or "거래완료" in text:
        return "거래완료"
    if lower in ("ongoing", "selling", "sale", "on_sale") or "판매중" in text:
        return "판매중"
    if text:
        return text
    return None


def _norm_text(text: str) -> str:
    return _clean_text(text).lower()


def _query_brand(query: str) -> str:
    q = _norm_text(query)
    for brand, aliases in _BRAND_KEYWORDS.items():
        if any(alias.lower() in q for alias in aliases):
            return brand
    return ""


def _has_brand_keyword(text: str, query: str) -> bool:
    brand = _query_brand(query)
    if not brand:
        return True
    t = _norm_text(text)
    return any(alias.lower() in t for alias in _BRAND_KEYWORDS[brand])


def _has_bag_keyword(text: str) -> bool:
    t = _norm_text(text)
    return any(keyword.lower() in t for keyword in _BAG_KEYWORDS)


def _print_nationwide_notice() -> None:
    global _NATIONWIDE_NOTICE_PRINTED
    if not _debug_daangn_enabled():
        return
    if _NATIONWIDE_NOTICE_PRINTED:
        return
    _NATIONWIDE_NOTICE_PRINTED = True
    print(
        "[daangn] nationwide search URL uses no region/location parameter; "
        "if results still look local, Daangn web is applying location context outside our query params."
    )


def _is_listing_href(href: str) -> bool:
    return _detail_match(href) is not None or _article_match(href) is not None


def _absolute_detail_url(href: str) -> str:
    h = (href or "").strip()
    if h.startswith("https://www.daangn.com"):
        return h.split("?", 1)[0].split("#", 1)[0]
    if h.startswith("//www.daangn.com"):
        return ("https:" + h).split("?", 1)[0].split("#", 1)[0]
    if h.startswith("/"):
        return (_DAANGN_BASE + h).split("?", 1)[0].split("#", 1)[0]
    if h.startswith("http"):
        return h.split("?", 1)[0].split("#", 1)[0]
    return (_DAANGN_BASE + "/" + h.lstrip("/")).split("?", 1)[0].split("#", 1)[0]


def _detail_match(href_or_url: str) -> re.Match[str] | None:
    url = _absolute_detail_url(href_or_url)
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.netloc and parsed.netloc != "www.daangn.com":
        return None
    path = parsed.path
    return _DETAIL_PATH_RE.match(path)


def _article_match(href_or_url: str) -> re.Match[str] | None:
    url = _absolute_detail_url(href_or_url)
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.netloc and parsed.netloc != "www.daangn.com":
        return None
    return _ARTICLE_HREF.match(parsed.path)


def _detail_reject_reason(href: str) -> str:
    h = (href or "").strip()
    if not h:
        return "empty_href"
    url = _absolute_detail_url(h)
    try:
        parsed = urlparse(url)
    except Exception:
        return "invalid_url"
    if parsed.netloc and parsed.netloc != "www.daangn.com":
        return "external_host"
    path = parsed.path or ""
    if path in ("/kr/buy-sell", "/kr/buy-sell/") or parsed.query:
        return "search_page"
    if "/kr/buy-sell/" not in path:
        if _ARTICLE_HREF.match(path):
            return "unknown"
        return "not_buy_sell_detail"
    if not _DETAIL_PATH_RE.match(path):
        return "detail_pattern_mismatch"
    return "unknown"


def _detail_id(url: str) -> str:
    m = _detail_match(url)
    if not m:
        am = _article_match(url)
        return am.group(1) if am else _item_debug_id(url)
    return m.group(2) if m else _item_debug_id(url)


def _title_from_detail_url(url: str) -> str:
    m = _detail_match(url)
    if not m:
        return ""
    slug = unquote(m.group(1))
    return _clean_text(slug.replace("-", " "))


def _decoded_detail_slug(url: str) -> str:
    m = _detail_match(url)
    return unquote(m.group(1)) if m else ""


def _html_title(html: str) -> str:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    return _clean_text(title_match.group(1)) if title_match else ""


def _query_terms(query: str) -> list[str]:
    return [part for part in re.split(r"\s+", _norm_text(query)) if part]


def _text_matches_query(text: str, query: str) -> bool:
    terms = _query_terms(query)
    if not terms:
        return True
    haystack = _norm_text(text)
    return all(term in haystack for term in terms)


def _debug_detail_candidate(href: str) -> None:
    if _debug_daangn_enabled():
        print(f"[daangn] detail href candidate={href}")


def _debug_detail_rejected(href: str, reason: str) -> None:
    if _debug_daangn_enabled():
        print(f"[daangn] rejected href reason={reason} href={href}")


def _debug_detail_accepted(url: str) -> None:
    if _debug_daangn_enabled():
        print(f"[daangn] accepted detail url={url}")


def _item_debug_id(url: str) -> str:
    return hashlib.sha256((url or "").encode("utf-8")).hexdigest()[:12]


def _is_valid_listing_item(title: str, price_krw: int | None, url: str, *, query: str = "", description: str = "") -> bool:
    t = _clean_text(title)
    blob = f"{title} {description}"
    if not _is_listing_href(url):
        return False
    if not t or len(t) < 2:
        return False
    if t.lower() in ("thumbnail", "image", "thumbnailurl"):
        return False
    if any(x in t for x in ("로그인", "회원가입", "채팅하기", "중고거래", "동네", "카테고리")):
        return False
    if not isinstance(price_krw, int) or price_krw <= 0:
        return False
    if query and not _has_brand_keyword(blob, query):
        return False
    if query and not _has_bag_keyword(blob):
        return False
    return True


def _listing_reject_reason(
    title: str,
    price_krw: int | None,
    url: str,
    *,
    query: str = "",
    description: str = "",
) -> tuple[str, bool, bool]:
    t = _clean_text(title)
    blob = f"{title} {description}"
    brand_match = _has_brand_keyword(blob, query) if query else True
    bag_match = _has_bag_keyword(blob) if query else True
    if not _is_listing_href(url):
        return _detail_reject_reason(url), brand_match, bag_match
    if not t or len(t) < 2:
        return "empty_or_short_title", brand_match, bag_match
    if t.lower() in ("thumbnail", "image", "thumbnailurl"):
        return "generic_image_title", brand_match, bag_match
    if any(x in t for x in ("로그인", "회원가입", "채팅하기", "중고거래", "동네", "카테고리")):
        return "navigation_or_chrome_text", brand_match, bag_match
    if not isinstance(price_krw, int) or price_krw <= 0:
        return "missing_or_invalid_price", brand_match, bag_match
    if query and not brand_match:
        return "brand_mismatch", brand_match, bag_match
    if query and not bag_match:
        return "bag_keyword_mismatch", brand_match, bag_match
    return "", brand_match, bag_match


def _log_parsed_items(query: str, rows: list[RawListing]) -> None:
    if not _debug_daangn_enabled():
        return
    for row in rows[:5]:
        print(
            "[daangn] item "
            f"query={query} id={_detail_id(row.listing_url)} "
            f"title={_clean_text(row.model_name)[:80]} "
            f"price={row.price_krw} location={_clean_text(row.status_text)[:60]} "
            f"url={row.listing_url}"
        )


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
        self.region_in = ""
        _print_nationwide_notice()
        self._use_auto_wait = use_auto_wait
        self._filtered_irrelevant = 0

    def search_url(self, query: str, *, only_on_sale: bool = True) -> str:
        base = "https://www.daangn.com/kr/buy-sell/"
        params: dict[str, str] = {"search": query, "only_on_sale": str(only_on_sale).lower()}
        return f"{base}?{urlencode(params)}"

    def search_urls(self, query: str, *, only_on_sale: bool = True) -> list[str]:
        # 전국 검색 고정: 지역을 의미하는 ``in``/location 파라미터를 절대 붙이지 않는다.
        # ``/search/{query}`` 경로는 브라우저/계정 위치 컨텍스트를 탈 수 있어 사용하지 않는다.
        return [self.search_url(query, only_on_sale=only_on_sale)]

    def search(self, query: str, *, only_on_sale: bool = True, limit: int = 40) -> list[RawListing]:
        last_rows: list[RawListing] = []
        for url in self.search_urls(query, only_on_sale=only_on_sale):
            rows: list[RawListing] = []
            try:
                original_stealth = self.stealth
                if original_stealth:
                    self.stealth = False
                if self.stealth and self._use_auto_wait:
                    resp = self.fetch(url, **daangn_auto_wait_fetch_kwargs())
                else:
                    resp = self.fetch(
                        url,
                        wait_selector="article.flea-market-article, script#__NEXT_DATA__",
                        wait_selector_state="attached",
                        wait=1200,
                    )
                rows = self.parse_search_response(resp, limit=limit)
            except Exception as exc:
                print(f"[daangn] http error={exc!r} query={query}")
            finally:
                if "original_stealth" in locals():
                    self.stealth = original_stealth
            if rows:
                return rows
            if self.stealth:
                print("[daangn] fetcher=Playwright")
                rows = self._search_with_playwright_fallback(url, limit=limit)
            if rows:
                return rows
            last_rows = rows
        return last_rows

    def parse_search_response(self, resp: Response, *, limit: int = 40) -> list[RawListing]:
        html = str(resp.html_content)
        query = _query_from_url(str(resp.url))
        self._filtered_irrelevant = 0
        if _debug_daangn_enabled():
            print(f"[daangn] html length={len(html)} query={query}")
            print(f"[daangn] title={_html_title(html)[:200]} query={query}")
        if _debug_html_enabled():
            print(f"[daangn] html head={html[:500]!r} query={query}")
        desc = self.response_description(resp)
        payload = self._extract_search_result_payload(html, query=query)
        if payload:
            rows = self._from_next_json(resp.url, payload, desc, limit, query=query)
            print("[daangn] source=json")
            print(f"[daangn] search results count={len(payload)}")
            print(f"[daangn] accepted count={len(rows)}")
            print(f"[daangn] parsed links={len(rows)} query={query}")
            print(f"[daangn] http filtered irrelevant={self._filtered_irrelevant} query={query}")
            _log_parsed_items(query, rows)
            return rows
        print("[daangn] no search result payload found")

        # 레거시(.flea-market-article)는 명시적인 검색 결과 카드일 때만 HTML parser로 사용한다.
        legacy = self._from_flea_market_articles(resp, desc, limit, query=query)
        if legacy:
            print("[daangn] source=html")
            print(f"[daangn] search results count={len(legacy)}")
            print(f"[daangn] accepted count={len(legacy)}")
            print(f"[daangn] parsed links={len(legacy)} query={query}")
            print(f"[daangn] http filtered irrelevant={self._filtered_irrelevant} query={query}")
            _log_parsed_items(query, legacy)
            return legacy

        print("[daangn] source=html")
        print("[daangn] search results count=0")
        print("[daangn] accepted count=0")
        print(f"[daangn] parsed links=0 query={query}")
        print(f"[daangn] http filtered irrelevant={self._filtered_irrelevant} query={query}")
        return []

    @staticmethod
    def _script_json_candidates(html: str) -> list[tuple[str, Any]]:
        scripts = re.findall(r"(?is)<script([^>]*)>(.*?)</script>", html or "")
        decoder = json.JSONDecoder()
        out: list[tuple[str, Any]] = []
        for attrs, body in scripts:
            attrs_l = attrs.lower()
            if not body or not any(
                marker in attrs_l or marker in body
                for marker in (
                    "__NEXT_DATA__",
                    "application/json",
                    "application/ld+json",
                    "self.__next_f.push",
                    "/kr/buy-sell/",
                    "fleamarket",
                    "article",
                )
            ):
                continue
            label = "script"
            id_match = re.search(r"""id=["']([^"']+)["']""", attrs, re.I)
            type_match = re.search(r"""type=["']([^"']+)["']""", attrs, re.I)
            if id_match:
                label = f"script#{id_match.group(1)}"
            elif type_match:
                label = f"script[type={type_match.group(1)}]"

            text = unescape(body).strip()
            if not text:
                continue
            try:
                out.append((label, json.loads(text)))
                continue
            except Exception:
                pass

            push_matches = re.findall(r"self\.__next_f\.push\((\[.*?\])\)", text, flags=re.S)
            for raw in push_matches:
                try:
                    out.append((f"{label}:next_f", json.loads(raw)))
                except Exception:
                    continue

            if "/kr/buy-sell/" not in text:
                continue
            starts = [m.start() for m in re.finditer(r"[\[{]", text)]
            for start in starts[:80]:
                try:
                    obj, _ = decoder.raw_decode(text[start:])
                except Exception:
                    continue
                out.append((f"{label}:embedded", obj))
        return out

    @staticmethod
    def _json_text(obj: Any, *, max_chars: int = 20_000) -> str:
        parts: list[str] = []

        def walk(node: Any) -> None:
            if len(" ".join(parts)) >= max_chars:
                return
            if isinstance(node, dict):
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, (str, int, float)):
                parts.append(str(node))

        walk(obj)
        return _clean_text(" ".join(parts))[:max_chars]

    @staticmethod
    def _json_listing_href(row: dict[str, Any]) -> str:
        stack: list[Any] = [row]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, str) and _is_listing_href(node):
                return node
        return ""

    def _iter_json_lists(self, obj: Any, path: str = "") -> list[tuple[str, list[dict[str, Any]]]]:
        found: list[tuple[str, list[dict[str, Any]]]] = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                child_path = f"{path}.{key}" if path else str(key)
                if isinstance(value, list):
                    rows = [item for item in value if isinstance(item, dict) and self._json_listing_href(item)]
                    if rows:
                        found.append((child_path, rows))
                found.extend(self._iter_json_lists(value, child_path))
        elif isinstance(obj, list):
            rows = [item for item in obj if isinstance(item, dict) and self._json_listing_href(item)]
            if rows:
                found.append((path or "root", rows))
            for idx, item in enumerate(obj[:200]):
                found.extend(self._iter_json_lists(item, f"{path}[{idx}]"))
        return found

    def _extract_search_result_payload(self, html: str, *, query: str) -> list[dict[str, Any]]:
        blocked_path_words = ("recommend", "nearby", "popular", "related", "home", "footer", "banner")
        explicit_search_path_words = ("search", "result")
        weak_listing_path_words = ("fleamarket", "article", "buy", "sell", "product")
        candidates: list[tuple[int, str, list[dict[str, Any]]]] = []

        for label, payload in self._script_json_candidates(html):
            for path, rows in self._iter_json_lists(payload):
                path_l = path.lower()
                if any(word in path_l for word in blocked_path_words):
                    continue
                rows_with_query = [row for row in rows if _text_matches_query(self._json_text(row), query)]
                explicit_path_score = 3 if any(word in path_l for word in explicit_search_path_words) else 0
                weak_path_score = 1 if any(word in path_l for word in weak_listing_path_words) else 0
                query_score = 2 if rows_with_query else 0
                if explicit_path_score == 0 and query_score == 0:
                    continue
                selected = rows if explicit_path_score else rows_with_query
                if not selected:
                    continue
                candidates.append((explicit_path_score + weak_path_score + query_score, f"{label}:{path}", selected))

        if not candidates:
            return []
        candidates.sort(key=lambda item: (-item[0], -len(item[2]), item[1]))
        if _debug_daangn_enabled():
            score, source, rows = candidates[0]
            print(f"[daangn] json search payload={source} score={score} count={len(rows)} query={query}")
        return candidates[0][2]

    def _from_next_json(
        self,
        page_url: str,
        articles: list[dict[str, Any]],
        page_desc: str,
        limit: int,
        query: str = "",
    ) -> list[RawListing]:
        out: list[RawListing] = []
        for row in articles:
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
            price = row.get("price") or row.get("priceText") or row.get("price_text")
            price_text = str(price).strip() if isinstance(price, str) else ""
            if isinstance(price, str):
                price_krw = parse_price_krw(price)
            elif isinstance(price, (int, float)):
                price_krw = int(price)
                price_text = f"{price_krw:,}원"
            else:
                row_text = self._json_text(row, max_chars=4000)
                price_text = extract_price_text(row_text)
                price_krw = parse_price_krw(price_text)
            href = row.get("href") or row.get("url") or row.get("webUrl") or row.get("web_url") or self._json_listing_href(row)
            _debug_detail_candidate(str(href))
            if not _is_listing_href(str(href)):
                _debug_detail_rejected(str(href), _detail_reject_reason(str(href)))
                continue
            listing_url = _absolute_detail_url(str(href))
            if not title:
                title = _title_from_detail_url(listing_url)
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
                    trade = _normalize_trade_state(v)
                    break
            # 브랜드 매칭/모델명 추정은 "매물 자체 텍스트"에서만 해야 한다.
            # page_desc(검색 페이지 전체 HTML 요약/URL 포함)를 섞으면 q=브랜드 키워드 때문에 오탐이 난다.
            row_desc = " ".join(x for x in (title, str(status), str(price)) if x)[:20_000]
            if not _is_valid_listing_item(title, price_krw, listing_url, query=query, description=row_desc):
                if _debug_daangn_enabled():
                    reason, brand_match, bag_match = _listing_reject_reason(
                        title,
                        price_krw,
                        listing_url,
                        query=query,
                        description=row_desc,
                    )
                    print(
                        "[daangn] json rejected "
                        f"reason={reason} brand_match={int(brand_match)} bag_match={int(bag_match)} "
                        f"title={title[:80]} price={price_krw} price_text={price_text!r} url={listing_url}"
                    )
                self._filtered_irrelevant += 1
                continue
            _debug_detail_accepted(listing_url)
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
                    price_text=price_text,
                    source_title=title,
                    fetched_at=utc_now_iso(),
                )
            )
            if len(out) >= limit:
                break
        return out

    def _from_flea_market_articles(self, resp: Response, page_desc: str, limit: int, query: str = "") -> list[RawListing]:
        """``.flea-market-article`` 고정 셀렉터 파싱."""
        out: list[RawListing] = []
        cards = resp.css("article.flea-market-article")
        for art in cards:
            href = str(art.css("a[href*='/buy-sell/']::attr(href)").get() or "").strip()
            if not href:
                href = str(art.css("a::attr(href)").get() or "").strip()
            _debug_detail_candidate(href)
            if not _is_listing_href(href):
                _debug_detail_rejected(href, _detail_reject_reason(href))
                continue
            title = str(art.css("h3::text").get() or "").strip()
            if len(title) < 2:
                title = str(art.css("img::attr(alt)").get() or "").strip()
            if title.strip().lower() in ("thumbnail", "image", "thumbnailurl"):
                title = ""
            if len(title) < 2:
                title = str(art.xpath("normalize-space(.//a[1])").get() or "").strip()
            title = title[:400]
            price_text = str(art.css("p.article-price::text").get() or "").strip()
            price_krw = parse_price_krw(price_text)
            if price_krw is None:
                price_text = extract_price_text(str(art.get()))
                price_krw = parse_price_krw(price_text)
            img = str(art.css("img::attr(src)").get() or "").strip()
            region = str(art.css("p.article-region-name::text").get() or "").strip()
            if not region:
                region = str(art.css(".article-region-name::text").get() or "").strip()
            listing_url = _absolute_detail_url(href)
            if not title:
                title = _title_from_detail_url(listing_url)
            description = f"{title} {region}".strip()
            if not _is_valid_listing_item(title, price_krw, listing_url, query=query, description=description):
                self._filtered_irrelevant += 1
                continue
            _debug_detail_accepted(listing_url)
            excerpt = str(art.get())[:12_000]
            out.append(
                RawListing(
                    source="daangn",
                    model_name=title or listing_url,
                    price_krw=price_krw,
                    status_text=region,
                    listing_url=listing_url or resp.url,
                    image_url=absolutize_url(resp.url, img),
                    description_text=description,
                    trade_state=None,
                    raw_html_excerpt=(excerpt + ("\n\n--- page ---\n" + page_desc[:8_000] if page_desc else ""))[:12_000],
                    price_text=price_text,
                    source_title=title,
                    fetched_at=utc_now_iso(),
                )
            )
            if len(out) >= limit:
                break
        return out

    def _from_buy_sell_anchors(self, resp: Response, page_desc: str, limit: int, query: str = "") -> list[RawListing]:
        """
        2026-04 기준 당근 검색 페이지는 JS 렌더링이 많아
        카드 전용 클래스가 고정되지 않을 수 있다. 상세 링크 앵커를 기준으로 파싱한다.
        """
        out: list[RawListing] = []
        seen: set[str] = set()
        anchors = resp.css("a[href*='/buy-sell/'], a[href*='/articles/']")
        for a in anchors:
            href = str(a.css("::attr(href)").get() or "").strip()
            _debug_detail_candidate(href)
            if not _is_listing_href(href):
                _debug_detail_rejected(href, _detail_reject_reason(href))
                continue
            listing_url = _absolute_detail_url(href)
            key = listing_url.rstrip("/")
            if key in seen:
                continue
            seen.add(key)

            scope = a
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
            if title == listing_url:
                title = _title_from_detail_url(listing_url) or title

            price_text = extract_price_text(blob) or extract_price_text(title)
            price_krw = parse_price_krw(price_text)
            if not _is_valid_listing_item(title, price_krw, listing_url, query=query, description=blob):
                self._filtered_irrelevant += 1
                continue
            _debug_detail_accepted(listing_url)
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
                    price_text=price_text,
                    source_title=title,
                    fetched_at=utc_now_iso(),
                )
            )
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _is_inside_non_listing_area(node: Any) -> bool:
        cur = node
        for _ in range(8):
            cur = getattr(cur, "parent", None)
            if cur is None:
                return False
            name = str(getattr(cur, "name", "") or "").lower()
            if name in ("nav", "header", "footer", "aside"):
                return True
            attrs = getattr(cur, "attrs", {}) or {}
            marker = " ".join(
                str(x)
                for x in (
                    attrs.get("id", ""),
                    " ".join(attrs.get("class", []) if isinstance(attrs.get("class"), list) else [attrs.get("class", "")]),
                    attrs.get("role", ""),
                    attrs.get("aria-label", ""),
                )
            ).lower()
            if any(word in marker for word in ("navigation", "navbar", "gnb", "footer", "header", "recommend")):
                return True
        return False

    @staticmethod
    def _extract_location_from_soup(scope: Any) -> str:
        selectors = (
            "[class*='region']",
            "[class*='location']",
            "[class*='address']",
            "[data-testid*='region']",
            "[data-testid*='location']",
        )
        for selector in selectors:
            try:
                node = scope.select_one(selector)
            except Exception:
                node = None
            if node is None:
                continue
            text = _clean_text(node.get_text(" ", strip=True))
            if text:
                return text[:120]
        text = _clean_text(scope.get_text(" ", strip=True))
        m = re.search(r"([가-힣]+(?:시|도)\s*)?([가-힣]+(?:구|군|시)\s+[가-힣0-9]+동)", text)
        return m.group(0)[:120] if m else ""

    @staticmethod
    def _element_debug_selector(node: Any) -> str:
        if node is None:
            return "document"
        name = str(getattr(node, "name", "") or "document")
        attrs = getattr(node, "attrs", {}) or {}
        if attrs.get("data-testid"):
            return f"{name}[data-testid='{attrs.get('data-testid')}']"
        if attrs.get("id"):
            return f"{name}#{attrs.get('id')}"
        classes = attrs.get("class", [])
        if isinstance(classes, str):
            classes = classes.split()
        if classes:
            return f"{name}." + ".".join(str(c) for c in classes[:3])
        role = attrs.get("role")
        if role:
            return f"{name}[role='{role}']"
        return name

    @staticmethod
    def _unique_listing_hrefs(node: Any) -> set[str]:
        urls: set[str] = set()
        for a in node.find_all("a", href=True):
            href = str(a.get("href") or "").strip()
            if _is_listing_href(href):
                urls.add(_absolute_detail_url(href).rstrip("/"))
        return urls

    def _select_search_result_root(self, soup: Any) -> tuple[Any, str, int]:
        anchors = [a for a in soup.find_all("a", href=True) if _is_listing_href(str(a.get("href") or ""))]
        all_count = len({_absolute_detail_url(str(a.get("href") or "")).rstrip("/") for a in anchors})
        if not anchors:
            return soup, "document:no_detail_links", 0

        candidates: list[tuple[int, int, Any, str]] = []
        preferred_selectors = (
            "section[data-testid*='search']",
            "section[class*='search']",
            "div[data-testid*='search']",
            "div[class*='search']",
            "section[data-testid*='feed']",
            "div[data-testid*='feed']",
            "main",
        )
        for selector in preferred_selectors:
            for node in soup.select(selector):
                count = len(self._unique_listing_hrefs(node))
                if count:
                    candidates.append((count, len(str(node)), node, selector))

        for a in anchors:
            cur = a
            for _ in range(8):
                cur = getattr(cur, "parent", None)
                if cur is None or getattr(cur, "name", "") in ("html", "body"):
                    break
                count = len(self._unique_listing_hrefs(cur))
                if count >= 2:
                    candidates.append((count, len(str(cur)), cur, self._element_debug_selector(cur)))

        if not candidates:
            return soup, "document:fallback", all_count

        max_count = max(c[0] for c in candidates)
        strong = [c for c in candidates if c[0] == max_count]
        count, _, node, selector = min(strong, key=lambda item: item[1])
        return node, selector, count

    def _from_soup_links(
        self,
        page_url: str,
        html: str,
        page_desc: str,
        limit: int,
        query: str = "",
        source_label: str = "http",
    ) -> list[RawListing]:
        """BeautifulSoup fallback for current Daangn search pages."""
        try:
            from bs4 import BeautifulSoup
        except Exception:
            return []

        soup = BeautifulSoup(html or "", "html.parser")
        out: list[RawListing] = []
        seen: set[str] = set()
        candidate_count = 0
        brand_match_count = 0
        bag_match_count = 0
        debug_detail_count = 0
        search_root, root_selector, root_link_count = self._select_search_result_root(soup)
        if _debug_daangn_enabled():
            print(f"[daangn] {source_label} search result selector={root_selector} detail_links={root_link_count} query={query}")
        for a in search_root.find_all("a", href=True):
            if self._is_inside_non_listing_area(a):
                continue
            href = str(a.get("href") or "").strip()
            if not _is_listing_href(href):
                _debug_detail_rejected(href, _detail_reject_reason(href))
                continue
            candidate_count += 1
            listing_url = _absolute_detail_url(href)
            key = listing_url.rstrip("/")
            if key in seen:
                continue
            seen.add(key)

            scope = a
            for _ in range(4):
                scope_text = _clean_text(scope.get_text(" ", strip=True))
                if parse_price_krw(scope_text) is not None and len(scope_text) >= 8:
                    break
                parent = getattr(scope, "parent", None)
                if parent is None or getattr(parent, "name", "") in ("body", "html"):
                    break
                scope = parent

            img_tag = a.find("img") or scope.find("img")
            img = ""
            title = _clean_text(str(a.get("aria-label") or a.get("title") or ""))
            if img_tag is not None:
                img = str(img_tag.get("src") or img_tag.get("data-src") or img_tag.get("srcset") or "").strip()
                if not title:
                    title = _clean_text(str(img_tag.get("alt") or ""))
            if not title or title.lower() in ("thumbnail", "image", "thumbnailurl"):
                title = _clean_text(a.get_text(" ", strip=True))

            blob = _clean_text(scope.get_text(" ", strip=True))
            if (not title or len(title) < 2) and blob:
                parts = [p.strip() for p in re.split(r"\s{2,}|\n", blob) if p.strip()]
                title = next((p for p in parts if parse_price_krw(p) is None and len(p) >= 2), "")
            if not title:
                title = _title_from_detail_url(listing_url) or listing_url

            price_text = extract_price_text(blob) or extract_price_text(title)
            price_krw = parse_price_krw(price_text)
            reject_reason, brand_match, bag_match = _listing_reject_reason(
                title,
                price_krw,
                listing_url,
                query=query,
                description=blob,
            )
            if brand_match:
                brand_match_count += 1
            if bag_match:
                bag_match_count += 1
            if _debug_daangn_enabled() and debug_detail_count < 10:
                debug_detail_count += 1
                print(
                    "[daangn] detail "
                    f"query={query} source={source_label} "
                    f"slug={_decoded_detail_slug(listing_url)} "
                    f"brand_match={int(brand_match)} bag_keyword_match={int(bag_match)} "
                    f"reject_reason={reject_reason or 'accepted'} url={listing_url}"
                )
            if reject_reason:
                self._filtered_irrelevant += 1
                continue
            _debug_detail_accepted(listing_url)
            location = self._extract_location_from_soup(scope)
            out.append(
                RawListing(
                    source="daangn",
                    model_name=title[:400],
                    price_krw=price_krw,
                    status_text=location,
                    listing_url=listing_url or page_url,
                    image_url=absolutize_url(page_url, img.split(" ", 1)[0]) if img else "",
                    description_text=blob[:2000] or title,
                    trade_state=None,
                    raw_html_excerpt=(str(scope)[:8_000] + ("\n\n--- page ---\n" + page_desc[:4_000] if page_desc else ""))[:12_000],
                    price_text=price_text,
                    source_title=title[:400],
                    fetched_at=utc_now_iso(),
                )
            )
            if len(out) >= limit:
                break

        print(f"[daangn] {source_label} soup candidate links={candidate_count} url={page_url}")
        print(
            f"[daangn] query={query} candidates={candidate_count} "
            f"brand_match={brand_match_count} bag_match={bag_match_count} accepted={len(out)}"
        )
        return out

    def _extract_playwright_dom_payload(self, page: Any, *, query: str) -> dict[str, Any]:
        script = r"""
        (query) => {
          const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
          const queryTerms = clean(query).toLowerCase().split(/\s+/).filter(Boolean);
          const hasQuery = (text) => {
            const t = clean(text).toLowerCase();
            return queryTerms.length === 0 || queryTerms.every((term) => t.includes(term));
          };
          const marker = (el) => clean([
            el.tagName || "",
            el.id || "",
            el.getAttribute("class") || "",
            el.getAttribute("data-testid") || "",
            el.getAttribute("aria-label") || "",
            el.getAttribute("role") || "",
          ].join(" ")).toLowerCase();
          const isBlocked = (el) => /(recommend|popular|nearby|footer|header|navigation|navbar|gnb|banner|related)/.test(marker(el));
          const detailLinks = (el) => Array.from(el.querySelectorAll('a[href*="/kr/buy-sell/"], a[href*="/articles/"]'))
            .filter((a) => {
              if (/[?&](q|search)=/.test(a.href || "")) return false;
              const path = new URL(a.href, location.origin).pathname;
              return /\/kr\/buy-sell\/.+-[a-z0-9]{8,}\/?$/i.test(path) || /\/articles\/\d+\/?$/i.test(path);
            });
          const priceRe = /\d[\d,]*\s*원/;
          const totalAnchors = detailLinks(document).length;
          const unique = (items) => Array.from(new Set(items));

          const cardForAnchor = (anchor, root) => {
            let cur = anchor;
            for (let i = 0; i < 7 && cur && cur !== root && cur !== document.body; i += 1) {
              const text = clean(cur.innerText || "");
              if (priceRe.test(text) && text.length >= 4 && text.length <= 1400) return cur;
              cur = cur.parentElement;
            }
            const text = clean(anchor.innerText || "");
            return priceRe.test(text) ? anchor : null;
          };

          const rootCandidates = [];
          for (const el of Array.from(document.querySelectorAll("main, section, div[data-testid], [role='list'], ul, ol"))) {
            if (isBlocked(el)) continue;
            const m = marker(el);
            const anchors = detailLinks(el);
            if (!anchors.length) continue;
            const cards = unique(anchors.map((a) => cardForAnchor(a, el)).filter(Boolean));
            const validCards = cards.filter((card) => {
              if (isBlocked(card)) return false;
              const text = clean(card.innerText || "");
              if (!priceRe.test(text)) return false;
              return hasQuery(text) || /(search|result|list|feed|catalog|article|fleamarket|product|buy|sell)/.test(m);
            });
            if (!validCards.length) continue;
            const explicit = /(search|result)/.test(m);
            const feedish = /(list|feed|catalog|article|fleamarket|product|buy|sell)/.test(m);
            rootCandidates.push({
              el,
              cards: validCards,
              score: validCards.length * 10 + (explicit ? 5 : 0) + (feedish ? 2 : 0) + (hasQuery(el.innerText) ? 2 : 0),
              size: (el.innerText || "").length,
            });
          }

          if (!rootCandidates.length) {
            return { rows: [], totalAnchors, validCards: 0 };
          }
          rootCandidates.sort((a, b) => b.score - a.score || b.cards.length - a.cards.length || a.size - b.size);
          const cards = rootCandidates[0].cards;

          const seenCards = new Set();
          const seenUrls = new Set();
          const rows = [];
          for (const card of cards) {
            if (seenCards.has(card)) continue;
            seenCards.add(card);
            const link = detailLinks(card)[0];
            if (!link) continue;
            const url = new URL(link.href, location.origin).href.split(/[?#]/)[0];
            const key = url.replace(/\/$/, "");
            if (seenUrls.has(key)) continue;
            seenUrls.add(key);
            const text = clean(card.innerText || "");
            const lines = text.split(/\n+/).map(clean).filter(Boolean);
            const priceLine = lines.find((line) => priceRe.test(line)) || "";
            const img = card.querySelector("img");
            const title = clean(
              link.getAttribute("aria-label") ||
              link.getAttribute("title") ||
              (img && img.getAttribute("alt")) ||
              lines.find((line) => line !== priceLine && !/(분 전|시간 전|일 전|끌올|채팅|관심|조회)/.test(line)) ||
              link.innerText ||
              ""
            );
            const location = lines.find((line) => /[가-힣]+(?:시|도|구|군|동|읍|면)/.test(line) && !/\d[\d,]*\s*원/.test(line)) || "";
            if ((url.includes("/kr/buy-sell/") || url.includes("/articles/")) && title && priceLine) {
              rows.push({
                title,
                price: priceLine,
                href: url,
                content: location,
                description: text,
                thumbnail: img ? (img.currentSrc || img.src || img.getAttribute("data-src") || "") : "",
              });
            }
          }
          return { rows, totalAnchors, validCards: cards.length };
        }
        """
        try:
            result = page.evaluate(script, query)
        except Exception:
            return {"rows": [], "totalAnchors": 0, "validCards": 0}
        if not isinstance(result, dict):
            return {"rows": [], "totalAnchors": 0, "validCards": 0}
        rows = result.get("rows")
        return {
            "rows": [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else [],
            "totalAnchors": int(result.get("totalAnchors") or 0),
            "validCards": int(result.get("validCards") or 0),
        }

    def _search_with_playwright_fallback(self, url: str, *, limit: int) -> list[RawListing]:
        query = _query_from_url(url)
        print(f"[daangn] playwright fallback start query={query}")
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            print(f"[daangn] playwright error={exc!r}")
            return []

        browser = None
        context = None
        page = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    locale="ko-KR",
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                current_url = page.url
                print(f"[daangn] playwright current url={current_url}")
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass
                try:
                    page.wait_for_selector(
                        "main article:has(a[href*='/kr/buy-sell/']), "
                        "main article:has(a[href*='/articles/']), "
                        "main li:has(a[href*='/kr/buy-sell/']), "
                        "main li:has(a[href*='/articles/']), "
                        "main [data-testid*='article' i]:has(a[href*='/kr/buy-sell/']), "
                        "main [data-testid*='article' i]:has(a[href*='/articles/']), "
                        "main [data-testid*='product' i]:has(a[href*='/kr/buy-sell/']), "
                        "main [class*='article' i]:has(a[href*='/kr/buy-sell/']), "
                        "main [class*='product' i]:has(a[href*='/kr/buy-sell/'])",
                        timeout=8_000,
                    )
                except Exception:
                    pass
                dom_result = self._extract_playwright_dom_payload(page, query=query)
                html = page.content()
                try:
                    body_text = _clean_text(page.locator("body").inner_text(timeout=2_000))
                except Exception:
                    body_text = ""
                if current_url.split("#", 1)[0] != page.url.split("#", 1)[0]:
                    current_url = page.url
                    print(f"[daangn] playwright current url={current_url}")
                try:
                    page.close()
                finally:
                    page = None
                try:
                    context.close()
                finally:
                    context = None
                try:
                    browser.close()
                finally:
                    browser = None
            if _debug_daangn_enabled():
                print(f"[daangn] playwright html length={len(html)} query={query}")
                print(f"[daangn] title={_html_title(html)[:200]} query={query}")
            if _debug_html_enabled():
                print(f"[daangn] playwright html head={html[:500]!r} query={query}")
            self._filtered_irrelevant = 0
            dom_payload = dom_result.get("rows", []) if isinstance(dom_result, dict) else []
            total_anchors = int(dom_result.get("totalAnchors") or 0) if isinstance(dom_result, dict) else 0
            valid_cards = int(dom_result.get("validCards") or 0) if isinstance(dom_result, dict) else 0
            print(f"[daangn] playwright total anchors={total_anchors}")
            print(f"[daangn] playwright valid cards={valid_cards}")
            if dom_payload:
                rows = self._from_next_json(url, dom_payload, "", limit, query=query)
                print("[daangn] source=playwright")
                print(f"[daangn] search results count={len(dom_payload)}")
                print(f"[daangn] accepted count={len(rows)}")
                print(f"[daangn] parsed links={len(rows)} query={query}")
                print(f"[daangn] playwright filtered irrelevant={self._filtered_irrelevant} query={query}")
                _log_parsed_items(query, rows)
                return rows

            if not self._extract_search_result_payload(html, query=query):
                print("[daangn] no search result payload found")
            print(f"[daangn] playwright body text head={body_text[:500]!r}")
            print(f"[daangn] playwright html head={html[:500]!r}")
            print("[daangn] source=playwright")
            print("[daangn] search results count=0")
            print("[daangn] accepted count=0")
            print(f"[daangn] parsed links=0 query={query}")
            print(f"[daangn] playwright filtered irrelevant={self._filtered_irrelevant} query={query}")
            return []
        except Exception as exc:
            print(f"[daangn] playwright error={exc!r}")
            return []
        finally:
            for obj in (page, context, browser):
                if obj is None:
                    continue
                try:
                    obj.close()
                except Exception:
                    pass


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

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

_WON_RE = re.compile(r"(?P<n>[\d,]+)\s*원")
_MAN_RE = re.compile(r"(?P<n>[\d.]+)\s*만")


def parse_price_krw(text: str | None) -> int | None:
    """한국어 가격 문자열에서 원 단위 정수 추출."""
    if not text:
        return None
    t = text.strip().replace("\u00a0", " ")
    m = _WON_RE.search(t)
    if m:
        return int(m.group("n").replace(",", ""))
    m2 = _MAN_RE.search(t)
    if m2:
        return int(float(m2.group("n").replace(",", "")) * 10_000)
    digits = re.sub(r"[^\d]", "", t)
    if len(digits) >= 4:
        return int(digits)
    return None


def strip_html_to_description(html: str, max_chars: int = 120_000) -> str:
    """스크립트/스타일 제거 후 본문 평문 (GPT 입력용)."""
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    html = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def absolutize_url(base: str, href: str | None) -> str:
    if not href:
        return ""
    from urllib.parse import urljoin

    return urljoin(base, href)


def find_json_list_by_key(obj: Any, target_key: str) -> list | None:
    """중첩 dict/list에서 첫 번째 target_key 리스트를 DFS로 탐색."""
    if isinstance(obj, dict):
        v = obj.get(target_key)
        if isinstance(v, list) and v:
            return v
        for child in obj.values():
            found = find_json_list_by_key(child, target_key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_json_list_by_key(item, target_key)
            if found is not None:
                return found
    return None


def parse_next_json_fleamarkets(html: str) -> list[dict[str, Any]] | None:
    """당근 등 Next.js __NEXT_DATA__ 내 fleamarketArticles 추출 시도."""
    m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(?P<j>.*?)</script>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return None
    try:
        data = json.loads(m.group("j"))
    except json.JSONDecodeError:
        return None
    articles = find_json_list_by_key(data, "fleamarketArticles")
    if articles:
        return articles
    return find_json_list_by_key(data, "allPageArticles")

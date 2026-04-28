from __future__ import annotations

import json
import re
from html import unescape
from datetime import datetime, timezone
from typing import Any

_WON_RE = re.compile(r"(?P<n>\d[\d,]*)\s*원")
_MAN_RE = re.compile(r"(?P<n>\d[\d,]*(?:\.\d+)?)\s*만\s*원?")
_BAEK_MAN_RE = re.compile(r"(?:(?P<baek>\d+)\s*백)?\s*(?P<man>\d+)\s*만\s*원?")


def parse_price_krw(text: str | None) -> int | None:
    """한국어 가격 문자열에서 원 단위 정수 추출."""
    if not text:
        return None
    t = unescape(str(text)).strip().replace("\u00a0", " ")
    t = re.sub(r"\s+", " ", t)
    if re.search(r"나눔|무료", t, re.I):
        return 0
    if re.search(r"가격\s*없음|문의|상담|ask|contact", t, re.I):
        return None
    if re.fullmatch(r"\d[\d,]*(?:\.0+)?", t):
        return int(float(t.replace(",", "")))
    candidates: list[tuple[int, int]] = []
    m = _WON_RE.search(t)
    for m in _WON_RE.finditer(t):
        n = int(m.group("n").replace(",", ""))
        candidates.append((m.start(), n))
    for m in _BAEK_MAN_RE.finditer(t):
        baek = int(m.group("baek") or 0)
        man = int(m.group("man") or 0)
        candidates.append((m.start(), (baek * 100 + man) * 10_000))
    for m in _MAN_RE.finditer(t):
        n = float(m.group("n").replace(",", ""))
        candidates.append((m.start(), int(n * 10_000)))
    valid = [(pos, price) for pos, price in candidates if 0 <= price <= 500_000_000]
    if not valid:
        return None
    valid.sort(key=lambda item: item[0])
    return valid[0][1]


def extract_price_text(text: str | None) -> str:
    if not text:
        return ""
    t = unescape(str(text)).replace("\u00a0", " ")
    t = re.sub(r"\s+", " ", t).strip()
    for regex in (_WON_RE, _BAEK_MAN_RE, _MAN_RE):
        m = regex.search(t)
        if m:
            return m.group(0).strip()
    if re.search(r"나눔|무료", t, re.I):
        return "나눔"
    return ""


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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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

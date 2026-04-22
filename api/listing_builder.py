"""Scrapling RawListing / DaangnEnrichedListing → 대시보드 ``Listing`` JSON (camelCase)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from api.brand_constants import BRAND_MATCH_PATTERNS, BAG_BRAND_CANONICAL
from api.daangn_media import is_listing_image_proxy_allowed

from collectors.models import DaangnEnrichedListing, RawListing

_BRAND_PATTERNS: list[tuple[str, str]] = list(BRAND_MATCH_PATTERNS)


def _normalize_detail_link(platform: str, url: str) -> str:
    """
    플랫폼별 '진짜 상세 페이지' URL만 남기기.
    - 메인/검색 페이지 URL이면 빈 문자열 반환(=수집 실패 취급).
    """
    p = (platform or "").strip().lower()
    u = (url or "").strip()
    if not u or not u.startswith("http"):
        return ""

    # Daangn: /articles/{id} 우선, 없으면 /kr/buy-sell/{slug}도 상세로 인정.
    if p == "daangn":
        if u == "https://www.daangn.com" or u.rstrip("/") in ("https://www.daangn.com/kr", "https://www.daangn.com/kr/buy-sell"):
            return ""
        if "/articles/" in u:
            return u
        if "/kr/buy-sell/" in u and u.rstrip("/").endswith("/kr/buy-sell") is False:
            return u
        return ""

    # Bunjang: query 제거하고 /products/{id}로 정규화
    if p == "bunjang":
        m = re.search(r"/products/(\d+)", u)
        if not m:
            return ""
        pid = m.group(1)
        return f"https://m.bunjang.co.kr/products/{pid}"

    # Feelway: view_goods.php?g_no={id} 형태 강제
    if p == "feelway":
        m = re.search(r"view_goods\.php\?g_no=(\d+)", u)
        if not m:
            return ""
        gid = m.group(1)
        return f"https://www.feelway.com/view_goods.php?g_no={gid}"

    # Gugus: 아직 검색 URL이 404로 불안정. 상세(goodsView/goodsNo)만 통과.
    if p in ("gugus", "gogoose"):
        if "goodsView" in u or "goodsNo=" in u:
            return u
        return ""

    return u

# (캐논 브랜드, 제목/설명 부분문자열·별칭 소문자, 정규화 시 권장 표기)
# 긴 별칭을 먼저 넣을 것(부분일치 순서).
_MODEL_ALIAS_ROWS: list[tuple[str, str, str]] = [
    ("샤넬", "클래식 미듐", "Classic Medium Flap"),
    ("샤넬", "클래식미듐", "Classic Medium Flap"),
    ("샤넬", "클미", "Classic Medium Flap"),
    ("샤넬", "보이백", "Boy Bag Medium"),
    ("샤넬", "woc", "Wallet on Chain"),
    ("루이비통", "네버풀", "Neverfull MM"),
    ("루이비통", "neverfull", "Neverfull MM"),
    ("루이비통", "스피디", "Speedy 25"),
    ("루이비통", "speedy", "Speedy 25"),
    ("루이비통", "온더고", "OnTheGo MM"),
    ("루이비통", "capucines", "Capucines MM"),
    ("루이비통", "캡슈신", "Capucines MM"),
    ("구찌", "마몬트", "GG Marmont Small"),
    ("구찌", "marmont", "GG Marmont Small"),
    ("구찌", "디오니소스", "Dionysus Small"),
    ("구찌", "호스빗", "Horsebit 1955"),
    ("에르메스", "버킨", "Birkin 30"),
    ("에르메스", "birkin", "Birkin 30"),
    ("에르메스", "켈리", "Kelly 28"),
    ("에르메스", "kelly", "Kelly 28"),
    ("에르메스", "이블린", "Evelyne TPM"),
    ("에르메스", "피코탄", "Picotin 18"),
    ("에르메스", "린디", "Lindy 26"),
    ("고야드", "생루이", "Saint Louis PM"),
    ("고야드", "st louis", "Saint Louis PM"),
    ("고야드", "아르투아", "Artois MM"),
    ("고야드", "아노", "Anjou Mini"),
    ("고야드", "벨베드", "Belvedere PM"),
    ("디올", "북토트", "Book Tote Medium"),
    ("디올", "book tote", "Book Tote Medium"),
    ("디올", "레이디 디올", "Lady Dior Medium"),
    ("디올", "레이디디올", "Lady Dior Medium"),
    ("디올", "lady dior", "Lady Dior Medium"),
    ("디올", "새들", "Saddle Medium"),
    ("프라다", "사피아노", "Galleria Saffiano Medium"),
    ("프라다", "갈레리아", "Galleria Saffiano Medium"),
    ("프라다", "re-edition", "Re-Edition 2005"),
    ("프라다", "리에디션", "Re-Edition 2005"),
    ("프라다", "나일론", "Re-Nylon Backpack"),
    ("보테가베네타", "카세트", "Cassette Medium"),
    ("보테가베네타", "조디", "Jodie Medium"),
    ("보테가베네타", "jodie", "Jodie Medium"),
    ("보테가베네타", "아르코", "Arco 33"),
    ("보테가베네타", "파우치", "Pouch Large"),
    ("셀린느", "러기지", "Luggage Micro"),
    ("셀린느", "luggage", "Luggage Micro"),
    ("셀린느", "트리옹프", "Triomphe Medium"),
    ("셀린느", "클래식 박스", "Classic Box Medium"),
    ("펜디", "바게트", "Baguette Medium"),
    ("펜디", "baguette", "Baguette Medium"),
    ("펜디", "피카부", "Peekaboo Medium"),
    ("펜디", "펜디매니아", "Fendi Mania Shopper"),
    ("발렌시아가", "시티", "City Medium"),
    ("발렌시아가", "아워글래스", "Hourglass Small"),
    ("발렌시아가", "hourglass", "Hourglass Small"),
    ("발렌시아가", "네오 클래식", "Neo Classic City S"),
    ("생로랑", "루루", "LouLou Medium"),
    ("생로랑", "loulou", "LouLou Medium"),
    ("생로랑", "삭드주르", "Sac de Jour Small"),
    ("생로랑", "카이아", "Kaia Medium"),
    ("생로랑", "엔벨로프", "Envelope Chain Medium"),
    ("버버리", "캔버스 체크", "TB Canvas Tote Medium"),
    ("버버리", "롤라", "Lola Small"),
    ("버버리", "프레임", "Title Double Flap"),
    ("미우미우", "와더", "Wander Matelassé"),
    ("미우미우", "아이리스", "Iris Medium"),
    ("토즈", "디 백", "Di Bag Medium"),
    ("토즈", "타임리스", "Timeless T Leather Mini"),
    ("발렌티노", "록스터드", "Rockstud Spike Medium"),
    ("발렌티노", "vsling", "VSLing Medium"),
    ("페라가모", "가니치니", "Gancini Top Handle"),
    ("페라가모", "바라", "Vara Bow Medium"),
    ("끌로에", "나일", "Nile Bracelet Medium"),
    ("끌로에", "마르씨", "Marcie Medium"),
    ("끌로에", "페이", "Faye Medium"),
    ("지방시", "앤티고나", "Antigona Medium"),
    ("지방시", "antigona", "Antigona Medium"),
    ("알렉산더맥퀸", "스컬", "Skull Clutch"),
    ("몽클레어", "몽클레어 백", "Leather Tote"),
    ("카르티에", "팬더", "Panthère Mini Top Handle"),
    ("불가리", "세르펜티", "Serpenti Forever"),
    ("불가리", "serpenti", "Serpenti Forever"),
]

_MODEL_ALIAS_ROWS.sort(key=lambda r: len(r[1]), reverse=True)

LISTING_NORMALIZATION_LLM_SYSTEM_PROMPT = """\
당신은 한국 중고 명품 가방(핸드백) 매물의 제목·설명을 분석해 브랜드·모델명을 정규화하는 어시스턴트입니다.

규칙:
1) 브랜드는 아래 캐논 한글 이름 중 하나로만 출력합니다.
2) 모델은 영문 정식 라인명 + 사이즈(있으면) 형태를 권장합니다. (예: Classic Medium Flap, Neverfull MM)
3) 애칭·오타·줄임말은 아래 별칭 테이블을 참고해 정식 모델로 매핑합니다.
4) 확신이 낮으면 원문 제목을 유지하되 브랜드만 캐논명으로 교정합니다.
5) status_summary: 매물 상태·구성을 한국어로 **약 15자 이내** 한 줄로 요약합니다. (예: 'A급 모서리 미세', '새제급 풀구성')
6) is_suspicious: 본문·가격 패턴상 가품·레플·허위 저가 등 **의심 징후**가 있으면 true, 없으면 false.

캐논 브랜드(가방/핸드백 카테고리):
{brands}

별칭 → 권장 표기 (일부; 나머지는 동일 패턴으로 추론):
{aliases}

출력 형식(JSON 한 개만, 마크다운 없이):
{{"brand_ko": "…", "normalized_model": "…", "confidence": 0.0~1.0, "status_summary": "…", "is_suspicious": false}}
""".format(
    brands=", ".join(BAG_BRAND_CANONICAL),
    aliases="; ".join(f"{nick}→{m}({b})" for b, nick, m in _MODEL_ALIAS_ROWS[:80]),
)


def _guess_brand(text: str) -> str:
    t = text or ""
    for label, pat in _BRAND_PATTERNS:
        if re.search(pat, t, re.I):
            return label
    return "기타"


def _normalize_model_line(brand: str, raw_title: str, description: str) -> str:
    """별칭·대표 라인 기반 휴리스틱 정규화( LLM 없이 )."""
    blob = f"{raw_title} {description}".lower()
    if brand == "기타":
        return (raw_title or "").strip()[:200] or "—"
    for b, nick, model in _MODEL_ALIAS_ROWS:
        if b != brand:
            continue
        if nick.lower() in blob:
            return f"{brand} {model}"
    cleaned = re.sub(r"\s+", " ", (raw_title or "").strip())
    return cleaned[:200] if cleaned else "—"


_SUMMARY_MAX = 15

_SUSPICIOUS_TEXT = re.compile(
    r"가품|가품문의|가품의심|가품\s*아님|정품\s*아님|짝퉁|레플|레플리카|replica|fake\s*bag|"
    r"counterfeit|이미테이션|비교\s*가|비교가|퀄\s*좋|원가\s*이하|착한\s*가격|특가\s*9{2,}|"
    r"명품\s*스타일|브랜드\s*스타일",
    re.I,
)


def _clamp_summary(s: str, max_len: int = _SUMMARY_MAX) -> str:
    t = re.sub(r"\s+", " ", (s or "").strip())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _heuristic_status_summary(blob: str, grade: str, warranty: bool, receipt: bool) -> str:
    """LLM 미연동 PoC용 — 상태를 약 15자 내 한국어로 요약."""
    b = blob or ""
    if re.search(r"미개봉|새제|새상품|택\s*있|택달", b):
        core = "새제급 풀구성"
    elif re.search(r"생(?:텍|얼)|거의\s*새", b):
        core = "생얼·컨디션 양호"
    elif re.search(r"하자|스크래치|찍힘|오염", b):
        core = f"{grade}급·일부 하자"
    elif grade == "B":
        core = "B급 사용감 있음"
    elif grade == "A":
        core = "A급 전반 양호"
    else:
        core = "S급 최상 컨디션"
    if receipt and warranty:
        core = _clamp_summary(f"{core}·영수증·개런티", _SUMMARY_MAX)
    elif receipt:
        core = _clamp_summary(f"{core}·영수증", _SUMMARY_MAX)
    elif warranty:
        core = _clamp_summary(f"{core}·개런티", _SUMMARY_MAX)
    return _clamp_summary(core, _SUMMARY_MAX)


def _is_suspicious_listing(blob: str, price: int, market: int | None) -> bool:
    """본문·가격 휴리스틱 가품/비정상 의심."""
    b = blob or ""
    if _SUSPICIOUS_TEXT.search(b):
        return True
    if re.search(r"\b\d\s*만\s*원|\d{1,2}\s*만에\s*급매", b) and price > 0 and price < 300_000:
        return True
    if market and market >= 2_000_000 and price > 0 and price < int(market * 0.12):
        return True
    return False


def _expected_profit_krw(price: int, market: int | None) -> int:
    if market is None or market <= 0 or price < 0:
        return 0
    return max(0, int(market) - int(price))


def _guess_ai_from_text(blob: str) -> dict[str, Any]:
    b = blob or ""
    warranty = bool(re.search(r"보증서|개런티|게런티", b))
    receipt = bool(re.search(r"영수증|구매영수증", b))
    grade = "S"
    if re.search(r"\bB급| B급|상태\s*B", b, re.I):
        grade = "B"
    elif re.search(r"\bA급| A급|상태\s*A", b, re.I):
        grade = "A"
    return {"warranty": warranty, "receipt": receipt, "condition_grade": grade}


def _profit_rate_pct(price: int, market: int | None) -> float:
    if not market or market <= 0 or price <= 0:
        return 0.0
    return round((market - price) / market * 100.0, 2)


def _absolute_daangn_listing_url(url: str) -> str:
    """상대 경로·스킴 없는 URL을 당근 웹 절대 URL로."""
    u = (url or "").strip()
    if not u:
        return "https://www.daangn.com/kr/"
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return "https://www.daangn.com" + u
    if not u.startswith("http"):
        return "https://www.daangn.com/" + u.lstrip("/")
    return u


def _utc_collected_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def collected_timestamp_iso() -> str:
    """데모·시드 행에 붙일 서버 수집 시각 (UTC ISO)."""
    return _utc_collected_iso()


def _platform_prices_with_defaults(pp_in: dict[str, Any] | None) -> dict[str, int]:
    """미수집 플랫폼은 ``0`` — 프론트에서 '확인 중'으로 표시."""
    pp = pp_in or {}

    def one(key: str) -> int:
        v = pp.get(key)
        if v is None:
            return 0
        try:
            n = int(v)
            return n if n > 0 else 0
        except (TypeError, ValueError):
            return 0

    return {
        "gogoose_lowest_krw": one("gugus"),
        "feelway_lowest_krw": one("feelway"),
        "bunjang_lowest_krw": one("bunjang"),
    }


def _coerce_reasonable_price(v: int | None) -> int | None:
    """플랫폼 파싱 오류(outlier) 방어용 범위 체크."""
    if v is None:
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    if n < 50_000 or n > 500_000_000:
        return None
    return n


def _avg_market_price_from_platforms(pp_in: dict[str, Any] | None) -> int | None:
    """
    4사 비교 기준가:
    - (번개/필웨이/구구스) 수집값 중 '정상 범위'만 모아 평균.
    - 값이 없으면 None.
    """
    pp = pp_in or {}
    vals: list[int] = []
    for k in ("bunjang", "feelway", "gugus"):
        v = pp.get(k)
        n = _coerce_reasonable_price(v if isinstance(v, (int, float)) else None)
        if n:
            vals.append(n)
    if not vals:
        return None
    return int(sum(vals) / len(vals))


def _browser_image_proxy_url(raw_img: str) -> str:
    """Vite 등 프론트 오리진의 ``/api`` 프록시와 맞추기 위해 상대 경로 사용."""
    from urllib.parse import quote

    return f"/api/image?url={quote(raw_img.strip(), safe='')}"


def _ref_platform_to_frontend(ref: str | None) -> str | None:
    if ref == "gugus":
        return "gogoose"
    if ref in ("bunjang", "feelway", "gogoose"):
        return ref
    return ref


def _platform_links_for_api(enriched: DaangnEnrichedListing) -> dict[str, str]:
    """시세에 쓰인 상세 URL — 프론트 ``PlatformId`` 키(gogoose)로 통일."""
    pl = enriched.platform_listing_urls or {}
    out: dict[str, str] = {}
    for src_key, api_key in (("bunjang", "bunjang"), ("feelway", "feelway"), ("gugus", "gogoose")):
        v = pl.get(src_key)
        if isinstance(v, str) and v.strip():
            out[api_key] = v.strip()
    return out


def enriched_to_listing_dict(
    enriched: DaangnEnrichedListing,
    *,
    use_image_proxy: bool,
    image_proxy_prefix: str = "",
) -> dict[str, Any]:
    _ = image_proxy_prefix  # 브라우저는 상대 경로 ``/api/image`` 사용 (Vite 프록시)
    d = enriched.daangn
    brand = _guess_brand(d.model_name + " " + d.description_text)
    blob_ai = d.description_text + " " + d.model_name
    ai = _guess_ai_from_text(blob_ai)
    # 기존: 최저가 기준 → 변경: 4사(번개/필웨이/구구스) 평균 시세 기준
    market = _avg_market_price_from_platforms(enriched.platform_prices_krw)
    price = int(d.price_krw or 0)
    ref = market if market and market > 0 else price
    grade = str(ai.get("condition_grade") or "A")
    status_summary = _heuristic_status_summary(
        blob_ai, grade, bool(ai.get("warranty")), bool(ai.get("receipt"))
    )
    is_suspicious = _is_suspicious_listing(blob_ai, price, market)
    expected_profit = _expected_profit_krw(price, market)
    platform_prices = _platform_prices_with_defaults(enriched.platform_prices_krw)
    ref_platform = _ref_platform_to_frontend(enriched.reference_platform)
    raw_img = (d.image_url or "").strip()
    if use_image_proxy and raw_img and is_listing_image_proxy_allowed(raw_img):
        image_url = _browser_image_proxy_url(raw_img)
    else:
        image_url = raw_img

    lid = hashlib.sha256(f"{d.listing_url}|{d.model_name}".encode()).hexdigest()[:20]
    source_url = _absolute_daangn_listing_url(d.listing_url or "")
    source_url = _normalize_detail_link("daangn", source_url) or source_url
    platform_links = _platform_links_for_api(enriched)

    return {
        "id": f"api-{lid}",
        "brand": brand,
        "rawTitle": d.model_name,
        "normalizedModel": _normalize_model_line(brand, d.model_name, d.description_text),
        "price": price,
        "marketPrice": int(ref) if ref else price,
        "arbitrageRate": _profit_rate_pct(price, market),
        "status_summary": status_summary,
        "is_suspicious": is_suspicious,
        "expected_profit": expected_profit,
        "location": (d.status_text or "")[:80] or "—",
        "postedMinutesAgo": 0,
        "imageUrl": image_url,
        "sourceUrl": source_url,
        "link": source_url,
        "platform": "daangn",
        "platformLinks": platform_links,
        "status": "완료",
        "ai_status": ai,
        "platform_prices": platform_prices,
        "reference_platform": ref_platform,
        "reference_price_krw": market,
        "collectedAt": _utc_collected_iso(),
    }


def raw_daangn_to_partial_dict(raw: RawListing, *, use_image_proxy: bool = True) -> dict[str, Any]:
    """시세 없이 당근 행만 있을 때 (중간 스냅샷)."""
    brand = _guess_brand(raw.model_name + " " + raw.description_text)
    blob_ai = raw.description_text + " " + raw.model_name
    ai = _guess_ai_from_text(blob_ai)
    price = int(raw.price_krw or 0)
    grade = str(ai.get("condition_grade") or "A")
    status_summary = _heuristic_status_summary(
        blob_ai, grade, bool(ai.get("warranty")), bool(ai.get("receipt"))
    )
    is_suspicious = _is_suspicious_listing(blob_ai, price, None)
    expected_profit = 0
    lid = hashlib.sha256(f"{raw.listing_url}|{raw.model_name}".encode()).hexdigest()[:20]
    raw_img = (raw.image_url or "").strip()
    if use_image_proxy and raw_img and is_listing_image_proxy_allowed(raw_img):
        img_out = _browser_image_proxy_url(raw_img)
    else:
        img_out = raw_img
    source_url = _absolute_daangn_listing_url(raw.listing_url or "")
    source_url = _normalize_detail_link("daangn", source_url) or source_url
    return {
        "id": f"api-{lid}",
        "brand": brand,
        "rawTitle": raw.model_name,
        "normalizedModel": _normalize_model_line(brand, raw.model_name, raw.description_text),
        "price": price,
        "marketPrice": price,
        "arbitrageRate": 0.0,
        "status_summary": status_summary,
        "is_suspicious": is_suspicious,
        "expected_profit": expected_profit,
        "location": (raw.status_text or "")[:80] or "—",
        "postedMinutesAgo": 0,
        "imageUrl": img_out,
        "sourceUrl": source_url,
        "link": source_url,
        "platform": "daangn",
        "platformLinks": {},
        "status": "완료",
        "ai_status": ai,
        "platform_prices": _platform_prices_with_defaults({}),
        "reference_platform": None,
        "reference_price_krw": None,
        "collectedAt": _utc_collected_iso(),
    }


def raw_market_to_listing_dict(
    raw: RawListing,
    *,
    platform: str,
    use_image_proxy: bool = True,
) -> dict[str, Any]:
    """
    번개/필웨이/구구스 등 '독립 피드'용 RawListing → Listing dict.
    (기능 로직은 그대로 두고, 최소 필드만 채워 대시보드/텔레그램 파이프라인에 올린다.)
    """
    plat = (platform or raw.source or "").strip().lower() or "daangn"
    brand = _guess_brand(raw.model_name + " " + raw.description_text)
    blob_ai = raw.description_text + " " + raw.model_name
    ai = _guess_ai_from_text(blob_ai)
    price = int(raw.price_krw or 0)
    grade = str(ai.get("condition_grade") or "A")
    status_summary = _heuristic_status_summary(
        blob_ai, grade, bool(ai.get("warranty")), bool(ai.get("receipt"))
    )
    is_suspicious = _is_suspicious_listing(blob_ai, price, None)
    lid = hashlib.sha256(f"{raw.listing_url}|{raw.model_name}|{plat}".encode()).hexdigest()[:20]

    raw_img = (raw.image_url or "").strip()
    if use_image_proxy and raw_img and is_listing_image_proxy_allowed(raw_img):
        img_out = _browser_image_proxy_url(raw_img)
    else:
        img_out = raw_img

    link = (raw.listing_url or "").strip()
    if link.startswith("//"):
        link = "https:" + link
    link_norm = _normalize_detail_link(plat, link)
    source_url = link_norm or (link if link.startswith("http") else link)

    return {
        "id": f"api-{plat}-{lid}",
        "brand": brand,
        "rawTitle": raw.model_name,
        "normalizedModel": _normalize_model_line(brand, raw.model_name, raw.description_text),
        "price": price,
        "marketPrice": price,
        "arbitrageRate": 0.0,
        "status_summary": status_summary,
        "is_suspicious": is_suspicious,
        "expected_profit": 0,
        "location": (raw.status_text or "")[:80] or "—",
        "postedMinutesAgo": 0,
        "imageUrl": img_out,
        "sourceUrl": source_url,
        "link": source_url,
        "platform": plat,
        "platformLinks": {},
        "status": "완료",
        "ai_status": ai,
        "platform_prices": _platform_prices_with_defaults({}),
        "reference_platform": None,
        "reference_price_krw": None,
        "collectedAt": _utc_collected_iso(),
    }

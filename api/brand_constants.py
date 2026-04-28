"""
명품 가방/핸드백 수집용 브랜드 (영문·국문 쌍 + 매칭 정규식).

프론트 `BAG_BRAND_PAIRS` / `BAG_BRANDS`·`settings_store`·당근 검색 쿼리와 동기화할 것.
"""

from __future__ import annotations

import re
from typing import TypedDict

# ---------------------------------------------------------------------------
BAG_SEARCH_SUFFIXES: tuple[str, ...] = ("가방", "핸드백")


class BagBrandDef(TypedDict):
    ko: str
    en: str
    pattern: str


# (국문 캐논, 필웨이식 영문 표기, 제목·설명 매칭 정규식) — 구체적·긴 패턴을 앞에 둘 것.
BAG_BRAND_DEFS: tuple[BagBrandDef, ...] = (
    {"ko": "반클리프아펠", "en": "Van Cleef & Arpels", "pattern": r"반클리프|반클리프\s*아펠|Van\s*Cleef|VCA\b|Arpels"},
    {"ko": "메종마르지엘라", "en": "Maison Margiela", "pattern": r"메종\s*마르지엘라|Maison\s*Margiela|Margiela"},
    {"ko": "돌체앤가바나", "en": "Dolce&Gabbana", "pattern": r"돌체\s*(앤|&)\s*가바나|Dolce\s*Gabbana|Dolce\s*&\s*Gabbana|D\s*&\s*G\b|DG\b"},
    {"ko": "메종키츠네", "en": "Maison Kitsune", "pattern": r"메종\s*키츠네|Maison\s*Kitsun[eé]|Kitsune"},
    {"ko": "피어오브갓", "en": "Fear of God", "pattern": r"피어\s*오브\s*갓|Fear\s*of\s*God|FOG\b"},
    {"ko": "루이비통", "en": "Louis Vuitton", "pattern": r"루이비통|Louis\s*Vuitton|루이\s*비통|루이뷔통|LV\b|lv\b"},
    {"ko": "미우미우", "en": "Miu Miu", "pattern": r"미우미우|Miu\s*Miu|MIU\s*MIU"},
    {"ko": "생로랑", "en": "Saint Laurent", "pattern": r"생로랑|Saint\s*Laurent|입생로랑|YSL\b|ysl\b"},
    {"ko": "알렉산더맥퀸", "en": "Alexander McQueen", "pattern": r"알렉산더\s*맥퀸|Alexander\s*McQueen|McQueen|맥퀸"},
    {"ko": "보테가베네타", "en": "Bottega Veneta", "pattern": r"보테가\s*베네타|BOTTEGA\s*VENETA|Bottega|보테가"},
    {"ko": "브루넬로쿠치넬리", "en": "Brunello Cucinelli", "pattern": r"브루넬로|Cucinelli|Brunello\s*Cucinelli"},
    {"ko": "파텍필립", "en": "Patek Philippe", "pattern": r"파텍\s*필립|Patek\s*Philippe|PATEK"},
    {"ko": "크롬하츠", "en": "Chrome Hearts", "pattern": r"크롬\s*하츠|Chrome\s*Hearts"},
    {"ko": "디스퀘어드2", "en": "Dsquared2", "pattern": r"디스퀘어드|Dsquared2|D\s*Squared"},
    {"ko": "발렌시아가", "en": "Balenciaga", "pattern": r"발렌시아가|Balenciaga|BALENCIAGA"},
    {"ko": "페라가모", "en": "Ferragamo", "pattern": r"페라가모|FERRAGAMO|Ferragamo|살바토레\s*페라가모"},
    {"ko": "에르메스", "en": "HERMES", "pattern": r"에르메스|HERM[EÈ]S|Hermes|에르메"},
    {"ko": "프라다", "en": "PRADA", "pattern": r"프라다|PRADA|Prada"},
    {"ko": "셀린느", "en": "CELINE", "pattern": r"셀린느|셀린|CELINE|Celine"},
    {"ko": "로에베", "en": "Loewe", "pattern": r"로에베|LOEWE|Loewe"},
    {"ko": "고야드", "en": "GOYARD", "pattern": r"고야드|GOYARD|Goyard|고야투드"},
    {"ko": "펜디", "en": "FENDI", "pattern": r"펜디|FENDI|Fendi"},
    {"ko": "토즈", "en": "TODS", "pattern": r"토즈|TOD'?S|Tods"},
    {"ko": "샤넬", "en": "CHANEL", "pattern": r"샤넬|CHANEL|Chanel"},
    {"ko": "구찌", "en": "GUCCI", "pattern": r"구찌|GUCCI|Gucci"},
    {"ko": "디올", "en": "DIOR", "pattern": r"디올|DIOR|Dior"},
    {"ko": "지방시", "en": "Givenchy", "pattern": r"지방시|GIVENCHY|Givenchy"},
    {"ko": "끌로에", "en": "Chloe", "pattern": r"끌로에|CHLOE|Chloé|Chloe"},
    {"ko": "몽클레어", "en": "Moncler", "pattern": r"몽클레어|몽클레르|MONCLER|Moncler"},
    {"ko": "카르티에", "en": "Cartier", "pattern": r"카르티에|Cartier|CARTIER"},
    {"ko": "불가리", "en": "BVLGARI", "pattern": r"불가리|BVLGARI|Bvlgari|불가리"},
    {"ko": "버버리", "en": "Burberry", "pattern": r"버버리|BURBERRY|Burberry"},
    {"ko": "발렌티노", "en": "Valentino", "pattern": r"발렌티노|VALENTINO|Valentino"},
    {"ko": "발망", "en": "Balmain", "pattern": r"발망|Balmain|BALMAIN"},
    {"ko": "베르사체", "en": "Versace", "pattern": r"베르사체|VERSACE|Versace"},
    {"ko": "톰포드", "en": "TOM FORD", "pattern": r"톰\s*포드|TOM\s*FORD|Tom\s*Ford"},
    {"ko": "톰브라운", "en": "Thom Browne", "pattern": r"톰\s*브라운|Thom\s*Browne"},
    {"ko": "태그호이어", "en": "Tag Heuer", "pattern": r"태그\s*호이어|TAG\s*Heuer|Tag\s*Heuer"},
    {"ko": "오메가", "en": "OMEGA", "pattern": r"오메가|OMEGA|Omega"},
    {"ko": "롤렉스", "en": "Rolex", "pattern": r"롤렉스|ROLEX|Rolex"},
    {"ko": "브라이틀링", "en": "Breitling", "pattern": r"브라이틀링|Breitling|BREITLING"},
    {"ko": "다미아니", "en": "Damiani", "pattern": r"다미아니|Damiani"},
    {"ko": "티파니", "en": "TIFFANY & Co", "pattern": r"티파니|Tiffany|TIFFANY"},
    {"ko": "로로피아나", "en": "Loro Piana", "pattern": r"로로\s*피아나|Loro\s*Piana"},
    {"ko": "막스마라", "en": "Max Mara", "pattern": r"막스\s*마라|Max\s*Mara|MAX\s*MARA"},
    {"ko": "이자벨마랑", "en": "Isabel Marant", "pattern": r"이자벨\s*마랑|Isabel\s*Marant"},
    {"ko": "스톤아일랜드", "en": "Stone Island", "pattern": r"스톤\s*아일랜드|Stone\s*Island"},
    {"ko": "씨피컴퍼니", "en": "CP Company", "pattern": r"씨피\s*컴퍼니|CP\s*Company|C\.?\s*P\.?\s*Company"},
    {"ko": "골든구스", "en": "Golden Goose", "pattern": r"골든\s*구스|Golden\s*Goose"},
    {"ko": "오프화이트", "en": "Off White", "pattern": r"오프\s*화이트|Off\s*-?\s*White|OffWhite"},
    {"ko": "나이키", "en": "Nike", "pattern": r"나이키|Nike|NIKE\b"},
    {"ko": "아미", "en": "Ami", "pattern": r"아미|Ami|AMI\b"},
    {"ko": "비비안웨스트우드", "en": "Vivienne Westwood", "pattern": r"비비안|Westwood|Vivienne"},
    {"ko": "우영미", "en": "WOOYOUNGMI", "pattern": r"우영미|Wooyoungmi|WOOYOUNGMI"},
)

POC_TARGET_BRANDS: tuple[str, ...] = ("샤넬", "루이비통", "구찌")
_BRAND_DEF_BY_KO: dict[str, BagBrandDef] = {d["ko"]: d for d in BAG_BRAND_DEFS}
_POC_BRAND_DEFS: tuple[BagBrandDef, ...] = tuple(_BRAND_DEF_BY_KO[b] for b in POC_TARGET_BRANDS)

BAG_BRAND_CANONICAL: tuple[str, ...] = tuple(d["ko"] for d in _POC_BRAND_DEFS)
BAG_BRAND_PAIRS: tuple[tuple[str, str], ...] = tuple((d["ko"], d["en"]) for d in _POC_BRAND_DEFS)

BRAND_MATCH_PATTERNS: tuple[tuple[str, str], ...] = tuple((d["ko"], d["pattern"]) for d in _POC_BRAND_DEFS)

assert BAG_BRAND_CANONICAL == POC_TARGET_BRANDS, f"expected PoC brands {POC_TARGET_BRANDS}, got {BAG_BRAND_CANONICAL}"
assert len(BAG_BRAND_CANONICAL) == len({b for b in BAG_BRAND_CANONICAL}), "duplicate canonical ko brand"


def build_daangn_bag_queries() -> list[str]:
    """브랜드 × (가방|핸드백) 당근 검색 쿼리 전부 (국문 키워드)."""
    out: list[str] = []
    for brand in BAG_BRAND_CANONICAL:
        for suf in BAG_SEARCH_SUFFIXES:
            out.append(f"{brand} {suf}")
    return out


_SCRAPE_BRAND_ROTATION = {"offset": 0}


def build_daangn_bag_queries_scheduled(
    *,
    batch_brands: int | None = None,
    advance: bool = True,
) -> list[str]:
    """
    당근 검색 쿼리 — 브랜드가 많을 때 **배치로 순환**해 한 주기 부담을 줄임.

    - ``LUXEFINDER_SCRAPE_BRAND_BATCH`` 환경변수: 한 주기당 브랜드 수 (미설정 시 기본 3, 오프셋 순환).
    - ``0`` 또는 브랜드 수 이상 → 매 주기 전 브랜드 검색.
    - ``advance=True``이면 호출마다 오프셋을 진행해 시간에 따라 전 브랜드를 훑음.
    """
    from os import environ

    brands = list(BAG_BRAND_CANONICAL)
    n = len(brands)
    raw = (environ.get("LUXEFINDER_SCRAPE_BRAND_BATCH") or "").strip()
    try:
        # 환경변수 미설정 시 0이면 매 주기 전 브랜드×접미어를 전부 돌려 첫 응답이 수십 분~수시간 걸릴 수 있음.
        # 기본 3브랜드(×가방/핸드백)만 돌리고 오프셋으로 순환 — 전체 스캔은 LUXEFINDER_SCRAPE_BRAND_BATCH=0
        default_batch = 3
        batch = int(raw) if raw else (batch_brands if batch_brands is not None else default_batch)
    except ValueError:
        batch = 0
    if batch <= 0 or batch >= n:
        return build_daangn_bag_queries()
    start = _SCRAPE_BRAND_ROTATION["offset"] % n
    out: list[str] = []
    for j in range(batch):
        brand = brands[(start + j) % n]
        for suf in BAG_SEARCH_SUFFIXES:
            out.append(f"{brand} {suf}")
    if advance:
        _SCRAPE_BRAND_ROTATION["offset"] = (start + batch) % n
    return out


def text_matches_catalog_brand(text: str) -> str | None:
    """제목·설명 등에서 카탈로그 브랜드 하나를 찾으면 캐논 국문명, 없으면 None."""
    blob = text or ""
    for canon, pat in BRAND_MATCH_PATTERNS:
        if re.search(pat, blob, re.I):
            return canon
    return None

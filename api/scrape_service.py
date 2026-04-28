"""PoC realtime scraper: Daangn one listing -> analysis -> market compare -> Telegram."""

from __future__ import annotations

import os
import random
import re
import sys
import threading
import time
import traceback
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from statistics import median
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import httpx

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

POC_BRANDS: tuple[str, ...] = ("샤넬", "루이비통", "구찌")
POC_QUERIES: tuple[str, ...] = tuple(q for b in POC_BRANDS for q in (f"{b} 가방", f"{b} 핸드백"))
MODEL_MAP: dict[str, tuple[str, str]] = {
    "클미": ("샤넬", "샤넬 클래식 미디움 플랩백"),
    "클래식 미디움": ("샤넬", "샤넬 클래식 미디움 플랩백"),
    "클래식 미듐": ("샤넬", "샤넬 클래식 미디움 플랩백"),
    "클래식 플랩": ("샤넬", "샤넬 클래식 플랩백"),
    "보이백": ("샤넬", "샤넬 보이백"),
    "보이 백": ("샤넬", "샤넬 보이백"),
    "woc": ("샤넬", "샤넬 월렛 온 체인"),
    "월렛온체인": ("샤넬", "샤넬 월렛 온 체인"),
    "마몬트": ("구찌", "구찌 GG 마몬트 숄더백"),
    "gg 마몬트": ("구찌", "구찌 GG 마몬트 숄더백"),
    "디오니소스": ("구찌", "구찌 디오니소스 숄더백"),
    "홀스빗": ("구찌", "구찌 홀스빗 1955"),
    "재키": ("구찌", "구찌 재키 1961"),
    "네버풀": ("루이비통", "루이비통 네버풀 MM"),
    "neverfull": ("루이비통", "루이비통 네버풀 MM"),
    "스피디": ("루이비통", "루이비통 스피디 25"),
    "speedy": ("루이비통", "루이비통 스피디 25"),
    "온더고": ("루이비통", "루이비통 온더고 MM"),
    "onthego": ("루이비통", "루이비통 온더고 MM"),
    "알마": ("루이비통", "루이비통 알마 BB"),
}
MARKET_PLATFORMS: tuple[str, ...] = ("bunjang", "feelway", "gugus")
PLATFORM_PRICE_KEYS: dict[str, str] = {
    "bunjang": "bunjang_lowest_krw",
    "feelway": "feelway_lowest_krw",
    "gugus": "gogoose_lowest_krw",
}
PLATFORM_LINK_KEYS: dict[str, str] = {
    "bunjang": "bunjang",
    "feelway": "feelway",
    "gugus": "gogoose",
}
GRADE_RANK = {"S": 3, "A": 2, "B": 1, "C": 0}
SOLD_KEYWORDS = ("거래완료", "판매완료", "완료", "sold", "판매됨")

_SEEN_LOCK = threading.Lock()
_SEEN_LISTING_IDS: set[str] = set()
_BACKGROUND_STARTED = False
_BACKGROUND_STOP_EVENT = threading.Event()
_BACKGROUND_THREAD: threading.Thread | None = None
_BACKGROUND_LOCK = threading.Lock()
_QUERY_LOCK = threading.Lock()
_QUERY_CURSOR = 0
_QUERY_LAST_REQUEST_AT: dict[str, float] = {}
_QUERY_ORDER: list[str] = []


def clear_seen_listing_ids() -> None:
    with _SEEN_LOCK:
        _SEEN_LISTING_IDS.clear()
    print("[scraper] cleared seen ids")


@dataclass(frozen=True)
class ListingAnalysis:
    brand: str
    normalized_model_name: str
    has_authenticity_proof: bool
    condition_grade: str
    reasoning_short: str
    eligible: bool


@dataclass(frozen=True)
class MarketQuote:
    platform: str
    price: int | None
    url: str | None
    basis: str
    sold_count: int
    sample_count: int
    price_text: str = ""
    source_title: str = ""
    fetched_at: str = ""
    status: str = "ok"
    error: str = ""


@dataclass(frozen=True)
class MarketTarget:
    brand: str
    model_name: str
    raw_title: str
    required_groups: tuple[tuple[str, ...], ...]

    @property
    def matchable(self) -> bool:
        return bool(self.brand and self.required_groups)


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _log_fetches_enabled() -> bool:
    return _env_bool("LUXEFINDER_LOG_FETCHES", default=False)


def configure_fetch_logging() -> None:
    if _log_fetches_enabled():
        logging.getLogger("scrapling").setLevel(logging.INFO)
    else:
        logging.getLogger("scrapling").setLevel(logging.WARNING)


def _utc_collected_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _listing_id_from_raw(raw: Any) -> str:
    source = f"{getattr(raw, 'listing_url', '')}|{getattr(raw, 'model_name', '')}"
    return "api-" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:20]


def _absolute_daangn_url(url: str) -> str:
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


def _image_url(raw_img: str, *, use_image_proxy: bool) -> str:
    img = (raw_img or "").strip()
    if not img:
        return ""
    if not use_image_proxy:
        return img
    try:
        from api.daangn_media import is_listing_image_proxy_allowed

        if is_listing_image_proxy_allowed(img):
            return f"/api/image?url={quote(img, safe='')}"
    except Exception:
        traceback.print_exc()
    return img


def _seed_listings() -> list[dict[str, Any]]:
    """수집 비활성화 데모용. 실제 실패 fallback으로는 기본 사용하지 않는다."""
    ts = _utc_collected_iso()
    return [
        {
            "id": "seed-1",
            "brand": "샤넬",
            "rawTitle": "[시드] 샤넬 클래식 미듐 블랙 가방",
            "normalizedModel": "샤넬 클래식 미듐 블랙 가방",
            "normalized_model_name": "샤넬 클래식 미듐 블랙 가방",
            "price": 8_900_000,
            "marketPrice": 12_350_000,
            "arbitrageRate": 27.94,
            "status_summary": "A급 전반 양호",
            "is_suspicious": False,
            "expected_profit": 3_450_000,
            "location": "API 시드",
            "postedMinutesAgo": 1,
            "imageUrl": "",
            "sourceUrl": "https://www.daangn.com/kr/",
            "link": "https://www.daangn.com/kr/",
            "platform": "daangn",
            "platformLinks": {
                "bunjang": "https://m.bunjang.co.kr/",
                "feelway": "https://www.feelway.com/",
                "gogoose": "https://www.gugus.co.kr/",
            },
            "status": "완료",
            "analysis_status": "market_final",
            "has_authenticity_proof": True,
            "condition_grade": "A",
            "reasoning_short": "시드 데이터",
            "ai_status": {"warranty": True, "receipt": True, "condition_grade": "A"},
            "platform_prices": {
                "gogoose_lowest_krw": 12_400_000,
                "feelway_lowest_krw": 12_500_000,
                "bunjang_lowest_krw": 12_350_000,
            },
            "reference_platform": "bunjang",
            "reference_price_krw": 12_350_000,
            "collectedAt": ts,
        }
    ]


def _detect_brand(text: str) -> str | None:
    blob = text or ""
    patterns = {
        "샤넬": r"샤넬|CHANEL|Chanel",
        "루이비통": r"루이\s*비통|루이비통|루이뷔통|Louis\s*Vuitton|LV\b|lv\b",
        "구찌": r"구찌|GUCCI|Gucci",
    }
    for brand, pattern in patterns.items():
        if re.search(pattern, blob, re.I):
            return brand
    return None


def _normalize_brand(value: str) -> str:
    detected = _detect_brand(value)
    return detected or (value if value in POC_BRANDS else "")


def _looks_like_bag(text: str) -> bool:
    return bool(re.search(r"가방|핸드백|숄더|토트|크로스|백팩|클러치|백\b|bag|handbag|tote|shoulder", text or "", re.I))


def _has_authenticity_proof(text: str) -> bool:
    return bool(re.search(r"보증서|개런티|게런티|영수증|구매내역|인보이스|정품카드|authentic|receipt|invoice", text or "", re.I))


def _condition_grade(text: str) -> str:
    blob = text or ""
    if re.search(r"\bS급|새상품|미사용|사용감\s*없|거의\s*새|unused|like\s*new", blob, re.I):
        return "S"
    if re.search(r"\bA급|상태\s*좋|상태\s*양호|깨끗|미세\s*사용감|good", blob, re.I):
        return "A"
    if re.search(r"\bC급|하자|찢|파손|오염\s*심|수선\s*필요|repair", blob, re.I):
        return "C"
    return "B"


def _settings_gemini_key(settings_store: Any) -> str:
    env_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if env_key:
        return env_key
    if settings_store is None:
        return ""
    try:
        snap = settings_store.snapshot()
    except Exception:
        traceback.print_exc()
        return ""
    return str(getattr(snap, "openai_api_key", "") or "").strip()


def _gemini_models() -> list[str]:
    configured = (os.environ.get("GEMINI_MODEL") or "").strip()
    models = [configured] if configured else []
    models.extend(["gemini-flash-latest", "gemini-2.0-flash-lite", "gemini-2.0-flash"])
    out: list[str] = []
    for model in models:
        if model and model not in out:
            out.append(model)
    return out


def _gemini_model() -> str:
    return _gemini_models()[0]


def _gemini_generate_url(api_key: str, model: str | None = None) -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model or _gemini_model()}:generateContent?key={api_key}"


def _post_gemini_generate(client: httpx.Client, *, api_key: str, payload: dict[str, Any]) -> httpx.Response:
    last: httpx.Response | None = None
    last_exc: Exception | None = None
    for model in _gemini_models():
        try:
            resp = client.post(_gemini_generate_url(api_key, model), json=payload)
        except httpx.HTTPError as exc:
            last_exc = exc
            print(f"[analysis] Gemini model fallback error={exc!r} model={model}", file=sys.stderr)
            continue
        if resp.status_code not in (404, 429):
            return resp
        last = resp
        print(f"[analysis] Gemini model fallback status={resp.status_code} model={model}", file=sys.stderr)
    if last is None:
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No Gemini model configured")
    return last


def _parse_llm_json(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def normalize_model(title: str, description: str = "", *, brand: str | None = None) -> str:
    """Rule-first nickname/alias normalization for PoC luxury bag models."""
    blob = f"{title or ''} {description or ''}".lower()
    detected_brand = _normalize_brand(brand or _detect_brand(blob) or "")
    matches: list[tuple[int, str]] = []
    for alias, (alias_brand, normalized) in MODEL_MAP.items():
        if detected_brand and alias_brand != detected_brand:
            continue
        idx = blob.find(alias.lower())
        if idx >= 0:
            matches.append((len(alias), normalized))
    if matches:
        matches.sort(reverse=True)
        return matches[0][1]
    return ""


def llm_extract_model(title: str, description: str = "", *, brand: str, api_key: str = "") -> str:
    """Ask LLM only for the model name. Returns empty string when unclear/unavailable."""
    if not api_key or brand not in POC_BRANDS:
        return ""
    system = (
        "Extract the normalized luxury bag model name from a Korean secondhand listing. "
        "Return only JSON exactly like {\"model_name\":\"...\"}. "
        "Use the given brand. If the model is unclear or only generic words like bag/handbag appear, "
        "return {\"model_name\":\"\"}. Do not invent a model."
    )
    user = f"BRAND: {brand}\nTITLE:\n{title}\n\nDESCRIPTION:\n{description[:2500]}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{system}\n\n{user}"},
                ]
            }
        ]
    }
    try:
        with httpx.Client(timeout=12.0) as client:
            resp = _post_gemini_generate(client, api_key=api_key, payload=payload)
        resp.raise_for_status()
        payload = resp.json()
        content = payload["candidates"][0]["content"]["parts"][0]["text"]
        data = _parse_llm_json(content)
        if not data:
            return ""
        candidate = re.sub(r"\s+", " ", str(data.get("model_name") or "").strip())
        if not _model_name_is_clear(candidate, brand):
            return ""
        if brand not in candidate:
            candidate = f"{brand} {candidate}".strip()
        return candidate[:180]
    except Exception as exc:
        print(f"[analysis] Gemini model-name extraction failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return ""


def get_model_name(
    title: str,
    description: str = "",
    *,
    brand: str | None = None,
    api_key: str = "",
) -> str:
    """Final model normalizer: MODEL_MAP rules first, LLM fallback second."""
    normalized = normalize_model(title, description, brand=brand)
    if normalized:
        return normalized
    detected_brand = _normalize_brand(brand or _detect_brand(f"{title} {description}") or "")
    return llm_extract_model(title, description, brand=detected_brand, api_key=api_key)


def _llm_analyze_listing(raw: Any, *, api_key: str) -> ListingAnalysis | None:
    title = str(getattr(raw, "model_name", "") or "")
    desc = str(getattr(raw, "description_text", "") or "")
    if not api_key:
        return None
    system = (
        "You analyze Korean secondhand luxury bag listings for a PoC. "
        "Return only compact JSON with keys: brand, normalized_model_name, "
        "has_authenticity_proof, condition_grade, reasoning_short. "
        "Allowed brands are 샤넬, 루이비통, 구찌. Category must be bags only. "
        "condition_grade must be one of S,A,B,C. Be conservative: if model is unclear, "
        "return normalized_model_name as empty string; if proof is not explicit, false."
    )
    user = f"TITLE:\n{title}\n\nDESCRIPTION:\n{desc[:3000]}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{system}\n\n{user}"},
                ]
            }
        ]
    }
    try:
        with httpx.Client(timeout=18.0) as client:
            resp = _post_gemini_generate(client, api_key=api_key, payload=payload)
        resp.raise_for_status()
        payload = resp.json()
        content = payload["candidates"][0]["content"]["parts"][0]["text"]
        data = _parse_llm_json(content)
        if not data:
            return None
        brand = _normalize_brand(str(data.get("brand") or "").strip())
        normalized = get_model_name(title, desc, brand=brand, api_key=api_key)
        if not normalized:
            normalized = str(data.get("normalized_model_name") or "").strip()
        grade = str(data.get("condition_grade") or "").strip().upper()[:1] or "C"
        proof = bool(data.get("has_authenticity_proof"))
        reasoning = str(data.get("reasoning_short") or "").strip()[:160]
        eligible = _analysis_passes_filters(
            brand=brand,
            normalized_model_name=normalized,
            has_authenticity_proof=proof,
            condition_grade=grade,
            raw_text=f"{title} {desc}",
        )
        return ListingAnalysis(
            brand=brand,
            normalized_model_name=normalized,
            has_authenticity_proof=proof,
            condition_grade=grade,
            reasoning_short=reasoning or "LLM 분석",
            eligible=eligible,
        )
    except Exception as exc:
        print(f"[analysis] Gemini analysis failed; using conservative heuristic fallback: {exc}", file=sys.stderr)
        traceback.print_exc()
        return None


def _model_name_is_clear(model_name: str, brand: str) -> bool:
    text = re.sub(r"\s+", " ", (model_name or "").strip())
    if not text or len(text) < 4:
        return False
    generic = {"가방", "핸드백", "정품", "명품", "샤넬", "루이비통", "구찌", "백", "bag"}
    tokens = [t for t in re.split(r"[\s/,_-]+", text.lower()) if t]
    informative = [t for t in tokens if t not in generic and t != brand.lower()]
    return bool(informative)


def _analysis_passes_filters(
    *,
    brand: str,
    normalized_model_name: str,
    has_authenticity_proof: bool,
    condition_grade: str,
    raw_text: str,
) -> bool:
    if brand not in POC_BRANDS:
        return False
    if not _looks_like_bag(raw_text):
        return False
    if not has_authenticity_proof:
        return False
    if GRADE_RANK.get((condition_grade or "").upper(), 0) < GRADE_RANK["A"]:
        return False
    if not _model_name_is_clear(normalized_model_name, brand):
        return False
    return True


def analyze_listing(raw: Any, *, settings_store: Any = None) -> ListingAnalysis:
    api_key = _settings_gemini_key(settings_store)
    llm = _llm_analyze_listing(raw, api_key=api_key)
    if llm is not None:
        return llm

    title = str(getattr(raw, "model_name", "") or "")
    desc = str(getattr(raw, "description_text", "") or "")
    blob = f"{title} {desc}"
    brand = _normalize_brand(_detect_brand(blob) or "")
    is_bag = _looks_like_bag(blob)
    proof = _has_authenticity_proof(blob)
    grade = _condition_grade(blob)
    normalized = get_model_name(title, desc, brand=brand, api_key=api_key)

    reasons: list[str] = []
    if not brand:
        reasons.append("PoC 대상 브랜드 아님")
    if not is_bag:
        reasons.append("가방 키워드 없음")
    if not proof:
        reasons.append("보증/구매 증빙 없음")
    if GRADE_RANK.get(grade, 0) < GRADE_RANK["A"]:
        reasons.append(f"상태 {grade} 등급")
    if not _model_name_is_clear(normalized, brand):
        reasons.append("모델명 추론 실패")
    if not reasons:
        reasons.append(f"{brand} 가방, 증빙 확인, 상태 {grade}")

    eligible = _analysis_passes_filters(
        brand=brand,
        normalized_model_name=normalized,
        has_authenticity_proof=proof,
        condition_grade=grade,
        raw_text=blob,
    )
    return ListingAnalysis(
        brand=brand,
        normalized_model_name=normalized,
        has_authenticity_proof=proof,
        condition_grade=grade,
        reasoning_short="; ".join(reasons)[:120],
        eligible=eligible,
    )


def _empty_platform_prices() -> dict[str, int]:
    return {
        "bunjang_lowest_krw": 0,
        "feelway_lowest_krw": 0,
        "gogoose_lowest_krw": 0,
    }


def _base_listing_from_raw(raw: Any, analysis: ListingAnalysis, *, use_image_proxy: bool) -> dict[str, Any]:
    price = int(getattr(raw, "price_krw", 0) or 0)
    source_url = _absolute_daangn_url(str(getattr(raw, "listing_url", "") or ""))
    return {
        "id": _listing_id_from_raw(raw),
        "brand": analysis.brand,
        "rawTitle": str(getattr(raw, "model_name", "") or ""),
        "normalizedModel": analysis.normalized_model_name,
        "normalized_model_name": analysis.normalized_model_name,
        "price": price,
        "daangn_price": price,
        "daangn_price_text": str(getattr(raw, "price_text", "") or ""),
        "daangn_url": source_url,
        "marketPrice": price,
        "arbitrageRate": 0.0,
        "status_summary": analysis.reasoning_short,
        "is_suspicious": False,
        "expected_profit": 0,
        "location": str(getattr(raw, "status_text", "") or "")[:80],
        "postedMinutesAgo": 0,
        "imageUrl": _image_url(str(getattr(raw, "image_url", "") or ""), use_image_proxy=use_image_proxy),
        "sourceUrl": source_url,
        "link": source_url,
        "platform": "daangn",
        "platformLinks": {},
        "status": "분석중",
        "analysis_status": "new_listing",
        "eligible": analysis.eligible,
        "analysis_eligible": analysis.eligible,
        "exclusion_reason": "" if analysis.eligible else analysis.reasoning_short,
        "has_authenticity_proof": analysis.has_authenticity_proof,
        "condition_grade": analysis.condition_grade,
        "reasoning_short": analysis.reasoning_short,
        "ai_status": {
            "warranty": analysis.has_authenticity_proof,
            "receipt": analysis.has_authenticity_proof,
            "condition_grade": analysis.condition_grade,
        },
        "platform_prices": _empty_platform_prices(),
        "reference_platform": None,
        "reference_price_krw": None,
        "collectedAt": _utc_collected_iso(),
    }


def _safe_listing_url(item: Any) -> str | None:
    if item is None:
        return None
    url = str(getattr(item, "listing_url", "") or "").strip()
    return url if url.startswith("http") else None


def _market_item_text(item: Any) -> str:
    return " ".join(
        str(getattr(item, attr, "") or "")
        for attr in ("model_name", "status_text", "trade_state", "description_text")
    )


_BRAND_ALIASES: dict[str, tuple[str, ...]] = {
    "샤넬": ("샤넬", "chanel"),
    "루이비통": ("루이비통", "루이 비통", "louis vuitton", "louisvuitton", "vuitton", "lv"),
    "구찌": ("구찌", "gucci"),
}

_MODEL_TOKEN_ALIASES: dict[str, tuple[str, ...]] = {
    "클래식": ("클래식", "classic"),
    "미디움": ("미디움", "미듐", "medium"),
    "플랩백": ("플랩백", "플랩", "flap"),
    "보이백": ("보이백", "보이 백", "boy"),
    "월렛": ("월렛", "wallet"),
    "체인": ("체인", "chain"),
    "마몬트": ("마몬트", "marmont"),
    "디오니소스": ("디오니소스", "dionysus"),
    "홀스빗": ("홀스빗", "horsebit"),
    "재키": ("재키", "jackie"),
    "네버풀": ("네버풀", "neverfull"),
    "스피디": ("스피디", "speedy"),
    "온더고": ("온더고", "on the go", "onthego"),
    "알마": ("알마", "alma"),
    "bb": ("bb",),
    "mm": ("mm",),
    "25": ("25",),
    "1955": ("1955",),
    "1961": ("1961",),
}

_MODEL_EXACT_GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {
    "샤넬 보이백": (("보이백", "보이 백", "보이샤넬", "보이 샤넬", "boy bag", "boybag", "boy"),),
    "샤넬 월렛 온 체인": (("woc", "월렛온체인", "월렛 온 체인", "wallet on chain"),),
}

_VARIANT_GROUPS: dict[str, tuple[str, ...]] = {
    "블랙": ("블랙", "black", "noir", "느와르", "누아르", "노아르"),
    "화이트": ("화이트", "white", "blanc"),
    "브라운": ("브라운", "brown", "marron"),
    "베이지": ("베이지", "beige"),
    "카멜": ("카멜", "camel"),
    "레드": ("레드", "red", "rouge"),
    "핑크": ("핑크", "pink"),
    "그레이": ("그레이", "grey", "gray", "gris"),
    "네이비": ("네이비", "navy"),
    "에피": ("에피", "에삐", "epi"),
    "모노그램": ("모노그램", "monogram"),
    "다미에": ("다미에", "damier"),
    "앙프렝뜨": ("앙프렝뜨", "앙프렝트", "empreinte"),
    "캐비어": ("캐비어", "caviar"),
    "램스킨": ("램스킨", "lambskin"),
    "페이던트": ("페이던트", "patent"),
    "벨벳": ("벨벳", "velvet"),
    "은장": ("은장", "실버", "silver", "shw"),
    "금장": ("금장", "골드", "gold", "ghw"),
}

_VARIANT_CONFLICT_SETS: tuple[tuple[str, ...], ...] = (
    ("블랙", "화이트", "브라운", "베이지", "카멜", "레드", "핑크", "그레이", "네이비"),
    ("에피", "모노그램", "다미에", "앙프렝뜨", "캐비어", "램스킨", "페이던트", "벨벳"),
    ("은장", "금장"),
)

_MODEL_STOPWORDS: set[str] = {
    "샤넬",
    "루이비통",
    "루이",
    "비통",
    "구찌",
    "chanel",
    "louis",
    "vuitton",
    "gucci",
    "가방",
    "핸드백",
    "백",
    "정품",
    "미사용",
    "새상품",
    "판매",
    "팝니다",
    "팔아요",
    "블랙",
    "화이트",
    "브라운",
    "카멜",
    "베이지",
    "미사용",
    "사용감",
    "풀구성",
    "구성품",
    "가죽",
    "소재",
}


def _norm_match_text(value: str) -> str:
    s = (value or "").lower()
    s = re.sub(r"[\[\](){}/\\|,_\-+.:;\"'`~!@#$%^&*=]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _contains_alias(text: str, alias: str) -> bool:
    alias_n = _norm_match_text(alias)
    if not alias_n:
        return False
    if re.fullmatch(r"[a-z0-9]{1,3}", alias_n):
        return re.search(rf"(?<![a-z0-9]){re.escape(alias_n)}(?![a-z0-9])", text) is not None
    compact_text = text.replace(" ", "")
    compact_alias = alias_n.replace(" ", "")
    return alias_n in text or compact_alias in compact_text


def _model_tokens(model_name: str, brand: str) -> list[str]:
    base = _norm_match_text(model_name)
    for alias in _BRAND_ALIASES.get(brand, (brand,)):
        base = re.sub(rf"\b{re.escape(_norm_match_text(alias))}\b", " ", base)
    tokens = [t for t in re.split(r"\s+", base) if t]
    return [t for t in tokens if t not in _MODEL_STOPWORDS and len(t) >= 2]


def _fallback_model_name_from_title(raw_title: str, brand: str) -> str:
    text = _norm_match_text(raw_title)
    for alias in _BRAND_ALIASES.get(brand, (brand,)):
        text = text.replace(_norm_match_text(alias), " ")
    for aliases in _VARIANT_GROUPS.values():
        for alias in aliases:
            text = text.replace(_norm_match_text(alias), " ")
    tokens = [t for t in re.split(r"\s+", text) if t]
    keep = [
        t
        for t in tokens
        if t not in _MODEL_STOPWORDS
        and not re.fullmatch(r"\d+년|\d+년도|\d+만|\d+원|\d+", t)
        and len(t) >= 2
    ]
    return re.sub(r"\s+", " ", f"{brand} {' '.join(keep[:5])}").strip()


def _required_model_groups(model_name: str, brand: str) -> tuple[tuple[str, ...], ...]:
    exact = _MODEL_EXACT_GROUPS.get(model_name)
    if exact:
        return exact
    groups: list[tuple[str, ...]] = []
    for token in _model_tokens(model_name, brand):
        aliases = _MODEL_TOKEN_ALIASES.get(token, (token,))
        clean_aliases = tuple(dict.fromkeys(a for a in aliases if a.strip()))
        if clean_aliases:
            groups.append(clean_aliases)
    return tuple(groups)


def _variant_groups_from_title(raw_title: str) -> tuple[tuple[str, ...], ...]:
    text = _norm_match_text(raw_title)
    groups: list[tuple[str, ...]] = []
    for _, aliases in _VARIANT_GROUPS.items():
        if any(_contains_alias(text, alias) for alias in aliases):
            groups.append(aliases)
    return tuple(groups)


def _variant_keys_in_text(text: str) -> set[str]:
    found: set[str] = set()
    for key, aliases in _VARIANT_GROUPS.items():
        if any(_contains_alias(text, alias) for alias in aliases):
            found.add(key)
    return found


def _has_conflicting_submodel(text: str, target: MarketTarget) -> bool:
    model = _norm_match_text(target.model_name)
    if "woc" not in model and "월렛" not in model:
        if any(_contains_alias(text, alias) for alias in ("woc", "월렛온체인", "월렛 온 체인", "wallet on chain")):
            return True
    if "미디움" in model or "미듐" in model or "medium" in model:
        if any(_contains_alias(text, alias) for alias in ("라지", "large", "스몰", "small", "미니", "mini")):
            return True
    if "bb" in model:
        if any(_contains_alias(text, alias) for alias in ("pm", "mm", "gm")):
            return True
    if "mm" in model:
        if any(_contains_alias(text, alias) for alias in ("bb", "pm", "gm")):
            return True
    source = _norm_match_text(target.raw_title)
    source_variants = _variant_keys_in_text(source)
    result_variants = _variant_keys_in_text(text)
    for conflict_set in _VARIANT_CONFLICT_SETS:
        wanted = source_variants.intersection(conflict_set)
        if not wanted:
            continue
        conflicting = result_variants.intersection(conflict_set).difference(wanted)
        if conflicting:
            return True
    return False


def _market_target(listing: dict[str, Any]) -> MarketTarget:
    brand = str(listing.get("brand") or "")
    raw_title = str(listing.get("rawTitle") or "")
    model_name = str(listing.get("normalized_model_name") or listing.get("normalizedModel") or "")
    if not model_name:
        model_name = normalize_model(raw_title, str(listing.get("description") or ""), brand=brand)
    if not model_name:
        model_name = _fallback_model_name_from_title(raw_title, brand)
    groups = _required_model_groups(model_name, brand) + _variant_groups_from_title(raw_title)
    return MarketTarget(brand=brand, model_name=model_name, raw_title=raw_title, required_groups=groups)


def _market_result_matches_target(item: Any, target: MarketTarget) -> bool:
    if not target.matchable:
        return False
    text = _norm_match_text(_market_item_text(item))
    brand_ok = any(_contains_alias(text, alias) for alias in _BRAND_ALIASES.get(target.brand, (target.brand,)))
    if not brand_ok:
        return False
    if _has_conflicting_submodel(text, target):
        return False
    return all(any(_contains_alias(text, alias) for alias in group) for group in target.required_groups)


def is_sold(item: Any) -> bool:
    """Return True only when a market result explicitly looks completed/sold."""
    text = _market_item_text(item).lower()
    return any(k.lower() in text for k in SOLD_KEYWORDS)


def filter_sold(results: Iterable[Any]) -> list[Any]:
    """Completed 거래완료/판매완료/sold results only."""
    return [item for item in results if is_sold(item)]


def _coerce_market_price(value: Any) -> int | None:
    try:
        price = int(value)
    except (TypeError, ValueError):
        return None
    if price < 50_000 or price > 500_000_000:
        return None
    return price


def _priced_items(items: Iterable[Any]) -> list[tuple[int, Any]]:
    out: list[tuple[int, Any]] = []
    for item in items:
        price = _coerce_market_price(getattr(item, "price_krw", None))
        if price is not None:
            out.append((price, item))
    return out


def _active_fallback_items(items: Iterable[Any]) -> list[Any]:
    active = [item for item in items if not is_sold(item)]
    return active or list(items)


def _lower_20_percent_average(priced: list[tuple[int, Any]]) -> tuple[int, Any]:
    ordered = sorted(priced, key=lambda pair: pair[0])
    take = max(1, ceil(len(ordered) * 0.2))
    lower_band = ordered[:take]
    selected_price, selected_item = min(lower_band, key=lambda pair: pair[0])
    return selected_price, selected_item


def _realistic_reference_from_items(items: list[Any]) -> tuple[int | None, Any | None, str, int, int]:
    """
    Market reference rule:
    1. Use completed/sold prices only when at least 3 sold samples exist.
    2. Otherwise fallback to active prices using lower 20% average.
    3. Never use plain lowest price as the primary market reference.
    """
    sold = filter_sold(items)
    sold_priced = _priced_items(sold)
    all_priced = _priced_items(items)
    if len(sold_priced) >= 3:
        ref = int(median([price for price, _ in sold_priced]))
        selected_price, selected_item = min(sold_priced, key=lambda pair: abs(pair[0] - ref))
        return selected_price, selected_item, "sold_median_exact_item", len(sold_priced), len(all_priced)

    fallback_priced = _priced_items(_active_fallback_items(items))
    if not fallback_priced:
        return None, None, "no_reference", len(sold_priced), len(all_priced)
    ref, selected_item = _lower_20_percent_average(fallback_priced)
    return ref, selected_item, "active_lowest_exact_item", len(sold_priced), len(all_priced)


def _compare_one_platform(platform: str, queries: tuple[str, ...], target: MarketTarget) -> MarketQuote:
    from collectors.bunjang_spider import BunjangSpider
    from collectors.feelway_spider import FeelwaySpider
    from collectors.gugus_spider import GugusSpider

    spider_map = {
        "bunjang": BunjangSpider,
        "feelway": FeelwaySpider,
        "gugus": GugusSpider,
    }
    print(f"[market] start platform={platform} queries={queries} target={target.model_name or target.raw_title}")
    try:
        if not target.matchable:
            print(f"[market] failed platform={platform} reason=model_unclear queries={queries}")
            return MarketQuote(platform, None, None, "model_unclear", 0, 0, status="failed", error="model_unclear")
        market_stealth = _env_bool("LUXEFINDER_MARKET_STEALTH", default=False)
        spider = spider_map[platform](stealth=market_stealth)
        rows: list[Any] = []
        seen_urls: set[str] = set()
        per_query_limit = _env_int("LUXEFINDER_MARKET_COMPARE_LIMIT", 12)
        for query in queries:
            batch = list(spider.search(query, limit=per_query_limit))
            print(f"[market] fetched platform={platform} query={query} rows={len(batch)}")
            for row in batch:
                key = _safe_listing_url(row) or str(getattr(row, "model_name", ""))
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                rows.append(row)
            if any(_market_result_matches_target(row, target) for row in batch):
                break
        matched_rows = [row for row in rows if _market_result_matches_target(row, target)]
        print(
            f"[market] match platform={platform} raw={len(rows)} "
            f"matched={len(matched_rows)} target={target.model_name}"
        )
        if platform == "gugus" and rows and not matched_rows:
            samples = [
                str(getattr(row, "source_title", "") or getattr(row, "model_name", ""))[:120]
                for row in rows[:5]
            ]
            print(f"[market] gugus no-match samples target={target.required_groups} samples={samples}")
        if not matched_rows:
            return MarketQuote(
                platform,
                None,
                None,
                "no_exact_model_match",
                0,
                len(rows),
                status="failed",
                error="no_exact_model_match",
            )
        price, selected, basis, sold_count, sample_count = _realistic_reference_from_items(matched_rows)
        url = _safe_listing_url(selected) if selected is not None else None
        quote = MarketQuote(
            platform,
            price,
            url,
            basis,
            sold_count,
            sample_count,
            price_text=str(getattr(selected, "price_text", "") or ""),
            source_title=str(getattr(selected, "source_title", "") or getattr(selected, "model_name", "") or ""),
            fetched_at=str(getattr(selected, "fetched_at", "") or ""),
        )
        print(f"[market] done platform={platform} price={quote.price} url={quote.url} title={quote.source_title[:80]}")
        return quote
    except Exception as exc:
        print(f"[market] error platform={platform} error={exc}")
        traceback.print_exc()
        return MarketQuote(platform, None, None, "error", 0, 0, status="failed", error=str(exc))


def _market_query(listing: dict[str, Any]) -> str:
    return _market_queries(listing)[0]


def _market_queries(listing: dict[str, Any]) -> tuple[str, ...]:
    target = _market_target(listing)
    brand = str(listing.get("brand") or "")
    base = target.model_name or str(listing.get("rawTitle") or "")
    if brand and brand not in base:
        base = f"{brand} {base}"
    variant_terms: list[str] = []
    raw_text = _norm_match_text(target.raw_title)
    for key, aliases in _VARIANT_GROUPS.items():
        if any(_contains_alias(raw_text, alias) for alias in aliases):
            variant_terms.append(key)
    exact = f"{base} {' '.join(variant_terms)}".strip()
    raw = re.sub(r"\b(정품|미사용|새상품|판매|팝니다|팔아요)\b", " ", target.raw_title)
    candidates = [exact, raw, base]
    out: list[str] = []
    for q in candidates:
        cleaned = re.sub(r"\s+", " ", q).strip()[:120]
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return tuple(out)


def _publish_market_update(state: Any, hub: Any, listing_id: str, quote: MarketQuote) -> None:
    price_key = PLATFORM_PRICE_KEYS[quote.platform]
    link_key = PLATFORM_LINK_KEYS[quote.platform]
    patch: dict[str, Any] = {
        "analysis_status": "market_update",
        "status": "시세확인중" if quote.status != "failed" else "failed",
        "platform_prices": {price_key: int(quote.price or 0)},
        f"{link_key}_price": quote.price,
        f"{link_key}_price_text": quote.price_text,
        f"{link_key}_url": quote.url,
        "platform_basis": {
            link_key: {
                "basis": quote.basis,
                "sold_count": quote.sold_count,
                "sample_count": quote.sample_count,
                "price": quote.price,
                "price_text": quote.price_text,
                "url": quote.url,
                "source_title": quote.source_title,
                "fetched_at": quote.fetched_at,
                "status": quote.status,
                "error": quote.error,
            }
        },
    }
    if quote.url:
        patch["platformLinks"] = {link_key: quote.url}
    merged = state.merge_listing(listing_id, patch)
    if merged:
        print(
            f"[scraper] market_update id={listing_id} platform={link_key} "
            f"price={quote.price} basis={quote.basis}"
        )
        hub.publish_from_thread(
            {
                "type": "market_update",
                "id": listing_id,
                "platform": link_key,
                "platform_name": link_key,
                "price": quote.price,
                "price_text": quote.price_text,
                "url": quote.url,
                "source_title": quote.source_title,
                "fetched_at": quote.fetched_at,
                "basis": quote.basis,
                "status": quote.status,
                "error": quote.error,
                "listing": merged,
            }
        )


def _finalize_market(state: Any, hub: Any, listing: dict[str, Any]) -> dict[str, Any] | None:
    latest = None
    for row in state.snapshot():
        if row.get("id") == listing.get("id"):
            latest = row
            break
    if latest is None:
        return None

    prices = latest.get("platform_prices") or {}
    basis = latest.get("platform_basis") or {}
    candidates = {
        "bunjang": _coerce_market_price(prices.get("bunjang_lowest_krw")),
        "feelway": _coerce_market_price(prices.get("feelway_lowest_krw")),
        "gogoose": _coerce_market_price(prices.get("gogoose_lowest_krw")),
    }
    sold_valid = {
        k: v
        for k, v in candidates.items()
        if isinstance(v, int)
        and v > 0
        and isinstance(basis.get(k), dict)
        and str(basis[k].get("basis")) == "sold_median"
    }
    valid = sold_valid or {k: v for k, v in candidates.items() if isinstance(v, int) and v > 0}
    price = int(latest.get("price") or 0)
    if valid:
        market_price = int(median(list(valid.values())))
        ref_platform = "sold_reference" if sold_valid else "fallback_reference"
    else:
        ref_platform = None
        market_price = None
    expected_profit = max(0, int(market_price or 0) - price) if market_price else 0
    arbitrage = round((expected_profit / market_price) * 100.0, 2) if market_price else 0.0

    patch = {
        "analysis_status": "market_final",
        "status": "완료",
        "marketPrice": market_price or price,
        "arbitrageRate": arbitrage,
        "expected_profit": expected_profit,
        "profit_rate": arbitrage,
        "reference_platform": ref_platform,
        "reference_price_krw": market_price,
        "market_reference_price": market_price,
        "market_reference_basis": ref_platform,
    }
    merged = state.merge_listing(str(listing["id"]), patch)
    if merged:
        hub.publish_from_thread({"type": "market_final", "id": listing["id"], "listing": merged})
    return merged


def _telegram_enabled_and_ready(settings_store: Any) -> tuple[str, str] | None:
    if settings_store is None:
        return None
    try:
        cfg = settings_store.snapshot()
    except Exception:
        traceback.print_exc()
        return None
    if not getattr(cfg, "telegram_notifications_enabled", True):
        return None
    token = str(getattr(cfg, "telegram_bot_token", "") or "").strip()
    chat = str(getattr(cfg, "telegram_chat_id", "") or "").strip()
    if not token or not chat:
        return None
    return token, chat


def _send_telegram_once(row: dict[str, Any], settings_store: Any, *, public_api_base: str) -> tuple[str, str]:
    creds = _telegram_enabled_and_ready(settings_store)
    if not creds:
        print(f"[telegram] skipped id={row.get('id')} reason=not_configured")
        return "failed", "not_configured"
    if not row.get("reference_price_krw"):
        print(f"[telegram] skipped id={row.get('id')} reason=no_reference_price")
        return "failed", "no_reference_price"
    token, chat = creds
    try:
        from api.telegram_notify import send_listing_alert_telegram

        ok, msg = send_listing_alert_telegram(token, chat, row, public_api_base=public_api_base.rstrip("/"))
        if not ok:
            print(f"[telegram] id={row.get('id')}: {msg}", file=sys.stderr)
            return "failed", msg
        else:
            print(f"[telegram] sent id={row.get('id')}")
            return "sent", msg
    except Exception:
        traceback.print_exc()
        return "failed", "exception"


def _publish_telegram_status(state: Any, hub: Any, listing_id: str, status: str, message: str = "") -> None:
    patch = {"telegram_status": status, "telegram_error": message}
    merged = state.merge_listing(listing_id, patch)
    if merged:
        hub.publish_from_thread(
            {
                "type": "market_update",
                "id": listing_id,
                "listing": merged,
                "telegram_status": status,
                "telegram_error": message,
            }
        )


def _passes_profit_filters(row: dict[str, Any], settings_store: Any) -> bool:
    if not row.get("reference_price_krw"):
        return False
    try:
        cfg = settings_store.snapshot() if settings_store is not None else None
    except Exception:
        traceback.print_exc()
        cfg = None
    threshold = float(getattr(cfg, "telegram_alert_threshold_percent", 25.0) if cfg else 25.0)
    min_profit = int(getattr(cfg, "telegram_min_expected_profit_krw", 0) if cfg else 0)
    rate = float(row.get("profit_rate", row.get("arbitrageRate", 0)) or 0)
    profit = int(row.get("expected_profit") or 0)
    return rate >= threshold and profit >= min_profit


def next_queries(*, per_tick: int | None = None, interval_seconds: float | None = None) -> list[str]:
    """Return the next query or queries from the PoC round-robin queue."""
    global _QUERY_CURSOR, _QUERY_ORDER
    count = max(1, min(int(per_tick or _env_int("LUXEFINDER_QUERY_PER_TICK", 1)), len(POC_QUERIES)))
    min_gap = max(15.0, float(interval_seconds or _env_float("LUXEFINDER_QUERY_MIN_GAP_SECONDS", 15.0)))
    now = time.monotonic()
    selected: list[str] = []
    with _QUERY_LOCK:
        if not _QUERY_ORDER or _QUERY_CURSOR >= len(_QUERY_ORDER):
            _QUERY_ORDER = list(POC_QUERIES)
            random.shuffle(_QUERY_ORDER)
            _QUERY_CURSOR = 0
        attempts = 0
        while len(selected) < count and attempts < len(POC_QUERIES):
            if _QUERY_CURSOR >= len(_QUERY_ORDER):
                _QUERY_ORDER = list(POC_QUERIES)
                random.shuffle(_QUERY_ORDER)
                _QUERY_CURSOR = 0
            query = _QUERY_ORDER[_QUERY_CURSOR]
            _QUERY_CURSOR += 1
            attempts += 1
            last = _QUERY_LAST_REQUEST_AT.get(query, 0.0)
            if now - last < min_gap:
                continue
            _QUERY_LAST_REQUEST_AT[query] = now
            selected.append(query)
    return selected


def scrape_daangn_query(query: str, *, stealth: bool, limit: int = 2) -> list[Any]:
    from collectors.daangn_spider import DaangnSpider

    configure_fetch_logging()
    if _log_fetches_enabled():
        print(f"[scrape] fetch daangn query={query!r}")
    daangn = DaangnSpider(stealth=stealth)
    try:
        return list(daangn.search(query, limit=max(1, min(int(limit), 5))))
    except Exception as exc:
        print(f"[scraper] error: daangn query failed query={query!r}: {exc}", file=sys.stderr)
        traceback.print_exc()
        time.sleep(random.uniform(5.0, 10.0))
        return []


def scrape_daangn_latest(*, stealth: bool, queries: Iterable[str] | None = None, limit: int = 2) -> Iterable[Any]:
    selected = list(queries) if queries is not None else next_queries()
    for query in selected:
        yield from scrape_daangn_query(query, stealth=stealth, limit=limit)


def handle_new_listing(
    raw: Any,
    *,
    state: Any,
    hub: Any,
    use_image_proxy: bool,
    settings_store: Any = None,
    public_api_base: str = "http://127.0.0.1:8001",
) -> bool:
    listing_id = _listing_id_from_raw(raw)
    with _SEEN_LOCK:
        if listing_id in _SEEN_LISTING_IDS or state.has_listing(listing_id):
            return False
        _SEEN_LISTING_IDS.add(listing_id)

    analysis = analyze_listing(raw, settings_store=settings_store)
    if not analysis.eligible:
        print(f"[scraper] included_ineligible reason={analysis.reasoning_short} id={listing_id}")

    listing = _base_listing_from_raw(raw, analysis, use_image_proxy=use_image_proxy)
    created = state.add_listing_front(listing)
    if not created:
        return False
    print(f"[scraper] new_listing id={listing['id']} brand={listing['brand']} title={listing['rawTitle'][:80]}")
    hub.publish_from_thread({"type": "new_listing", "id": listing["id"], "listing": listing})

    queries = _market_queries(listing)
    target = _market_target(listing)
    print(
        f"[market] target id={listing['id']} brand={target.brand} "
        f"model={target.model_name} groups={target.required_groups} queries={queries}"
    )
    market_timeout = _env_int("LUXEFINDER_MARKET_PLATFORM_TIMEOUT", 25)
    pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="market-compare-")
    futures = {pool.submit(_compare_one_platform, platform, queries, target): platform for platform in MARKET_PLATFORMS}
    completed: set[Any] = set()
    try:
        for fut in as_completed(futures, timeout=market_timeout):
            completed.add(fut)
            platform = futures[fut]
            try:
                quote = fut.result()
            except Exception:
                traceback.print_exc()
                quote = MarketQuote(platform, None, None, "error", 0, 0, status="failed", error="future failed")
            _publish_market_update(state, hub, listing["id"], quote)
    except FuturesTimeoutError:
        for fut, platform in futures.items():
            if fut in completed:
                continue
            quote = MarketQuote(
                platform,
                None,
                None,
                "timeout",
                0,
                0,
                status="failed",
                error=f"market compare timeout after {market_timeout}s",
            )
            _publish_market_update(state, hub, listing["id"], quote)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    final = _finalize_market(state, hub, listing)
    if final:
        print(
            "[scraper] market_final "
            f"id={final.get('id')} ref={final.get('reference_platform')} "
            f"price={final.get('reference_price_krw')} profit={final.get('expected_profit')}"
        )
        if final.get("reference_price_krw"):
            tg_status, tg_msg = _send_telegram_once(final, settings_store, public_api_base=public_api_base)
            _publish_telegram_status(state, hub, str(final["id"]), tg_status, tg_msg)
        else:
            print(f"[telegram] skipped id={final.get('id')} reason=no_reference_price")
            _publish_telegram_status(state, hub, str(final["id"]), "failed", "no_reference_price")
    return True


def run_scrape_cycle(
    *,
    image_proxy_prefix: str = "",
    use_image_proxy: bool,
    stealth: bool,
    state: Any | None = None,
    hub: Any | None = None,
    settings_store: Any = None,
    public_api_base: str = "http://127.0.0.1:8001",
    queries: list[str] | None = None,
    limit: int = 2,
    **_: Any,
) -> list[dict[str, Any]]:
    """Run one PoC polling pass. If state/hub are provided, process per listing immediately."""
    if not _env_bool("LUXEFINDER_SCRAPE", default=True):
        return _seed_listings()
    if state is None or hub is None:
        return []
    selected_queries = list(queries) if queries is not None else next_queries()
    for query in selected_queries:
        print(f"[scraper] tick query={query}")
        try:
            rows = scrape_daangn_query(query, stealth=stealth, limit=limit)
            print(f"[scraper] fetched count={len(rows)} query={query}")
        except Exception as exc:
            print(f"[scraper] error: tick fetch failed query={query}: {exc}", file=sys.stderr)
            traceback.print_exc()
            rows = []
        fetched_ids = [_listing_id_from_raw(raw) for raw in rows]
        with _SEEN_LOCK:
            seen_hits = sum(1 for listing_id in fetched_ids if listing_id in _SEEN_LISTING_IDS or state.has_listing(listing_id))
            new_ids = [
                listing_id
                for listing_id in fetched_ids
                if listing_id not in _SEEN_LISTING_IDS and not state.has_listing(listing_id)
            ]
        print(f"[scraper] fetched ids={fetched_ids}")
        print(f"[scraper] seen hits={seen_hits}")
        print(f"[scraper] new ids={new_ids}")
        new_count = 0
        for raw in rows:
            try:
                if handle_new_listing(
                    raw,
                    state=state,
                    hub=hub,
                    use_image_proxy=use_image_proxy,
                    settings_store=settings_store,
                    public_api_base=public_api_base or image_proxy_prefix,
                ):
                    new_count += 1
            except Exception as exc:
                print(f"[scraper] error: listing handling failed query={query}: {exc}", file=sys.stderr)
                traceback.print_exc()
        print(f"[scraper] new count={new_count} query={query}")
    return state.snapshot()


def start_background_scraper(
    *,
    interval_sec: float,
    state: Any,
    hub: Any,
    image_proxy_prefix: str,
    use_image_proxy: bool,
    stealth: bool,
    settings_store: Any = None,
    public_api_base: str = "http://127.0.0.1:8001",
) -> None:
    """Start a 1-2s polling loop that fetches one query per tick."""
    global _BACKGROUND_STARTED, _BACKGROUND_THREAD
    configure_fetch_logging()
    with _BACKGROUND_LOCK:
        if _BACKGROUND_STARTED:
            print("[scraper] started")
            return
        _BACKGROUND_STOP_EVENT.clear()
        _BACKGROUND_STARTED = True

    _ = interval_sec
    pub = (public_api_base or image_proxy_prefix or "http://127.0.0.1:8001").rstrip("/")
    if _env_bool("LUXEFINDER_CLEAR_SEEN_ON_START", default=False):
        clear_seen_listing_ids()

    def _loop() -> None:
        while not _BACKGROUND_STOP_EVENT.is_set():
            try:
                run_scrape_cycle(
                    image_proxy_prefix=image_proxy_prefix,
                    use_image_proxy=use_image_proxy,
                    stealth=stealth,
                    state=state,
                    hub=hub,
                    settings_store=settings_store,
                    public_api_base=pub,
                    limit=_env_int("LUXEFINDER_DAANGN_PER_QUERY", 2),
                )
            except Exception as exc:
                if _BACKGROUND_STOP_EVENT.is_set():
                    break
                print(f"[scraper] error: background loop failed: {exc}", file=sys.stderr)
                traceback.print_exc()
                if _BACKGROUND_STOP_EVENT.wait(random.uniform(5.0, 10.0)):
                    break
            if _BACKGROUND_STOP_EVENT.wait(random.uniform(2.5, 4.5)):
                break

    t = threading.Thread(target=_loop, name="poc-realtime-scraper", daemon=False)
    _BACKGROUND_THREAD = t
    t.start()
    print("[scraper] started")


def stop_background_scraper(timeout: float = 3.0) -> None:
    """Signal the background scraper to stop and wait briefly for it."""
    global _BACKGROUND_STARTED, _BACKGROUND_THREAD
    with _BACKGROUND_LOCK:
        thread = _BACKGROUND_THREAD
        if not _BACKGROUND_STARTED and thread is None:
            return
        _BACKGROUND_STOP_EVENT.set()

    if thread is not None and thread.is_alive():
        thread.join(timeout=max(0.1, float(timeout)))

    with _BACKGROUND_LOCK:
        if _BACKGROUND_THREAD is thread and (thread is None or not thread.is_alive()):
            _BACKGROUND_THREAD = None
            _BACKGROUND_STARTED = False

"""PoC realtime scraper: Daangn one listing -> analysis -> market compare -> Telegram."""

from __future__ import annotations

import os
import base64
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

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

POC_BRANDS: tuple[str, ...] = ("샤넬", "루이비통", "구찌")
POC_QUERIES: tuple[str, ...] = tuple(q for b in POC_BRANDS for q in (f"{b} 가방", f"{b} 핸드백"))
DAANGN_MIN_PRICE_BY_BRAND: dict[str, int] = {
    "샤넬": 800_000,
    "루이비통": 300_000,
    "구찌": 250_000,
}
MODEL_MAP: dict[str, tuple[str, str]] = {
    "클미": ("샤넬", "샤넬 클래식 미디움 플랩백"),
    "클래식 미디움": ("샤넬", "샤넬 클래식 미디움 플랩백"),
    "클래식 미듐": ("샤넬", "샤넬 클래식 미디움 플랩백"),
    "클래식 플랩": ("샤넬", "샤넬 클래식 플랩백"),
    "보이백": ("샤넬", "샤넬 보이백"),
    "보이 백": ("샤넬", "샤넬 보이백"),
    "woc": ("샤넬", "샤넬 월렛 온 체인"),
    "월렛온체인": ("샤넬", "샤넬 월렛 온 체인"),
    "가브리엘 호보": ("샤넬", "샤넬 가브리엘 호보백"),
    "gabrielle hobo": ("샤넬", "샤넬 가브리엘 호보백"),
    "22백": ("샤넬", "샤넬 22백"),
    "22 백": ("샤넬", "샤넬 22백"),
    "퀼팅 클러치": ("샤넬", "샤넬 퀼팅 클러치"),
    "크루즈립틱": ("샤넬", "샤넬 크루즈 립스틱백"),
    "립틱백": ("샤넬", "샤넬 크루즈 립스틱백"),
    "마몬트": ("구찌", "구찌 GG 마몬트 숄더백"),
    "gg 마몬트": ("구찌", "구찌 GG 마몬트 숄더백"),
    "구찌마몬트": ("구찌", "구찌 GG 마몬트 숄더백"),
    "오피디아": ("구찌", "구찌 오피디아 GG 미니 버킷백"),
    "ophidia": ("구찌", "구찌 오피디아 GG 미니 버킷백"),
    "홀스빗 미니": ("구찌", "구찌 홀스빗 1955 미니백"),
    "horsebit mini": ("구찌", "구찌 홀스빗 1955 미니백"),
    "패드락 탑": ("구찌", "구찌 패드락 탑 핸들백"),
    "패드락 탑핸들": ("구찌", "구찌 패드락 탑 핸들백"),
    "패드락 탑 핸드백": ("구찌", "구찌 패드락 탑 핸들백"),
    "padlock top": ("구찌", "구찌 패드락 탑 핸들백"),
    "패드락": ("구찌", "구찌 패드락 숄더백"),
    "패들락": ("구찌", "구찌 패드락 숄더백"),
    "디오니소스": ("구찌", "구찌 디오니소스 숄더백"),
    "홀스빗": ("구찌", "구찌 홀스빗 1955"),
    "소호테슬": ("구찌", "구찌 소호 태슬 크로스백"),
    "소호 테슬": ("구찌", "구찌 소호 태슬 크로스백"),
    "미니탑핸들": ("구찌", "구찌 미니 탑핸들백"),
    "미니 탑핸들": ("구찌", "구찌 미니 탑핸들백"),
    "재키": ("구찌", "구찌 재키 1961"),
    "네버풀": ("루이비통", "루이비통 네버풀 MM"),
    "neverfull": ("루이비통", "루이비통 네버풀 MM"),
    "스피디": ("루이비통", "루이비통 스피디 25"),
    "speedy": ("루이비통", "루이비통 스피디 25"),
    "온더고": ("루이비통", "루이비통 온더고 MM"),
    "onthego": ("루이비통", "루이비통 온더고 MM"),
    "알마": ("루이비통", "루이비통 알마 BB"),
    "알마 bb": ("루이비통", "루이비통 알마 BB"),
    "포쉐트메티스": ("루이비통", "루이비통 포쉐트 메티스"),
    "포쉐트 메티스": ("루이비통", "루이비통 포쉐트 메티스"),
    "튀렌": ("루이비통", "루이비통 튀렌 PM"),
    "몽테뉴": ("루이비통", "루이비통 몽테뉴 GM"),
    "쁘띠뜨 팔레": ("루이비통", "루이비통 쁘띠뜨 팔레"),
    "쁘띠 팔레": ("루이비통", "루이비통 쁘띠뜨 팔레"),
    "도빌": ("루이비통", "루이비통 도빌"),
    "트위스트": ("루이비통", "루이비통 트위스트"),
    "딜라이트풀": ("루이비통", "루이비통 딜라이트풀"),
    "메신저백": ("루이비통", "루이비통 메신저백"),
    "메신저 백": ("루이비통", "루이비통 메신저백"),
    "미니 부아뜨 샤포": ("루이비통", "루이비통 미니 부아뜨 샤포"),
    "부아뜨 샤포": ("루이비통", "루이비통 부아뜨 샤포"),
    "알파 웨어러블 월릿": ("루이비통", "루이비통 알파 웨어러블 월릿"),
    "알파 웨어러블": ("루이비통", "루이비통 알파 웨어러블 월릿"),
}
MARKET_PLATFORMS: tuple[str, ...] = ("daangn", "bunjang", "feelway", "gugus")
PLATFORM_PRICE_KEYS: dict[str, str] = {
    "daangn": "daangn_market_lowest_krw",
    "bunjang": "bunjang_lowest_krw",
    "feelway": "feelway_lowest_krw",
    "gugus": "gogoose_lowest_krw",
}
PLATFORM_LINK_KEYS: dict[str, str] = {
    "daangn": "daangn_market",
    "bunjang": "bunjang",
    "feelway": "feelway",
    "gugus": "gogoose",
}
MARKET_MATCH_VERSION = "sold-active-kr-gugus-bunjang-daangn-query-soft-v10"
GRADE_RANK = {"S": 3, "A": 2, "B": 1, "C": 0}
SOLD_KEYWORDS = (
    "거래완료",
    "판매완료",
    "판매 완료",
    "완료",
    "판매됨",
    "sold",
    "sold_out",
    "sold out",
    "closed",
)
ACTIVE_KEYWORDS = ("판매중", "판매 중", "selling", "ongoing", "in stock", "instock")
NOT_ACTIVE_KEYWORDS = ("거래진행중", "예약중", "예약 완료", "reserved")

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
_LLM_CACHE_LOCK = threading.Lock()
_LLM_CACHE_LOADED = False
_LLM_CACHE: dict[str, dict[str, Any]] = {}
_LLM_CACHE_PATH = _ROOT / "data" / "llm_cache.json"
_LLM_CIRCUIT_LOCK = threading.Lock()
_LLM_COOLDOWN_UNTIL = 0.0
_LLM_LAST_CIRCUIT_LOG_UNTIL = 0.0
_MARKET_CACHE_LOCK = threading.Lock()
_MARKET_CACHE_LOADED = False
_MARKET_CACHE: dict[str, dict[str, Any]] = {}
_MARKET_CACHE_PATH = _ROOT / "data" / "market_cache.json"


class GeminiRequestError(RuntimeError):
    def __init__(self, *, status: int | None, model: str, reason: str) -> None:
        self.status = status
        self.model = model
        self.reason = reason
        status_label = status if status is not None else "network"
        super().__init__(f"status={status_label} model={model} reason={reason}")


class GeminiCircuitOpen(RuntimeError):
    pass


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
    basis_type: str = ""
    sold_price: int | None = None
    sold_price_text: str = ""
    sold_url: str | None = None
    sold_source_title: str = ""
    active_price: int | None = None
    active_price_text: str = ""
    active_url: str | None = None
    active_source_title: str = ""


@dataclass(frozen=True)
class MarketTarget:
    brand: str
    model_name: str
    raw_title: str
    required_groups: tuple[tuple[str, ...], ...]

    @property
    def matchable(self) -> bool:
        return bool(self.brand and self.model_name)


def _market_cache_key(model_name: str) -> str:
    return _norm_match_text(model_name)


def _load_market_cache_unlocked() -> None:
    global _MARKET_CACHE_LOADED, _MARKET_CACHE
    if _MARKET_CACHE_LOADED:
        return
    _MARKET_CACHE_LOADED = True
    if not _MARKET_CACHE_PATH.is_file():
        return
    try:
        data = json.loads(_MARKET_CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _MARKET_CACHE = {str(k): v for k, v in data.items() if isinstance(v, dict)}
    except (OSError, json.JSONDecodeError, TypeError):
        _MARKET_CACHE = {}


def _market_quote_to_cache(quote: MarketQuote) -> dict[str, Any]:
    return {
        "platform": quote.platform,
        "price": quote.price,
        "url": quote.url,
        "basis": quote.basis,
        "sold_count": quote.sold_count,
        "sample_count": quote.sample_count,
        "price_text": quote.price_text,
        "source_title": quote.source_title,
        "fetched_at": quote.fetched_at,
        "status": quote.status,
        "error": quote.error,
        "basis_type": quote.basis_type,
        "sold_price": quote.sold_price,
        "sold_price_text": quote.sold_price_text,
        "sold_url": quote.sold_url,
        "sold_source_title": quote.sold_source_title,
        "active_price": quote.active_price,
        "active_price_text": quote.active_price_text,
        "active_url": quote.active_url,
        "active_source_title": quote.active_source_title,
        "match_version": MARKET_MATCH_VERSION,
        "cached_at": _utc_collected_iso(),
    }


def _market_quote_from_cache(platform: str, data: dict[str, Any]) -> MarketQuote | None:
    if not isinstance(data, dict):
        return None
    if str(data.get("match_version") or "") != MARKET_MATCH_VERSION:
        return None
    try:
        return MarketQuote(
            platform=str(data.get("platform") or platform),
            price=_coerce_market_price(data.get("price")),
            url=str(data.get("url") or "") or None,
            basis=str(data.get("basis") or "cache"),
            sold_count=int(data.get("sold_count") or 0),
            sample_count=int(data.get("sample_count") or 0),
            price_text=str(data.get("price_text") or ""),
            source_title=str(data.get("source_title") or ""),
            fetched_at=str(data.get("fetched_at") or data.get("cached_at") or ""),
            status=str(data.get("status") or "ok"),
            error=str(data.get("error") or ""),
            basis_type=str(data.get("basis_type") or ""),
            sold_price=_coerce_market_price(data.get("sold_price")),
            sold_price_text=str(data.get("sold_price_text") or ""),
            sold_url=str(data.get("sold_url") or "") or None,
            sold_source_title=str(data.get("sold_source_title") or ""),
            active_price=_coerce_market_price(data.get("active_price")),
            active_price_text=str(data.get("active_price_text") or ""),
            active_url=str(data.get("active_url") or "") or None,
            active_source_title=str(data.get("active_source_title") or ""),
        )
    except (TypeError, ValueError):
        return None


def _market_cache_get(model_name: str, platform: str) -> MarketQuote | None:
    key = _market_cache_key(model_name)
    if not key:
        return None
    with _MARKET_CACHE_LOCK:
        _load_market_cache_unlocked()
        by_platform = _MARKET_CACHE.get(key)
        if not isinstance(by_platform, dict):
            return None
        data = by_platform.get(platform)
        quote = _market_quote_from_cache(platform, data) if isinstance(data, dict) else None
    if quote is not None:
        if quote.status == "failed" or not quote.price:
            return None
        print(f"[market] cache hit model={model_name} platform={platform}")
    return quote


def _market_cache_set(model_name: str, quote: MarketQuote) -> None:
    if quote.status == "failed" or not quote.price:
        return
    key = _market_cache_key(model_name)
    if not key:
        return
    with _MARKET_CACHE_LOCK:
        _load_market_cache_unlocked()
        bucket = _MARKET_CACHE.setdefault(key, {})
        bucket[quote.platform] = _market_quote_to_cache(quote)
        try:
            _MARKET_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = _MARKET_CACHE_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(_MARKET_CACHE, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(_MARKET_CACHE_PATH)
        except OSError as exc:
            print(f"[market] cache write failed reason={exc.__class__.__name__}", file=sys.stderr)


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


_MARKET_LISTING_SEMAPHORE = threading.BoundedSemaphore(
    max(1, _env_int("LUXEFINDER_MARKET_LISTING_WORKERS", 2))
)


def _llm_cooldown_seconds() -> float:
    return max(60.0, _env_float("LUXEFINDER_LLM_COOLDOWN_SECONDS", 600.0))


def _llm_until_label(until: float) -> str:
    return datetime.fromtimestamp(until, timezone.utc).isoformat().replace("+00:00", "Z")


def _log_llm_circuit(until: float, *, reason: str = "cooldown", model: str = "") -> None:
    global _LLM_LAST_CIRCUIT_LOG_UNTIL
    with _LLM_CIRCUIT_LOCK:
        if until <= _LLM_LAST_CIRCUIT_LOG_UNTIL:
            return
        _LLM_LAST_CIRCUIT_LOG_UNTIL = until
    extra = f" reason={reason}"
    if model:
        extra += f" model={model}"
    print(f"[llm] circuit open: cooldown until {_llm_until_label(until)}{extra}", file=sys.stderr)


def _open_llm_circuit(*, model: str, reason: str) -> None:
    global _LLM_COOLDOWN_UNTIL
    until = time.time() + _llm_cooldown_seconds()
    with _LLM_CIRCUIT_LOCK:
        _LLM_COOLDOWN_UNTIL = max(_LLM_COOLDOWN_UNTIL, until)
        active_until = _LLM_COOLDOWN_UNTIL
    _log_llm_circuit(active_until, reason=reason, model=model)


def _llm_circuit_open() -> bool:
    with _LLM_CIRCUIT_LOCK:
        until = _LLM_COOLDOWN_UNTIL
    if time.time() < until:
        _log_llm_circuit(until)
        return True
    return False


def _llm_cache_key(title: str, description: str, brand: str) -> str:
    payload = json.dumps(
        {
            "brand": brand or "",
            "description": description or "",
            "title": title or "",
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_llm_cache_unlocked() -> None:
    global _LLM_CACHE_LOADED, _LLM_CACHE
    if _LLM_CACHE_LOADED:
        return
    _LLM_CACHE_LOADED = True
    if not _LLM_CACHE_PATH.is_file():
        return
    try:
        data = json.loads(_LLM_CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _LLM_CACHE = {str(k): v for k, v in data.items() if isinstance(v, dict)}
    except (OSError, json.JSONDecodeError, TypeError):
        _LLM_CACHE = {}


def _llm_cache_get(title: str, description: str, brand: str) -> dict[str, Any] | None:
    key = _llm_cache_key(title, description, brand)
    with _LLM_CACHE_LOCK:
        _load_llm_cache_unlocked()
        cached = _LLM_CACHE.get(key)
        return dict(cached) if isinstance(cached, dict) else None


def _llm_cache_set(title: str, description: str, brand: str, data: dict[str, Any]) -> None:
    key = _llm_cache_key(title, description, brand)
    with _LLM_CACHE_LOCK:
        _load_llm_cache_unlocked()
        _LLM_CACHE[key] = {
            "brand": str(data.get("brand") or brand or ""),
            "condition_grade": str(data.get("condition_grade") or ""),
            "has_authenticity_proof": bool(data.get("has_authenticity_proof")),
            "model_name": str(data.get("model_name") or data.get("normalized_model_name") or ""),
            "normalized_model_name": str(data.get("normalized_model_name") or data.get("model_name") or ""),
            "reasoning_short": str(data.get("reasoning_short") or "")[:160],
            "cached_at": _utc_collected_iso(),
        }
        try:
            _LLM_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = _LLM_CACHE_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(_LLM_CACHE, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(_LLM_CACHE_PATH)
        except OSError as exc:
            print(f"[llm] cache write failed reason={exc.__class__.__name__}", file=sys.stderr)


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
    blob = text or ""
    if re.search(r"가품|짝퉁|레플리카|레플|정품\s*아니|정품은\s*아니", blob, re.I):
        return False
    explicit = (
        r"보증서|개런티|게런티|영수증|구매\s*영수증|구매내역|인보이스|정품카드|authentic|receipt|invoice"
    )
    purchase_context = (
        r"정품|백화점|현대\s*구매|현대백화점|신세계|롯데\s*백화점|롯백|공홈|공식\s*홈|매장\s*구매|"
        r"구매\s*했|구입\s*했|직접\s*구매|풀구성|구성품|박스|더스트백|쇼핑백|택까지"
    )
    return bool(re.search(explicit, blob, re.I) or re.search(purchase_context, blob, re.I))


def _explicitly_missing_authenticity_proof(text: str) -> bool:
    blob = text or ""
    return bool(
        re.search(
            r"(보증서|개런티|게런티|영수증|인보이스|구성품|박스|더스트백|쇼핑백|부속품).{0,12}"
            r"(없|분실|없습|없어|없네|없고)",
            blob,
            re.I,
        )
    )


def _looks_like_bag(text: str) -> bool:
    return bool(
        re.search(
            r"가방|백|핸드백|숄더|토트|크로스백|클러치|버킷|호보|미니백|체인백|파우치|"
            r"bag|handbag|tote|shoulder|crossbody|clutch|hobo|bucket",
            text or "",
            re.I,
        )
    )


_NON_BAG_RE = re.compile(
    r"뷰티|화장품|향수|립스틱|립밤|립틴트|크림|핸드\s*크림|세럼|파우더|쿠션|"
    r"와펜|브로치|키링|키홀더|키체인|참\b|스카프|넥\s*보우|넥보우|실크\s*넥|"
    r"더스트백|쇼핑백|박스만|빈\s*박스|구성품만|이너백|스트랩만",
    re.I,
)
_BAG_MODEL_RE = re.compile(
    r"포쉐트\s*메티스|포쉐트메티스|튀렌|몽테뉴|알마|도빌|트위스트|딜라이트풀|"
    r"네버풀|스피디|온더고|부아뜨|부아트|보아트|샤포|보이백|가브리엘|호보|"
    r"패드락|패들락|오피디아|홀스빗|마몬트|소호|재키|클래식|플랩|"
    r"pochette\s*metis|alma|neverfull|speedy|onthego|boite|chapeau|boy\s*bag|gabrielle|hobo|padlock|ophidia|horsebit|marmont",
    re.I,
)
_OTHER_BRAND_RE = re.compile(
    r"생로랑|입생로랑|ysl|프라다|디올|셀린|보테가|고야드|에르메스|버버리|발렌시아가|"
    r"saint\s*laurent|prada|dior|celine|bottega|goyard|hermes|burberry|balenciaga",
    re.I,
)
_FAKE_OR_LOW_VALUE_RE = re.compile(
    r"가품|짝퉁|레플리카|레플\b|이미테이션|정품\s*아니|정품은\s*아니|"
    r"st급|s급\s*레플|미러급|커스텀급|스타일|st\s*style|"
    r"키링|참\b|와펜|브로치|스카프|더스트백|쇼핑백|박스만|구성품만|이너백|스트랩만",
    re.I,
)


def _is_bag_collection_candidate(raw: Any) -> bool:
    title = str(getattr(raw, "model_name", "") or getattr(raw, "source_title", "") or "")
    desc = str(getattr(raw, "description_text", "") or "")
    text = f"{title} {desc}"
    if _NON_BAG_RE.search(title):
        return False
    if _OTHER_BRAND_RE.search(title) and not _detect_brand(title):
        return False
    return bool(_looks_like_bag(text) or _BAG_MODEL_RE.search(text))


def _min_daangn_price_for_brand(brand: str) -> int:
    env_key = f"LUXEFINDER_MIN_DAANGN_PRICE_{brand}"
    return max(0, _env_int(env_key, DAANGN_MIN_PRICE_BY_BRAND.get(brand, 300_000)))


def _is_reasonable_daangn_sale_candidate(raw: Any, analysis: ListingAnalysis) -> tuple[bool, str]:
    price = int(getattr(raw, "price_krw", 0) or 0)
    title = str(getattr(raw, "model_name", "") or getattr(raw, "source_title", "") or "")
    desc = str(getattr(raw, "description_text", "") or "")
    blob = f"{title} {desc}"
    if _FAKE_OR_LOW_VALUE_RE.search(blob):
        return False, "가품/부속품/저가 잡화 키워드"
    min_price = _min_daangn_price_for_brand(analysis.brand)
    if price < min_price:
        return False, f"판매가 비정상 저가({price:,}원 < {min_price:,}원)"
    return True, ""


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
    if _llm_circuit_open():
        raise GeminiCircuitOpen("cooldown")
    last: httpx.Response | None = None
    last_exc: Exception | None = None
    for model in _gemini_models():
        try:
            resp = client.post(_gemini_generate_url(api_key, model), json=payload)
        except httpx.HTTPError as exc:
            last_exc = exc
            print(f"[llm] request failed status=network model={model} reason={exc.__class__.__name__}", file=sys.stderr)
            continue
        if resp.status_code == 429:
            reason = "rate_limited"
            print(f"[llm] request failed status=429 model={model} reason={reason}", file=sys.stderr)
            _open_llm_circuit(model=model, reason=reason)
            raise GeminiRequestError(status=429, model=model, reason=reason)
        if resp.status_code == 404:
            last = resp
            print(f"[llm] request failed status=404 model={model} reason=model_not_found", file=sys.stderr)
            continue
        if resp.status_code < 400:
            return resp
        last = resp
        reason = resp.reason_phrase or "http_error"
        print(f"[llm] request failed status={resp.status_code} model={model} reason={reason}", file=sys.stderr)
        raise GeminiRequestError(status=resp.status_code, model=model, reason=reason)
    if last is None:
        if last_exc is not None:
            raise GeminiRequestError(status=None, model=_gemini_model(), reason=last_exc.__class__.__name__)
        raise RuntimeError("No Gemini model configured")
    raise GeminiRequestError(status=last.status_code, model=_gemini_model(), reason="model_not_found")


def _gemini_image_part(image_url: str) -> dict[str, Any] | None:
    url = (image_url or "").strip()
    if not url.startswith("http"):
        return None
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 LuxeFinder/0.1",
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                },
            )
        if resp.status_code >= 400:
            print(f"[llm] vision image fetch skipped status={resp.status_code} reason=http_error", file=sys.stderr)
            return None
        media_type = (resp.headers.get("content-type") or "image/jpeg").split(";", 1)[0].strip()
        if not media_type.startswith("image/"):
            return None
        if len(resp.content) > 4_000_000:
            print("[llm] vision image fetch skipped status=0 reason=image_too_large", file=sys.stderr)
            return None
        return {
            "inline_data": {
                "mime_type": media_type,
                "data": base64.b64encode(resp.content).decode("ascii"),
            }
        }
    except httpx.HTTPError as exc:
        print(f"[llm] vision image fetch skipped status=network reason={exc.__class__.__name__}", file=sys.stderr)
        return None


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
    cached = _llm_cache_get(title, description, brand)
    if cached:
        candidate = re.sub(
            r"\s+",
            " ",
            str(cached.get("model_name") or cached.get("normalized_model_name") or "").strip(),
        )
        return candidate if _model_name_is_clear(candidate, brand) else ""
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
        _llm_cache_set(title, description, brand, {"brand": brand, "model_name": candidate})
        return candidate[:180]
    except GeminiCircuitOpen:
        return ""
    except GeminiRequestError as exc:
        print(f"[llm] model-name extraction skipped status={exc.status} model={exc.model} reason={exc.reason}", file=sys.stderr)
        return ""
    except Exception as exc:
        print(f"[llm] model-name extraction failed reason={exc.__class__.__name__}", file=sys.stderr)
        return ""


def get_model_name(
    title: str,
    description: str = "",
    *,
    brand: str | None = None,
    api_key: str = "",
    allow_llm: bool = False,
) -> str:
    """Final model normalizer: MODEL_MAP rules first, LLM fallback second."""
    normalized = normalize_model(title, description, brand=brand)
    if normalized:
        return normalized
    detected_brand = _normalize_brand(brand or _detect_brand(f"{title} {description}") or "")
    blob = f"{title or ''} {description or ''}"
    if detected_brand and re.search(
        r"22백|퀼팅|크루즈|립틱|포쉐트|메티스|튀렌|몽테뉴|쁘띠|팔레|도빌|트위스트|딜라이트풀|"
        r"메신저|부아뜨|샤포|알파|웨어러블|월릿|소호|테슬|탑핸들|패드락|패들락|홀스빗|오피디아|마몬트|"
        r"가브리엘|보이백|알마|네버풀|스피디|온더고|neverfull|speedy|alma|marmont|ophidia|horsebit",
        blob,
        re.I,
    ):
        fallback = _fallback_model_name_from_title(title or description, detected_brand)
        if _model_name_is_clear(fallback, detected_brand):
            return fallback
    if not allow_llm:
        return ""
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
        print(f"[llm] analysis failed reason={exc.__class__.__name__}; using rule fallback", file=sys.stderr)
        return None


def _analysis_from_llm_data(title: str, desc: str, data: dict[str, Any], *, fallback_brand: str = "") -> ListingAnalysis:
    brand = _normalize_brand(str(data.get("brand") or fallback_brand or "").strip())
    if not brand:
        brand = _normalize_brand(_detect_brand(f"{title} {desc}") or "")
    normalized = str(data.get("normalized_model_name") or data.get("model_name") or "").strip()
    if normalized and brand and brand not in normalized:
        normalized = f"{brand} {normalized}".strip()
    if not _model_name_is_clear(normalized, brand):
        normalized = normalize_model(title, desc, brand=brand) or normalized
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
        reasoning_short=reasoning or "LLM analysis",
        eligible=eligible,
    )


def _llm_analyze_listing(raw: Any, *, api_key: str, rule_brand: str = "") -> ListingAnalysis | None:
    title = str(getattr(raw, "model_name", "") or "")
    desc = str(getattr(raw, "description_text", "") or "")
    brand_for_cache = _normalize_brand(rule_brand or _detect_brand(f"{title} {desc}") or "")
    if not api_key or not brand_for_cache or _llm_circuit_open():
        return None
    cached = _llm_cache_get(title, desc, brand_for_cache)
    if cached:
        return _analysis_from_llm_data(title, desc, cached, fallback_brand=brand_for_cache)
    system = (
        "You analyze Korean secondhand luxury bag listings for a PoC. "
        "Return only compact JSON with keys: brand, normalized_model_name, "
        "has_authenticity_proof, condition_grade, reasoning_short. "
        "Allowed brands are Chanel, Louis Vuitton, Gucci. Category must be bags only. "
        "condition_grade must be one of S,A,B,C. Be conservative: if model is unclear, "
        "return normalized_model_name as empty string; if proof is not explicit, false. "
        "Use both listing text and the image when an image is provided. Treat visible warranty cards, "
        "receipts, invoices, authenticity cards, boxes/cards with matching product proof as authenticity proof. "
        "Use the image to assist model-name and condition-grade judgment, but do not invent uncertain details."
    )
    user = f"TITLE:\n{title}\n\nDESCRIPTION:\n{desc[:3000]}"
    parts: list[dict[str, Any]] = [{"text": f"{system}\n\n{user}"}]
    image_part = _gemini_image_part(str(getattr(raw, "image_url", "") or ""))
    if image_part:
        parts.append(image_part)
    payload = {"contents": [{"parts": parts}]}
    try:
        with httpx.Client(timeout=18.0) as client:
            resp = _post_gemini_generate(client, api_key=api_key, payload=payload)
        payload = resp.json()
        content = payload["candidates"][0]["content"]["parts"][0]["text"]
        data = _parse_llm_json(content)
        if not data:
            return None
        if not str(data.get("brand") or "").strip():
            data["brand"] = brand_for_cache
        _llm_cache_set(title, desc, brand_for_cache, data)
        return _analysis_from_llm_data(title, desc, data, fallback_brand=brand_for_cache)
    except GeminiCircuitOpen:
        return None
    except GeminiRequestError as exc:
        print(f"[llm] analysis skipped status={exc.status} model={exc.model} reason={exc.reason}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"[llm] analysis failed reason={exc.__class__.__name__}; using rule fallback", file=sys.stderr)
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
    if GRADE_RANK.get(condition_grade, 0) < GRADE_RANK["B"]:
        return False
    if not _model_name_is_clear(normalized_model_name, brand):
        return False
    return True


def analyze_listing(raw: Any, *, settings_store: Any = None) -> ListingAnalysis:
    title = str(getattr(raw, "model_name", "") or "")
    desc = str(getattr(raw, "description_text", "") or "")
    blob = f"{title} {desc}"
    brand = _normalize_brand(_detect_brand(blob) or "")
    is_bag = _looks_like_bag(blob)
    proof = _has_authenticity_proof(blob)
    grade = _condition_grade(blob)
    normalized = get_model_name(title, desc, brand=brand)

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
    api_key = _settings_gemini_key(settings_store)
    ambiguous = bool(
        api_key
        and brand
        and is_bag
        and not eligible
        and (
            not proof
            or GRADE_RANK.get(grade, 0) < GRADE_RANK["A"]
            or not _model_name_is_clear(normalized, brand)
        )
    )
    if ambiguous:
        llm = _llm_analyze_listing(raw, api_key=api_key, rule_brand=brand)
        if llm is not None:
            return llm

    return ListingAnalysis(
        brand=brand,
        normalized_model_name=normalized,
        has_authenticity_proof=proof,
        condition_grade=grade,
        reasoning_short="; ".join(reasons)[:120],
        eligible=eligible,
    )


def _rule_analysis_from_raw(raw: Any) -> ListingAnalysis:
    title = str(getattr(raw, "model_name", "") or "")
    desc = str(getattr(raw, "description_text", "") or "")
    blob = f"{title} {desc}"
    brand = _normalize_brand(_detect_brand(blob) or "")
    is_bag = _looks_like_bag(blob)
    proof = _has_authenticity_proof(blob)
    grade = _condition_grade(blob)
    normalized = get_model_name(title, desc, brand=brand)
    eligible = _analysis_passes_filters(
        brand=brand,
        normalized_model_name=normalized,
        has_authenticity_proof=proof,
        condition_grade=grade,
        raw_text=blob,
    )
    reasons: list[str] = []
    if not brand:
        reasons.append("PoC target brand not matched")
    if not is_bag:
        reasons.append("bag keyword not matched")
    if not proof:
        reasons.append("authenticity proof not found")
    if GRADE_RANK.get(grade, 0) < GRADE_RANK["B"]:
        reasons.append(f"condition below B: {grade}")
    if not _model_name_is_clear(normalized, brand):
        reasons.append("model name unclear")
    if not reasons:
        reasons.append(f"{brand} bag, proof confirmed, condition {grade}")
    return ListingAnalysis(
        brand=brand,
        normalized_model_name=normalized,
        has_authenticity_proof=proof,
        condition_grade=grade,
        reasoning_short="; ".join(reasons)[:120],
        eligible=eligible,
    )


def _merge_rule_and_llm_analysis(raw: Any, rule: ListingAnalysis, llm: ListingAnalysis) -> ListingAnalysis:
    title = str(getattr(raw, "model_name", "") or "")
    desc = str(getattr(raw, "description_text", "") or "")
    blob = f"{title} {desc}"
    brand = llm.brand or rule.brand
    normalized = rule.normalized_model_name
    if not _model_name_is_clear(normalized, brand) and _model_name_is_clear(llm.normalized_model_name, brand):
        normalized = llm.normalized_model_name
    proof = bool(rule.has_authenticity_proof or llm.has_authenticity_proof)
    grade = llm.condition_grade if llm.condition_grade in GRADE_RANK else rule.condition_grade
    eligible = _analysis_passes_filters(
        brand=brand,
        normalized_model_name=normalized,
        has_authenticity_proof=proof,
        condition_grade=grade,
        raw_text=blob,
    )
    reasons: list[str] = []
    if not proof:
        reasons.append("authenticity proof not found")
    if GRADE_RANK.get(grade, 0) < GRADE_RANK["B"]:
        reasons.append(f"condition below B: {grade}")
    if not _model_name_is_clear(normalized, brand):
        reasons.append("model name unclear")
    if not reasons:
        reasons.append("text/image analysis merged")
    return ListingAnalysis(
        brand=brand,
        normalized_model_name=normalized,
        has_authenticity_proof=proof,
        condition_grade=grade,
        reasoning_short="; ".join(reasons)[:120],
        eligible=eligible,
    )


def analyze_listing(raw: Any, *, settings_store: Any = None) -> ListingAnalysis:
    rule = _rule_analysis_from_raw(raw)
    title = str(getattr(raw, "model_name", "") or "")
    desc = str(getattr(raw, "description_text", "") or "")
    image_url = str(getattr(raw, "image_url", "") or "").strip()
    api_key = _settings_gemini_key(settings_store)
    should_call_llm = bool(
        api_key
        and rule.brand
        and _looks_like_bag(f"{title} {desc}")
        and (image_url or not rule.eligible)
        and (
            image_url
            or not rule.has_authenticity_proof
            or GRADE_RANK.get(rule.condition_grade, 0) < GRADE_RANK["B"]
            or not _model_name_is_clear(rule.normalized_model_name, rule.brand)
        )
    )
    if should_call_llm:
        llm = _llm_analyze_listing(raw, api_key=api_key, rule_brand=rule.brand)
        if llm is not None:
            return _merge_rule_and_llm_analysis(raw, rule, llm)
    return rule


def _empty_platform_prices() -> dict[str, int]:
    return {
        "daangn_market_lowest_krw": 0,
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
    if "globalbunjang.com" in url.lower():
        return None
    return url if url.startswith("http") else None


def _market_item_text(item: Any) -> str:
    return " ".join(
        str(getattr(item, attr, "") or "")
        for attr in ("model_name", "status_text", "trade_state", "description_text")
    )


def _market_item_primary_text(item: Any) -> str:
    return " ".join(
        str(getattr(item, attr, "") or "")
        for attr in ("model_name", "source_title", "status_text", "trade_state")
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
    "월렛": ("월렛", "월릿", "wallet"),
    "wallet": ("월렛", "월릿", "wallet"),
    "체인": ("체인", "chain"),
    "gabrielle": ("가브리엘", "gabrielle"),
    "hobo": ("호보", "호보백", "hobo"),
    "호보백": ("호보", "호보백", "hobo"),
    "gg": ("gg",),
    "마몬트": ("마몬트", "marmont"),
    "오피디아": ("오피디아", "ophidia"),
    "ophidia": ("오피디아", "ophidia"),
    "패드락": ("패드락", "패들락", "padlock"),
    "디오니소스": ("디오니소스", "dionysus"),
    "홀스빗": ("홀스빗", "horsebit"),
    "재키": ("재키", "jackie"),
    "네버풀": ("네버풀", "neverfull"),
    "스피디": ("스피디", "speedy"),
    "온더고": ("온더고", "on the go", "onthego"),
    "알마": ("알마", "alma"),
    "포쉐트": ("포쉐트", "pochette"),
    "메티스": ("메티스", "metis"),
    "앙프렝뜨": ("앙프렝뜨", "앙프렝트", "앙프레뜨", "empreinte"),
    "alpha": ("알파", "alpha"),
    "wearable": ("웨어러블", "wearable"),
    "boite": ("부아뜨", "보아뜨", "부아트", "보아트", "boite"),
    "chapeau": ("샤포", "샤포백", "chapeau"),
    "petite": ("쁘띠뜨", "쁘띠", "petite"),
    "mini": ("미니", "스몰", "mini", "small"),
    "미니": ("미니", "스몰", "mini", "small"),
    "미니백": ("미니", "미니백", "스몰", "mini", "small"),
    "bucket": ("버킷", "버킷백", "bucket", "bucket bag", "bucketbag"),
    "버킷": ("버킷", "버킷백", "bucket", "bucket bag", "bucketbag"),
    "bb": ("bb", "비비"),
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
    "핸들백",
    "handbag",
    "bag",
    "백",
    "숄더백",
    "크로스백",
    "토트백",
    "체인백",
    "플랩백",
    "미니백",
    "탑핸들",
    "탑",
    "정품",
    "미사용",
    "새상품",
    "판매",
    "판매중",
    "판매합니다",
    "팝니다",
    "팔아요",
    "팔아용",
    "팔께요",
    "팔게요",
    "급처",
    "처분",
    "정리",
    "당일",
    "새상품",
    "중고",
    "명품",
    "상태",
    "구매",
    "영수증",
    "보증서",
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


_STRICT_MARKET_ATTRIBUTES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("에피", "epi"), ("에피", "epi")),
    (("모노그램", "monogram"), ("모노그램", "monogram")),
    (("다미에", "damier"), ("다미에", "damier")),
    (("앙프렝뜨", "앙프렝트", "empreinte"), ("앙프렝뜨", "앙프렝트", "empreinte")),
    (("캐비어", "caviar"), ("캐비어", "caviar")),
    (("램스킨", "lambskin"), ("램스킨", "lambskin")),
    (("블랙", "느와르", "누아르", "black", "noir"), ("블랙", "느와르", "누아르", "black", "noir")),
    (("화이트", "white", "blanc"), ("화이트", "white", "blanc")),
    (("브라운", "brown", "marron"), ("브라운", "brown", "marron")),
    (("베이지", "beige"), ("베이지", "beige")),
    (("금장", "골드", "gold", "ghw"), ("금장", "골드", "gold", "ghw")),
    (("은장", "실버", "silver", "shw"), ("은장", "실버", "silver", "shw")),
    (("탑핸들", "탑 핸들", "탑핸드", "top handle", "tophandle"), ("탑핸들", "탑 핸들", "탑핸드", "top handle", "tophandle")),
    (("호보", "호보백", "hobo"), ("호보", "호보백", "hobo")),
    (("버킷", "버킷백", "bucket"), ("버킷", "버킷백", "bucket")),
    (("패드락", "패들락", "padlock"), ("패드락", "패들락", "padlock")),
    (("오피디아", "ophidia"), ("오피디아", "ophidia")),
    (("홀스빗", "horsebit"), ("홀스빗", "horsebit")),
    (("보이백", "boy"), ("보이백", "boy")),
    (("가브리엘", "gabrielle"), ("가브리엘", "gabrielle")),
    (("수프림", "슈프림", "supreme"), ("수프림", "슈프림", "supreme")),
    (("캔버스", "canvas"), ("캔버스", "canvas")),
    (("숄더", "숄더백", "shoulder"), ("숄더", "숄더백", "shoulder")),
    (("체인", "chain"), ("체인", "chain")),
    (("부아뜨", "부아트", "보아트", "보이테", "boite"), ("부아뜨", "부아트", "보아트", "보이테", "boite")),
    (("샤포", "chapeau"), ("샤포", "chapeau")),
    (("미니", "mini"), ("미니", "mini")),
    (("스몰", "small"), ("스몰", "small")),
    (("미듐", "미디움", "medium"), ("미듐", "미디움", "medium")),
    (("라지", "large"), ("라지", "large")),
)
_SOFT_STRICT_ATTRIBUTE_ALIASES: set[str] = {
    "블랙", "느와르", "누아르", "black", "noir",
    "화이트", "white", "blanc",
    "브라운", "brown", "marron",
    "베이지", "beige",
    "금장", "골드", "gold", "ghw",
    "은장", "실버", "silver", "shw",
    "에피", "epi",
    "모노그램", "monogram",
    "다미에", "damier",
    "앙프렝뜨", "앙프렝트", "empreinte",
    "캐비어", "caviar",
    "램스킨", "lambskin",
    "캔버스", "canvas",
    "미니", "mini",
    "스몰", "small",
    "미듐", "미디움", "medium",
    "라지", "large",
}

_EXTRA_SUBMODEL_MARKERS: tuple[str, ...] = (
    "비스타",
    "bista",
    "dionysus",
    "디오니소스",
    "마몬트",
    "marmont",
    "소호",
    "soho",
    "재키",
    "jackie",
    "네버풀",
    "neverfull",
    "스피디",
    "speedy",
    "포쉐트",
    "pochette",
)

_STRICT_CONFLICT_GROUPS: tuple[tuple[str, ...], ...] = (
    ("에피", "모노그램", "다미에", "앙프렝뜨", "앙프렝트", "캐비어", "램스킨", "epi", "monogram", "damier", "empreinte", "caviar", "lambskin"),
    ("블랙", "화이트", "브라운", "베이지", "black", "white", "brown", "beige", "noir", "blanc", "marron"),
    ("금장", "은장", "골드", "실버", "gold", "silver", "ghw", "shw"),
    ("미니", "스몰", "미듐", "미디움", "라지", "mini", "small", "medium", "large"),
)


def _strict_market_attribute_groups(target: MarketTarget) -> tuple[tuple[str, ...], ...]:
    target_text = _norm_match_text(f"{target.model_name} {target.raw_title}")
    if any(_contains_alias(target_text, alias) for alias in ("패드락", "패들락", "padlock")):
        return tuple()
    groups: list[tuple[str, ...]] = []
    for triggers, required in _STRICT_MARKET_ATTRIBUTES:
        if any(alias in _SOFT_STRICT_ATTRIBUTE_ALIASES for alias in triggers):
            continue
        if any(_contains_alias(target_text, alias) for alias in triggers):
            groups.append(required)
    return tuple(dict.fromkeys(groups))


def _strict_attributes_ok(text: str, target: MarketTarget) -> bool:
    text_n = _norm_match_text(text)
    target_text = _norm_match_text(f"{target.model_name} {target.raw_title}")
    required_groups = _strict_market_attribute_groups(target)
    if not all(any(_contains_alias(text_n, alias) for alias in group) for group in required_groups):
        return False
    for conflict_group in _STRICT_CONFLICT_GROUPS:
        wanted = {alias for alias in conflict_group if _contains_alias(target_text, alias)}
        if not wanted:
            continue
        found = {alias for alias in conflict_group if _contains_alias(text_n, alias)}
        if found and not found.intersection(wanted):
            return False
    for marker in _EXTRA_SUBMODEL_MARKERS:
        if _contains_alias(text_n, marker) and not _contains_alias(target_text, marker):
            return False
    return True


def _enrich_market_model_name(model_name: str, raw_title: str) -> str:
    model = re.sub(r"\s+", " ", (model_name or "").strip())
    source = _norm_match_text(f"{model_name} {raw_title}")
    additions: list[str] = []
    if ("홀스빗" in source or "horsebit" in source) and ("미니" in source or "mini" in source):
        additions.extend(["1955", "미니백"])
    if ("패드락" in source or "패들락" in source or "padlock" in source) and (
        "탑" in source or "탑핸들" in source or "top" in source
    ):
        additions.append("탑 핸들백")
    if ("가브리엘" in source or "gabrielle" in source) and ("호보" in source or "hobo" in source):
        additions.append("호보백")
    for token in additions:
        if token and token not in model:
            model = f"{model} {token}".strip()
    return re.sub(r"\s+", " ", model).strip()


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
    if not _model_name_is_clear(model_name, brand) and brand:
        model_name = re.sub(r"\s+", " ", f"{brand} {raw_title}").strip()
    model_name = _enrich_market_model_name(model_name, raw_title)
    # Keep color/material variants out of the hard match. Market cards often omit
    # those details until the detail page, so making them mandatory drops real hits.
    groups = _required_model_groups(model_name, brand)
    return MarketTarget(brand=brand, model_name=model_name, raw_title=raw_title, required_groups=groups)


def _market_result_matches_target(item: Any, target: MarketTarget) -> bool:
    if not target.matchable:
        return False
    text = _norm_match_text(_market_item_text(item))
    primary_text = _norm_match_text(_market_item_primary_text(item))
    match_text = primary_text or text
    brand_ok = any(_contains_alias(match_text, alias) for alias in _BRAND_ALIASES.get(target.brand, (target.brand,)))
    if not brand_ok:
        return False
    if _has_conflicting_submodel(match_text, target):
        return False
    if not _strict_attributes_ok(match_text, target):
        return False
    if not target.required_groups:
        return True
    return all(any(_contains_alias(match_text, alias) for alias in group) for group in target.required_groups)


def _market_title_accuracy_ok(item: Any, target: MarketTarget) -> bool:
    title = str(getattr(item, "source_title", "") or getattr(item, "model_name", "") or "")
    text = _norm_match_text(title)
    if not text:
        return False
    target_text = _norm_match_text(f"{target.model_name} {target.raw_title}")
    if not target.required_groups:
        return any(_contains_alias(text, alias) for alias in _BRAND_ALIASES.get(target.brand, (target.brand,)))
    required_details: list[tuple[str, ...]] = []
    if any(_contains_alias(target_text, alias) for alias in ("미니", "mini")):
        required_details.append(("미니", "mini"))
    if any(_contains_alias(target_text, alias) for alias in ("탑", "탑핸들", "top handle", "top")):
        required_details.append(("탑", "탑핸들", "top handle", "top"))
    if any(_contains_alias(target_text, alias) for alias in ("호보", "호보백", "hobo")):
        required_details.append(("호보", "호보백", "hobo"))
    if required_details and not all(any(_contains_alias(text, alias) for alias in group) for group in required_details):
        return False
    brand_ok = any(_contains_alias(text, alias) for alias in _BRAND_ALIASES.get(target.brand, (target.brand,)))
    model_ok = bool(target.required_groups) and all(
        any(_contains_alias(text, alias) for alias in group)
        for group in target.required_groups
    )
    variant_keys = _variant_keys_in_text(f"{target.model_name} {target.raw_title}")
    variant_ok = False
    for key in variant_keys:
        aliases = _VARIANT_GROUPS.get(key, ())
        if aliases and any(_contains_alias(text, alias) for alias in aliases):
            variant_ok = True
            break
    if brand_ok and model_ok and not _has_conflicting_submodel(text, target) and _strict_attributes_ok(text, target):
        return True
    return False


def is_sold(item: Any) -> bool:
    """Return True only when a market result explicitly looks completed/sold."""
    text = _market_item_text(item).lower()
    return any(k.lower() in text for k in SOLD_KEYWORDS)


def is_active_listing(item: Any) -> bool:
    """Return True only for currently available/active sale results."""
    text = _market_item_text(item).lower()
    if is_sold(item):
        return False
    if any(k.lower() in text for k in NOT_ACTIVE_KEYWORDS):
        return False
    if any(k.lower() in text for k in ACTIVE_KEYWORDS):
        return True
    return False


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


def _active_items(items: Iterable[Any]) -> list[Any]:
    return [item for item in items if is_active_listing(item)]


def _active_fallback_items(items: Iterable[Any]) -> list[Any]:
    return _active_items(items)


def _lowest_price_item(priced: list[tuple[int, Any]]) -> tuple[int, Any]:
    return min(priced, key=lambda pair: pair[0])


def _realistic_reference_from_items(items: list[Any]) -> tuple[int | None, Any | None, str, int, int]:
    """
    Market reference rule:
    1. Use the lowest completed/sold price whenever sold samples exist.
    2. Otherwise keep the lowest active price as display-only fallback.
    """
    sold = filter_sold(items)
    sold_priced = _priced_items(sold)
    all_priced = _priced_items(items)
    if sold_priced:
        selected_price, selected_item = min(sold_priced, key=lambda pair: pair[0])
        return selected_price, selected_item, "sold_lowest_exact_item", len(sold_priced), len(all_priced)

    fallback_priced = _priced_items(_active_fallback_items(items))
    if not fallback_priced:
        return None, None, "no_reference", len(sold_priced), len(all_priced)
    ref, selected_item = _lowest_price_item(fallback_priced)
    return ref, selected_item, "active_fallback_lowest_item", len(sold_priced), len(all_priced)


def _platform_market_search_queries(platform: str, queries: Iterable[str]) -> list[str]:
    base_queries: list[str] = []
    for q in queries:
        cleaned = re.sub(r"\s+", " ", str(q or "")).strip()
        if cleaned and cleaned not in base_queries:
            base_queries.append(cleaned)

    search_queries: list[str] = list(base_queries)
    # Bunjang and Daangn expose completed-sale state in result payloads. Feelway
    # and Gugus treat completed-sale words as plain keywords, which produces
    # unrelated active rows and must not be mixed into sold/active comparison.
    if platform in {"bunjang", "daangn"}:
        for cleaned in base_queries:
            for suffix in ("거래완료", "판매완료", "sold"):
                sq = f"{cleaned} {suffix}".strip()
                if sq not in search_queries:
                    search_queries.append(sq)
    return search_queries[: _env_int("LUXEFINDER_MARKET_QUERY_LIMIT", 8)]


def _compare_one_platform(platform: str, queries: tuple[str, ...], target: MarketTarget) -> MarketQuote:
    from collectors.daangn_spider import DaangnSpider
    from collectors.bunjang_spider import BunjangSpider
    from collectors.feelway_spider import FeelwaySpider
    from collectors.gugus_spider import GugusSpider
    from collectors.base_collector import FetcherConfig

    spider_map = {
        "daangn": DaangnSpider,
        "bunjang": BunjangSpider,
        "feelway": FeelwaySpider,
        "gugus": GugusSpider,
    }
    print(f"[market] start platform={platform} target={target.model_name or target.raw_title}")
    try:
        if not target.matchable:
            print(f"[market] failed platform={platform} reason=model_unclear queries={queries}")
            return MarketQuote(platform, None, None, "model_unclear", 0, 0, status="failed", error="model_unclear")
        cached = _market_cache_get(target.model_name, platform)
        if cached is not None:
            return cached
        market_stealth = _env_bool("LUXEFINDER_MARKET_STEALTH", default=False)
        market_fetch_timeout = _env_int("LUXEFINDER_MARKET_FETCH_TIMEOUT_MS", 10_000)
        spider = spider_map[platform](
            stealth=market_stealth,
            fetcher_cfg=FetcherConfig(timeout=market_fetch_timeout, wait=500, network_idle=False),
        )
        rows: list[Any] = []
        seen_urls: set[str] = set()
        search_queries = _platform_market_search_queries(platform, queries or (target.model_name,))
        per_page_limit = _env_int("LUXEFINDER_MARKET_COMPARE_LIMIT", 20)
        max_pages = max(1, min(_env_int("LUXEFINDER_MARKET_MAX_PAGES", 1), 2))
        for query in search_queries:
            print(f"[market] search platform={platform} query={query}")
            for page in range(1, max_pages + 1):
                if platform == "daangn":
                    if page > 1:
                        batch = []
                    else:
                        batch = list(spider.search(query, only_on_sale=False, limit=per_page_limit))
                elif hasattr(spider, "search_page"):
                    batch = list(spider.search_page(query, page=page, limit=per_page_limit))
                else:
                    batch = list(spider.search(query, limit=per_page_limit))
                    if page > 1:
                        batch = []
                print(f"[market] platform={platform} query={query} page={page} results={len(batch)}")
                for row in batch:
                    key = _safe_listing_url(row) or str(getattr(row, "model_name", ""))
                    if key in seen_urls:
                        continue
                    seen_urls.add(key)
                    rows.append(row)
        matched_rows = [
            row for row in rows
            if _market_result_matches_target(row, target) and _market_title_accuracy_ok(row, target)
        ]
        for row in matched_rows:
            print(
                "[market] accepted "
                f"title={str(getattr(row, 'source_title', '') or getattr(row, 'model_name', ''))[:120]} "
                f"price={getattr(row, 'price_krw', None)}"
            )
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
            quote = MarketQuote(
                platform,
                None,
                None,
                "no_exact_model_match",
                0,
                len(rows),
                status="failed",
                error="no_exact_model_match",
            )
            _market_cache_set(target.model_name, quote)
            return quote
        sold_priced = _priced_items(filter_sold(matched_rows))
        active_priced = _priced_items(_active_items(matched_rows))
        all_priced = _priced_items(matched_rows)
        sold_price: int | None = None
        sold_selected = None
        active_price: int | None = None
        active_selected = None
        if sold_priced:
            sold_price, sold_selected = min(sold_priced, key=lambda pair: pair[0])
        if active_priced:
            active_price, active_selected = _lowest_price_item(active_priced)
        if sold_price is not None:
            price = sold_price
            selected = sold_selected
            basis = "sold_lowest_exact_item"
            basis_type = "sold"
        elif active_price is not None:
            price = active_price
            selected = active_selected
            basis = "active_fallback_lowest_item"
            basis_type = "active_fallback"
        else:
            price, selected, basis, _, _ = _realistic_reference_from_items(matched_rows)
            basis_type = "active_fallback" if price else "no_reference"
        sold_count = len(sold_priced)
        sample_count = len(all_priced)
        active_url = _safe_listing_url(active_selected) if active_selected is not None else None
        sold_url = _safe_listing_url(sold_selected) if sold_selected is not None else None
        quote = MarketQuote(
            platform,
            price,
            active_url,
            basis,
            sold_count,
            sample_count,
            price_text=str(getattr(selected, "price_text", "") or ""),
            source_title=str(getattr(selected, "source_title", "") or getattr(selected, "model_name", "") or ""),
            fetched_at=str(getattr(selected, "fetched_at", "") or ""),
            basis_type=basis_type,
            sold_price=sold_price,
            sold_price_text=str(getattr(sold_selected, "price_text", "") or ""),
            sold_url=sold_url,
            sold_source_title=str(getattr(sold_selected, "source_title", "") or getattr(sold_selected, "model_name", "") or ""),
            active_price=active_price,
            active_price_text=str(getattr(active_selected, "price_text", "") or ""),
            active_url=active_url,
            active_source_title=str(getattr(active_selected, "source_title", "") or getattr(active_selected, "model_name", "") or ""),
        )
        print(
            f"[market] done platform={platform} basis_type={quote.basis_type} "
            f"sold={quote.sold_price} active={quote.active_price} active_url={quote.active_url}"
        )
        _market_cache_set(target.model_name, quote)
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
    token_query = ""
    token_terms = [group[0] for group in target.required_groups if group and group[0]]
    if brand and token_terms:
        token_query = f"{brand} {' '.join(token_terms[:3])}"
    candidates = [exact, base, token_query, raw]
    for q in (exact,):
        if re.search(r"(?<![a-z0-9])bb(?![a-z0-9])", q, re.I):
            candidates.append(re.sub(r"(?<![a-z0-9])bb(?![a-z0-9])", "비비", q, flags=re.I))
        if "에피" in q:
            candidates.append(q.replace("에피", "에삐"))
        if "블랙" in q:
            candidates.append(q.replace("블랙", "느와르"))
    out: list[str] = []
    for q in candidates:
        cleaned = re.sub(r"\s+", " ", q).strip()[:120]
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return tuple(out)


def _publish_market_update(state: Any, hub: Any, listing_id: str, quote: MarketQuote) -> None:
    price_key = PLATFORM_PRICE_KEYS[quote.platform]
    link_key = PLATFORM_LINK_KEYS[quote.platform]
    basis_key = "gogoose" if quote.platform == "gugus" else quote.platform
    public_status = quote.status
    patch: dict[str, Any] = {
        "analysis_status": "market_update",
        "status": "시세확인중",
        "platform_prices": {price_key: int(quote.active_price or 0)},
        f"{link_key}_price": quote.active_price,
        f"{link_key}_price_text": quote.active_price_text,
        f"{link_key}_url": quote.active_url,
        f"{link_key}_sold_price": quote.sold_price,
        f"{link_key}_sold_price_text": quote.sold_price_text,
        f"{link_key}_sold_url": quote.sold_url,
        f"{link_key}_sold_basis_url": quote.sold_url,
        f"{link_key}_active_price": quote.active_price,
        f"{link_key}_active_price_text": quote.active_price_text,
        f"{link_key}_active_url": quote.active_url,
        "platform_basis": {
            basis_key: {
                "basis": quote.basis,
                "basis_type": quote.basis_type,
                "sold_count": quote.sold_count,
                "sample_count": quote.sample_count,
                "price": quote.price,
                "price_text": quote.price_text,
                "url": quote.active_url,
                "sold_price": quote.sold_price,
                "sold_price_text": quote.sold_price_text,
                "sold_url": quote.sold_url,
                "sold_basis_url": quote.sold_url,
                "sold_source_title": quote.sold_source_title,
                "active_price": quote.active_price,
                "active_price_text": quote.active_price_text,
                "active_url": quote.active_url,
                "active_source_title": quote.active_source_title,
                "source_title": quote.source_title,
                "fetched_at": quote.fetched_at,
                "status": public_status,
                "error": quote.error,
            }
        },
    }
    if quote.active_url and quote.platform != "daangn":
        patch["platformLinks"] = {link_key: quote.active_url}
    merged = state.merge_listing(listing_id, patch)
    if merged:
        print(
            f"[scraper] market_update id={listing_id} platform={link_key} "
            f"price={quote.price} basis={quote.basis} basis_type={quote.basis_type}"
        )
        if _env_bool("LUXEFINDER_PUBLISH_MARKET_UPDATES", default=False):
            hub.publish_from_thread(
                {
                    "type": "market_update",
                    "id": listing_id,
                    "platform": link_key,
                    "platform_name": link_key,
                    "price": quote.price,
                    "price_text": quote.price_text,
                    "url": quote.active_url,
                    "sold_price": quote.sold_price,
                    "sold_url": quote.sold_url,
                    "active_price": quote.active_price,
                    "active_url": quote.active_url,
                    "source_title": quote.source_title,
                    "fetched_at": quote.fetched_at,
                    "basis": quote.basis,
                    "basis_type": quote.basis_type,
                    "status": public_status,
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

    basis = latest.get("platform_basis") or {}
    basis_rows = {k: v for k, v in basis.items() if isinstance(v, dict)}
    sold_valid = {
        k: price
        for k, row in basis_rows.items()
        if isinstance((price := _coerce_market_price(row.get("sold_price"))), int) and price > 0
    }
    active_valid = {
        k: price
        for k, row in basis_rows.items()
        if isinstance((price := _coerce_market_price(row.get("active_price"))), int) and price > 0
    }
    price = int(latest.get("price") or 0)
    if sold_valid:
        source_platform, market_price = min(sold_valid.items(), key=lambda pair: pair[1])
        basis_type = "sold"
        fallback_used = False
    else:
        source_platform = None
        market_price = None
        basis_type = None
        fallback_used = False
    expected_profit = (int(market_price) - price) if market_price else 0
    arbitrage = round((expected_profit / market_price) * 100.0, 2) if market_price else 0.0

    patch = {
        "analysis_status": "market_final",
        "status": "완료",
        "marketPrice": market_price,
        "arbitrageRate": arbitrage,
        "expected_profit": expected_profit,
        "profit_rate": arbitrage,
        "best_resale_price": None,
        "best_resale_platform": None,
        "max_expected_profit": 0,
        "max_profit_rate": 0.0,
        "reference_platform": source_platform,
        "reference_price_krw": market_price,
        "market_reference_price": market_price,
        "market_reference_basis": basis_type,
        "market_reference_source": {
            "fallback_used": fallback_used,
            "basis_type": basis_type,
            "platform": source_platform,
            "platforms": list(sold_valid.keys()),
            "sold_platforms": list(sold_valid.keys()),
            "active_platforms": list(active_valid.keys()),
        },
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


def _process_market_for_listing(
    listing: dict[str, Any],
    *,
    state: Any,
    hub: Any,
    settings_store: Any = None,
    public_api_base: str = "http://127.0.0.1:8001",
) -> None:
    queries = _market_queries(listing)
    target = _market_target(listing)
    print(
        f"[market] target id={listing['id']} brand={target.brand} "
        f"model={target.model_name} groups={target.required_groups} queries={queries}"
    )
    market_timeout = _env_int("LUXEFINDER_MARKET_PLATFORM_TIMEOUT", 30)
    pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="market-compare-")
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
            if _passes_profit_filters(final, settings_store):
                tg_status, tg_msg = _send_telegram_once(final, settings_store, public_api_base=public_api_base)
                _publish_telegram_status(state, hub, str(final["id"]), tg_status, tg_msg)
            else:
                print(f"[telegram] skipped id={final.get('id')} reason=condition")
                _publish_telegram_status(state, hub, str(final["id"]), "skipped_condition", "profit filters not met")
        else:
            print(f"[telegram] skipped id={final.get('id')} reason=no_reference_price")
            _publish_telegram_status(state, hub, str(final["id"]), "failed", "no_reference_price")


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


def scrape_daangn_query(query: str, *, stealth: bool, limit: int = 1000) -> list[Any]:
    from collectors.daangn_spider import DaangnSpider

    configure_fetch_logging()
    if _log_fetches_enabled():
        print(f"[scrape] fetch daangn query={query!r}")
    daangn = DaangnSpider(stealth=stealth)
    try:
        return list(daangn.search(query, limit=max(1, int(limit))))
    except Exception as exc:
        print(f"[scraper] error: daangn query failed query={query!r}: {exc}", file=sys.stderr)
        traceback.print_exc()
        time.sleep(random.uniform(5.0, 10.0))
        return []


def scrape_daangn_latest(*, stealth: bool, queries: Iterable[str] | None = None, limit: int = 1000) -> Iterable[Any]:
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

    if not _is_bag_collection_candidate(raw):
        title = str(getattr(raw, "model_name", "") or getattr(raw, "source_title", "") or "")[:80]
        print(f"[scraper] skipped_non_bag id={listing_id} title={title}")
        return False

    analysis = analyze_listing(raw, settings_store=settings_store)
    reasonable, price_reason = _is_reasonable_daangn_sale_candidate(raw, analysis)
    if not reasonable:
        title = str(getattr(raw, "model_name", "") or getattr(raw, "source_title", "") or "")[:80]
        print(f"[scraper] skipped_unreasonable_price id={listing_id} reason={price_reason} title={title}")
        return False

    if not analysis.eligible:
        listing = _base_listing_from_raw(raw, analysis, use_image_proxy=use_image_proxy)
        listing.update(
            {
                "status": "excluded",
                "analysis_status": "excluded",
                "telegram_status": "skipped_excluded",
                "telegram_error": analysis.reasoning_short,
                "exclusion_reason": analysis.reasoning_short,
            }
        )
        created = state.add_listing_front(listing)
        print(f"[scraper] excluded id={listing_id} reason={analysis.reasoning_short}")
        if created:
            hub.publish_from_thread({"type": "excluded_listing", "id": listing["id"], "listing": listing})
        return created

    listing = _base_listing_from_raw(raw, analysis, use_image_proxy=use_image_proxy)
    created = state.add_listing_front(listing)
    if not created:
        return False
    print(f"[scraper] new_listing id={listing['id']} brand={listing['brand']} title={listing['rawTitle'][:80]}")
    _process_market_for_listing(
        listing=listing,
        state=state,
        hub=hub,
        settings_store=settings_store,
        public_api_base=public_api_base,
    )
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
    limit: int = 1000,
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

    sleep_seconds = max(1.0, float(interval_sec or 1.5))
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
                    limit=_env_int("LUXEFINDER_DAANGN_PER_QUERY", 1000),
                )
            except Exception as exc:
                if _BACKGROUND_STOP_EVENT.is_set():
                    break
                print(f"[scraper] error: background loop failed: {exc}", file=sys.stderr)
                traceback.print_exc()
                if _BACKGROUND_STOP_EVENT.wait(random.uniform(5.0, 10.0)):
                    break
            if _BACKGROUND_STOP_EVENT.wait(sleep_seconds):
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

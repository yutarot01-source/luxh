"""Scrapling 수집 주기 실행 (스레드에서 블로킹 I/O)."""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from api.settings_store import SettingsStore

# 프로젝트 루트 (LuxeFinder/) 를 path 에 추가
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def _seed_listings() -> list[dict[str, Any]]:
    """수집기 실패 시 대시보드 연동용 최소 시드."""
    _ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return [
        {
            "id": "seed-1",
            "brand": "샤넬",
            "rawTitle": "[시드] 샤넬 클래식 미듐 블랙",
            "normalizedModel": "[시드] 샤넬 클래식 미듐 블랙",
            "price": 8_900_000,
            "marketPrice": 12_350_000,
            "arbitrageRate": 27.94,
            "status_summary": "A급 전반 양호·영수증",
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
            "ai_status": {"warranty": True, "receipt": True, "condition_grade": "A"},
            "platform_prices": {
                "gogoose_lowest_krw": 12_400_000,
                "feelway_lowest_krw": 12_500_000,
                "bunjang_lowest_krw": 12_350_000,
            },
            "reference_platform": "bunjang",
            "reference_price_krw": 12_350_000,
            "collectedAt": _ts,
        }
    ]


GRADE_RANK = {"S": 3, "A": 2, "B": 1}


def _listing_meets_telegram_alert(row: dict[str, Any], cfg: Any) -> bool:
    """대시보드 필터(브랜드·실루엣·차익·등급·보증) + 텔레그램 전용 최소 예상 수익."""
    from api.listing_filters import listing_matches_selected_categories

    if not cfg.telegram_notifications_enabled:
        return False
    if not (cfg.telegram_bot_token and cfg.telegram_chat_id):
        return False
    thr = float(cfg.telegram_alert_threshold_percent or 0)
    rate = float(row.get("arbitrageRate") or 0)
    if rate < thr:
        return False
    ai = row.get("ai_status") or {}
    if cfg.require_warranty and not bool(ai.get("warranty")):
        return False
    g = str(ai.get("condition_grade") or "B").upper()
    min_g = str(cfg.min_grade or "B").upper()
    if GRADE_RANK.get(g, 1) < GRADE_RANK.get(min_g, 1):
        return False
    brands = list(cfg.selected_brands or [])
    if brands and row.get("brand") not in brands:
        return False
    min_profit = int(getattr(cfg, "telegram_min_expected_profit_krw", 0) or 0)
    if min_profit > 0:
        ep = row.get("expected_profit")
        if not isinstance(ep, (int, float)) or int(ep) < min_profit:
            return False
    cats = list(getattr(cfg, "selected_categories", None) or [])
    if not listing_matches_selected_categories(
        raw_title=str(row.get("rawTitle") or ""),
        normalized_model=str(row.get("normalizedModel") or ""),
        selected_ids=cats,
    ):
        return False
    return True


def _notify_new_listings(
    fresh_rows: list[dict[str, Any]],
    settings_store: SettingsStore | None,
    *,
    public_api_base: str,
) -> None:
    if not fresh_rows or settings_store is None:
        return
    from api.telegram_notify import send_listing_alert_telegram

    cfg = settings_store.snapshot()
    if not cfg.telegram_notifications_enabled:
        return
    token, chat = cfg.telegram_bot_token.strip(), cfg.telegram_chat_id.strip()
    if not token or not chat:
        return
    base = (public_api_base or "").rstrip("/")
    for row in fresh_rows:
        if not _listing_meets_telegram_alert(row, cfg):
            continue
        ok, msg = send_listing_alert_telegram(token, chat, row, public_api_base=base)
        if not ok:
            print(f"[telegram] id={row.get('id')}: {msg}", file=sys.stderr)


def run_scrape_cycle(
    *,
    image_proxy_prefix: str,
    use_image_proxy: bool,
    stealth: bool,
    queries: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    당근 검색 → MarketMatcher 시세 병합 → Listing dict 리스트.
    (각 당근 매물마다 ``enrich`` 가 **번개장터·구구스·필웨이** 스파이더를 호출해 시세·상세 URL을 붙입니다.)

    ``LUXEFINDER_SCRAPE=0`` 이면 시드만 반환.

    검색 쿼리는 ``api.brand_constants.build_daangn_bag_queries_scheduled`` 로 생성합니다.
    ``LUXEFINDER_SCRAPE_BRAND_BATCH`` 에 양의 정수를 주면 한 주기에 해당 개수의 브랜드만
    순환 검색해 부하를 나누고, 호출마다 오프셋이 진행되어 시간이 지나면 전 브랜드를 훑습니다.
    (미설정·0·브랜드 수 이상이면 매 주기 전 브랜드 × 가방/핸드백 접미 전부 검색.)
    """
    # 운영/데모에서 환경변수로 수집을 끄는 경우가 있는데,
    # "백엔드가 전혀 작동하지 않는다"로 보이지 않도록 로그를 남긴다.
    if not _env_bool("LUXEFINDER_SCRAPE", default=True):
        print("[scrape] LUXEFINDER_SCRAPE=0 → seed listings only")
        return _seed_listings()

    if queries is None:
        from api.brand_constants import build_daangn_bag_queries_scheduled

        queries = build_daangn_bag_queries_scheduled()

    try:
        from api.brand_constants import text_matches_catalog_brand

        from collectors.market_matcher import MarketMatcher
        from collectors.bunjang_spider import BunjangSpider
        from collectors.feelway_spider import FeelwaySpider
        from collectors.gugus_spider import GugusSpider

        from .listing_builder import enriched_to_listing_dict, raw_market_to_listing_dict

        mm = MarketMatcher(stealth=stealth)
        bj = BunjangSpider(stealth=stealth)
        fw = FeelwaySpider(stealth=stealth)
        gg = GugusSpider(stealth=stealth)
        out: list[dict[str, Any]] = []
        for q in queries:
            # 1) 당근(메인) + (번개/구구스/필웨이) 시세 매칭
            try:
                print(f"[scrape] [당근마켓] {q!r} 수집 중...")
                before = len(out)
                for enriched in mm.scan_brands_pipeline([q], per_query_limit=3):
                    blob = f"{enriched.daangn.model_name} {enriched.daangn.description_text}"
                    if text_matches_catalog_brand(blob) is None:
                        continue
                    row = enriched_to_listing_dict(
                        enriched,
                        use_image_proxy=use_image_proxy,
                        image_proxy_prefix=image_proxy_prefix,
                    )
                    if row.get("brand") == "기타":
                        continue
                    out.append(row)
                print(f"[scrape] [당근마켓] {q!r} 완료 (추가 {len(out)-before}건)")
            except Exception:
                traceback.print_exc()

            # 2) 번개장터(독립 피드)
            try:
                print(f"[scrape] [번개장터] {q!r} 수집 중...")
                rows = bj.search(q, limit=3)
                for r in rows:
                    out.append(
                        raw_market_to_listing_dict(
                            r,
                            platform="bunjang",
                            use_image_proxy=use_image_proxy,
                        )
                    )
                print(f"[scrape] [번개장터] {q!r} 완료 (성공 {len(rows)}건)")
            except Exception:
                traceback.print_exc()

            # 3) 필웨이(독립 피드)
            try:
                print(f"[scrape] [필웨이] {q!r} 수집 중...")
                rows = fw.search(q, limit=3)
                for r in rows:
                    out.append(
                        raw_market_to_listing_dict(
                            r,
                            platform="feelway",
                            use_image_proxy=use_image_proxy,
                        )
                    )
                print(f"[scrape] [필웨이] {q!r} 완료 (성공 {len(rows)}건)")
            except Exception:
                traceback.print_exc()

            # 4) 구구스(독립 피드; 실패해도 루프 지속)
            try:
                print(f"[scrape] [구구스] {q!r} 수집 중...")
                rows = gg.search(q, limit=3)
                for r in rows:
                    out.append(
                        raw_market_to_listing_dict(
                            r,
                            platform="gugus",
                            use_image_proxy=use_image_proxy,
                        )
                    )
                print(f"[scrape] [구구스] {q!r} 완료 (성공 {len(rows)}건)")
            except Exception:
                traceback.print_exc()

        if not out:
            return _seed_listings()
        return out
    except Exception:
        traceback.print_exc()
        return _seed_listings()


def start_background_scraper(
    *,
    interval_sec: float,
    state: Any,
    hub: Any,
    image_proxy_prefix: str,
    use_image_proxy: bool,
    stealth: bool,
    settings_store: SettingsStore | None = None,
) -> None:
    import threading
    import time

    def _loop() -> None:
        while True:
            time.sleep(interval_sec)
            try:
                before_ids = {x["id"] for x in state.snapshot()}
                rows = run_scrape_cycle(
                    image_proxy_prefix=image_proxy_prefix,
                    use_image_proxy=use_image_proxy,
                    stealth=stealth,
                )
                fresh = [x for x in rows if x["id"] not in before_ids]
                full = state.prepend(rows)
                _notify_new_listings(fresh, settings_store, public_api_base=image_proxy_prefix)
                hub.publish_from_thread({"type": "snapshot", "listings": full})
            except Exception:
                traceback.print_exc()

    t = threading.Thread(target=_loop, name="scraper", daemon=True)
    t.start()

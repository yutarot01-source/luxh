"""
1:1 실시간 파이프라인: 당근 매물 1건 포착 → 즉시 3사 시세(``asyncio`` 병렬 + 하이브리드) →
4사 비교·수익률 산출 → ``listing_ready`` SSE + 텔레그램 푸시.

- ``선 수집 후 비교`` 없음: 당근 검색 결과의 **각 행**마다 독립 워커가 곧바로 시세 태스크 실행.
- 타 플랫폼: ``collectors.hybrid_market.lowest_acceptable_hybrid`` (정적 우선 → 스텔스).
- 전체 SLA: ``LUXEFINDER_COMPARE_BUDGET_SEC`` (기본 5초) 안에 3사 ``asyncio.wait`` 병렬.
"""

from __future__ import annotations

import asyncio
import os
import traceback
from typing import Any

from collectors.models import DaangnEnrichedListing, RawListing

_ROOT_EXEC = None  # lazy: ThreadPoolExecutor for daangn-item workers


def _worker_pool() -> Any:
    global _ROOT_EXEC
    if _ROOT_EXEC is None:
        from concurrent.futures import ThreadPoolExecutor

        _ROOT_EXEC = ThreadPoolExecutor(max_workers=24, thread_name_prefix="rt-1to1-")
    return _ROOT_EXEC


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def _listing_url_or_none(item: RawListing | None) -> str | None:
    if item is None:
        return None
    u = (item.listing_url or "").strip()
    return u or None


async def _gather_three_lowest(query: str, budget: float) -> tuple[
    tuple[int | None, RawListing | None],
    tuple[int | None, RawListing | None],
    tuple[int | None, RawListing | None],
]:
    from collectors.bunjang_spider import BunjangSpider
    from collectors.feelway_spider import FeelwaySpider
    from collectors.gugus_spider import GugusSpider
    from collectors.hybrid_market import lowest_acceptable_hybrid

    t1 = asyncio.create_task(asyncio.to_thread(lowest_acceptable_hybrid, BunjangSpider, query))
    t2 = asyncio.create_task(asyncio.to_thread(lowest_acceptable_hybrid, FeelwaySpider, query))
    t3 = asyncio.create_task(asyncio.to_thread(lowest_acceptable_hybrid, GugusSpider, query))
    done, pending = await asyncio.wait([t1, t2, t3], timeout=budget)
    for p in pending:
        p.cancel()

    def _one(t: asyncio.Task) -> tuple[int | None, RawListing | None]:
        if t in done and not t.cancelled():
            try:
                return t.result()
            except Exception:
                traceback.print_exc()
        return None, None

    return _one(t1), _one(t2), _one(t3)


def _process_one_daangn_listing(
    raw: RawListing,
    *,
    state: Any,
    hub: Any,
    stealth: bool,
    use_image_proxy: bool,
    image_proxy_prefix: str,
    settings_store: Any,
    public_api_base: str,
) -> None:
    try:
        from api.brand_constants import text_matches_catalog_brand
        from api.listing_builder import enriched_to_listing_dict
        from api.scrape_service import _notify_new_listings

        blob = f"{raw.model_name} {raw.description_text}"
        matched_brand = text_matches_catalog_brand(blob)
        if matched_brand is None:
            return

        # 1:1 매칭 파이프라인은 "브랜드가 확인된 매물"에만 화력을 집중한다.
        # 시세 조회 쿼리에도 브랜드를 강제 포함해 잡동사니/오탐을 줄인다.
        base_title = (raw.model_name or "").strip()
        query = base_title
        if matched_brand and matched_brand.lower() not in base_title.lower():
            query = f"{matched_brand} {base_title}".strip()
        query = query[:120]
        if not query:
            return

        budget = float(os.environ.get("LUXEFINDER_COMPARE_BUDGET_SEC", "5") or "5")
        budget = max(1.5, min(budget, 15.0))

        try:
            (bj_p, bj_r), (fw_p, fw_r), (gg_p, gg_r) = asyncio.run(_gather_three_lowest(query, budget))
        except Exception:
            traceback.print_exc()
            bj_p, bj_r = None, None
            fw_p, fw_r = None, None
            gg_p, gg_r = None, None

        platform = {"bunjang": bj_p, "feelway": fw_p, "gugus": gg_p}
        urls = {
            "bunjang": _listing_url_or_none(bj_r),
            "feelway": _listing_url_or_none(fw_r),
            "gugus": _listing_url_or_none(gg_r),
        }
        priced = {k: v for k, v in platform.items() if isinstance(v, int) and v > 0}
        if priced:
            ref_platform = min(priced, key=lambda k: priced[k])
            market_price_krw = int(priced[ref_platform])
        else:
            ref_platform = None
            market_price_krw = None

        enriched = DaangnEnrichedListing(
            daangn=raw,
            market_price_krw=market_price_krw,
            platform_prices_krw=platform,
            reference_platform=ref_platform,
            platform_listing_urls=urls,
        )
        row = enriched_to_listing_dict(
            enriched,
            use_image_proxy=use_image_proxy,
            image_proxy_prefix=image_proxy_prefix,
        )
        if row.get("brand") == "기타":
            return

        state.add_listing_front(row)
        hub.publish_from_thread({"type": "listing_ready", "listing": row})
        _notify_new_listings([row], settings_store, public_api_base=public_api_base.rstrip("/"))
    except Exception:
        traceback.print_exc()


def run_incremental_cycle(
    *,
    image_proxy_prefix: str,
    use_image_proxy: bool,
    stealth: bool,
    state: Any,
    hub: Any,
    settings_store: Any = None,
    public_api_base: str = "http://127.0.0.1:8000",
    queries: list[str] | None = None,
) -> None:
    if not _env_bool("LUXEFINDER_SCRAPE", default=True):
        return

    from api.brand_constants import build_daangn_bag_queries_scheduled
    from collectors.daangn_spider import DaangnSpider

    if queries is None:
        queries = build_daangn_bag_queries_scheduled()

    daangn_limit = int(os.environ.get("LUXEFINDER_DAANGN_PER_QUERY", "10") or "10")
    daangn_limit = max(1, min(daangn_limit, 40))
    daangn = DaangnSpider(stealth=stealth)
    pub = (public_api_base or "").rstrip("/")

    for q in queries:
        try:
            items = daangn.search(q, limit=daangn_limit)
        except Exception:
            traceback.print_exc()
            continue
        for raw in items:
            if not isinstance(raw, RawListing):
                continue
            _worker_pool().submit(
                _process_one_daangn_listing,
                raw,
                state=state,
                hub=hub,
                stealth=stealth,
                use_image_proxy=use_image_proxy,
                image_proxy_prefix=image_proxy_prefix,
                settings_store=settings_store,
                public_api_base=pub,
            )


def start_incremental_background_loops(
    *,
    interval_sec: float,
    state: Any,
    hub: Any,
    image_proxy_prefix: str,
    use_image_proxy: bool,
    stealth: bool,
    settings_store: Any = None,
    public_api_base: str = "http://127.0.0.1:8000",
) -> None:
    import threading
    import time

    pub = (public_api_base or "").rstrip("/")

    def _loop() -> None:
        while True:
            time.sleep(interval_sec)
            try:
                run_incremental_cycle(
                    image_proxy_prefix=image_proxy_prefix,
                    use_image_proxy=use_image_proxy,
                    stealth=stealth,
                    state=state,
                    hub=hub,
                    settings_store=settings_store,
                    public_api_base=pub,
                )
            except Exception:
                traceback.print_exc()

    t = threading.Thread(target=_loop, name="incremental-scraper", daemon=True)
    t.start()

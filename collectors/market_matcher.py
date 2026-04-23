"""
당근 메인 매물에 대해 번개장터·구구스·필웨이 최저 시세를 붙여 ``market_price`` 산출.

- ``scan_brands_pipeline(..., enrich_markets=True)`` 일 때만 매 당근 행마다 ``enrich`` 호출(느림).
- 기본 ``enrich_markets=True`` (1:1 시세 비교). 끄려면 ``LUXEFINDER_ENRICH_MARKETS=0``.
"""

from __future__ import annotations

import traceback

from .bunjang_spider import BunjangSpider
from .daangn_spider import DaangnSpider
from .feelway_spider import FeelwaySpider
from .gugus_spider import GugusSpider
from .models import DaangnEnrichedListing, RawListing


class MarketMatcher:
    def __init__(
        self,
        *,
        daangn: DaangnSpider | None = None,
        bunjang: BunjangSpider | None = None,
        gugus: GugusSpider | None = None,
        feelway: FeelwaySpider | None = None,
        stealth: bool = True,
    ) -> None:
        self.daangn = daangn or DaangnSpider(stealth=stealth)
        self.bunjang = bunjang or BunjangSpider(stealth=stealth)
        self.gugus = gugus or GugusSpider(stealth=stealth)
        self.feelway = feelway or FeelwaySpider(stealth=stealth)

    @staticmethod
    def build_search_query(daangn_item: RawListing) -> str:
        """
        동일 모델 추정용 쿼리.

        - 브랜드 키워드가 확인된 매물에만 시세를 붙이는 파이프라인 특성상,
          쿼리에도 브랜드를 포함시키는 것이 오탐/미탐을 크게 줄인다.
        """
        title = (daangn_item.model_name or "").strip()
        desc = (daangn_item.description_text or "").strip()
        blob = f"{title} {desc}".strip()
        brand: str | None = None
        try:
            from api.brand_constants import text_matches_catalog_brand

            brand = text_matches_catalog_brand(blob)
        except Exception:
            brand = None

        q = title
        if brand:
            # title 에 브랜드가 없으면 앞에 붙여 검색 정확도 개선
            if brand.lower() not in q.lower():
                q = f"{brand} {q}".strip()
        return q[:120]

    @staticmethod
    def _listing_url_or_none(item: RawListing | None) -> str | None:
        if item is None:
            return None
        u = (item.listing_url or "").strip()
        return u or None

    @staticmethod
    def _safe_lowest(spider: object, q: str) -> tuple[int | None, RawListing | None]:
        try:
            fn = getattr(spider, "lowest_acceptable_price", None)
            if not callable(fn):
                return None, None
            return fn(q)  # type: ignore[misc]
        except Exception:
            traceback.print_exc()
            return None, None

    def enrich(self, daangn_item: RawListing) -> DaangnEnrichedListing:
        from concurrent.futures import ThreadPoolExecutor

        q = self.build_search_query(daangn_item)
        print(f"[match] enrich query={q!r} (source=daangn) parallel=3")
        with ThreadPoolExecutor(max_workers=3) as ex:
            f_bj = ex.submit(self._safe_lowest, self.bunjang, q)
            f_gg = ex.submit(self._safe_lowest, self.gugus, q)
            f_fw = ex.submit(self._safe_lowest, self.feelway, q)
            bp, rb = f_bj.result()
            gp, rg = f_gg.result()
            fp, rf = f_fw.result()
        print(f"[match] [bunjang] lowest={bp} url={(rb.listing_url if rb else None)}")
        print(f"[match] [gugus] lowest={gp} url={(rg.listing_url if rg else None)}")
        print(f"[match] [feelway] lowest={fp} url={(rf.listing_url if rf else None)}")
        platform = {"bunjang": bp, "gugus": gp, "feelway": fp}
        urls = {
            "bunjang": self._listing_url_or_none(rb),
            "gugus": self._listing_url_or_none(rg),
            "feelway": self._listing_url_or_none(rf),
        }
        priced = {k: v for k, v in platform.items() if isinstance(v, int) and v > 0}
        if not priced:
            return DaangnEnrichedListing(
                daangn=daangn_item,
                market_price_krw=None,
                platform_prices_krw=platform,
                reference_platform=None,
                platform_listing_urls=urls,
            )
        ref_platform = min(priced, key=lambda k: priced[k])
        market = priced[ref_platform]
        return DaangnEnrichedListing(
            daangn=daangn_item,
            market_price_krw=market,
            platform_prices_krw=platform,
            reference_platform=ref_platform,
            platform_listing_urls=urls,
        )

    def scan_brands_pipeline(
        self,
        queries: list[str],
        *,
        per_query_limit: int = 12,
        enrich_markets: bool = True,
    ) -> list[DaangnEnrichedListing]:
        """키워드별 당근 검색 후, ``enrich_markets=True`` 일 때만 번개/구구스/필웨이 시세 조회(느림)."""
        enriched: list[DaangnEnrichedListing] = []
        for q in queries:
            try:
                items = self.daangn.search(q, limit=per_query_limit)
                print(f"[match] [daangn] query={q!r} items={len(items)} enrich_markets={enrich_markets}")
            except Exception:
                traceback.print_exc()
                continue
            for item in items:
                try:
                    if enrich_markets:
                        enriched.append(self.enrich(item))
                    else:
                        enriched.append(
                            DaangnEnrichedListing(
                                daangn=item,
                                market_price_krw=None,
                            )
                        )
                except Exception:
                    traceback.print_exc()
                    continue
        return enriched


def attach_market_json_fields(enriched: DaangnEnrichedListing) -> dict:
    """프론트/백엔드 Listing 스키마에 가깝게 flatten."""
    d = enriched.daangn
    return {
        "source": "daangn",
        "model_name": d.model_name,
        "price_krw": d.price_krw,
        "market_price_krw": enriched.market_price_krw,
        "platform_prices_krw": enriched.platform_prices_krw,
        "reference_platform": enriched.reference_platform,
        "listing_url": d.listing_url,
        "image_url": d.image_url,
        "status_text": d.status_text,
        "trade_state": d.trade_state,
        "description_text": d.description_text,
    }

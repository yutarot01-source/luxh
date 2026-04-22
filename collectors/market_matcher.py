"""
당근 메인 매물에 대해 번개장터·구구스·필웨이 최저 시세를 붙여 ``market_price`` 산출.

- 각 플랫폼 스파이더는 ``lowest_acceptable_price`` 로 (판매중/거래완료 우선, 예약 제외 규칙은 spider 쪽) 후보를 좁힘.
- 세 소스 중 **유효한 숫자만** 모아 최소값을 ``market_price_krw`` 로 설정.
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
        """동일 모델 추정용 쿼리. 운영에서는 GPT 정규화 모델명으로 교체."""
        return (daangn_item.model_name or "").strip()[:120]

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
        q = self.build_search_query(daangn_item)
        print(f"[match] enrich query={q!r} (source=daangn)")
        bp, rb = self._safe_lowest(self.bunjang, q)
        print(f"[match] [bunjang] lowest={bp} url={(rb.listing_url if rb else None)}")
        gp, rg = self._safe_lowest(self.gugus, q)
        print(f"[match] [gugus] lowest={gp} url={(rg.listing_url if rg else None)}")
        fp, rf = self._safe_lowest(self.feelway, q)
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
    ) -> list[DaangnEnrichedListing]:
        """샤넬/루이비통/구찌 등 키워드별 당근 → 시세 병합 일괄 실행."""
        enriched: list[DaangnEnrichedListing] = []
        for q in queries:
            try:
                items = self.daangn.search(q, limit=per_query_limit)
                print(f"[match] [daangn] query={q!r} items={len(items)}")
            except Exception:
                traceback.print_exc()
                continue
            for item in items:
                try:
                    enriched.append(self.enrich(item))
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

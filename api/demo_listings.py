"""대시보드 UI 확인용 샘플 1건 — 당근 프록시 이미지·원문 절대 URL 포함."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from api.listing_builder import collected_timestamp_iso

# 당근 정적 자산(프록시 허용 호스트). 깨지면 apple-touch-icon 등으로 교체 가능.
_SAMPLE_ORIGINAL_IMAGE = "https://www.daangn.com/apple-touch-icon.png"
_SAMPLE_SOURCE = "https://www.daangn.com/kr/buy-sell/"

DEMO_LISTING_IDS: frozenset[str] = frozenset({"demo-ui-live"})

DEMO_LISTING_ROWS: list[dict[str, Any]] = [
    {
        "id": "demo-ui-live",
        "brand": "샤넬",
        "rawTitle": "[샘플] 당근 이미지·원문 링크 테스트",
        "normalizedModel": "[샘플] 당근 프록시 이미지 / 원문 버튼 확인",
        "price": 8_900_000,
        "marketPrice": 12_350_000,
        "arbitrageRate": 27.94,
        "status_summary": "A급·영수증·개런티",
        "is_suspicious": False,
        "expected_profit": 3_450_000,
        "location": "서버 샘플 (수집 없이 표시)",
        "postedMinutesAgo": 0,
        "imageUrl": f"/api/image?url={quote(_SAMPLE_ORIGINAL_IMAGE, safe='')}",
        "sourceUrl": _SAMPLE_SOURCE,
        "link": _SAMPLE_SOURCE,
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
            "feelway_lowest_krw": 0,
            "bunjang_lowest_krw": 12_350_000,
        },
        "reference_platform": "bunjang",
        "reference_price_krw": 12_350_000,
    },
]


def merge_demo_listings_first(scraped: list[dict[str, Any]], *, max_items: int) -> list[dict[str, Any]]:
    """샘플 1건을 앞에 두고, 동일 id는 스크랩 결과에서 제외한 뒤 잘라낸다."""
    tail = [x for x in scraped if str(x.get("id", "")) not in DEMO_LISTING_IDS]
    ts = collected_timestamp_iso()
    demos = [{**row, "collectedAt": ts} for row in DEMO_LISTING_ROWS]
    merged = demos + tail
    return merged[:max_items]

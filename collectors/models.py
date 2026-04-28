"""통합 JSON 직렬화용 모델 (FastAPI / 프론트 `Listing`과 필드 정렬 가능)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SourceId = Literal["daangn", "bunjang", "gugus", "feelway"]


@dataclass
class RawListing:
    """단일 플랫폼 검색/목록에서 추출한 원시 행."""

    source: SourceId
    model_name: str
    price_krw: int | None
    status_text: str
    listing_url: str
    image_url: str
    description_text: str
    trade_state: str | None = None
    """판매중 / 거래완료 / 예약중 등 원문 라벨 (사이트별 상이)."""
    raw_html_excerpt: str | None = None
    """디버깅·셀렉터 튜닝용. 운영에서는 비활성화 권장."""
    price_text: str = ""
    """원문에 표시된 가격 문자열."""
    source_title: str = ""
    """원문 카드/상세 제목."""
    fetched_at: str = ""
    """수집 시각(UTC ISO)."""

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DaangnEnrichedListing:
    """당근 메인 매물 + 타 플랫폼 시세 비교 결과."""

    daangn: RawListing
    market_price_krw: int | None
    """번개/구구스/필웨이 중 수집된 최저가(원). 없으면 None."""
    platform_prices_krw: dict[str, int | None] = field(
        default_factory=lambda: {"bunjang": None, "gugus": None, "feelway": None}
    )
    reference_platform: str | None = None
    """최저가를 제공한 플랫폼 키 (bunjang | gugus | feelway)."""
    platform_listing_urls: dict[str, str | None] = field(
        default_factory=lambda: {"bunjang": None, "gugus": None, "feelway": None}
    )
    """시세 산출에 사용된 각 플랫폼 **상세 페이지** URL (스파이더 ``listing_url``)."""

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

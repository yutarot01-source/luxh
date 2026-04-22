"""대시보드 설정 — 스레드 안전 + JSON 파일 영속화."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from api.brand_constants import BAG_BRAND_CANONICAL

DEFAULT_BRANDS: tuple[str, ...] = BAG_BRAND_CANONICAL

# 프론트 `LISTING_CATEGORY_FILTERS` id 와 동일
DEFAULT_CATEGORY_IDS: tuple[str, ...] = (
    "tote_shoulder",
    "crossbody",
    "clutch_chain",
    "top_handle",
    "backpack",
    "bucket_hobo",
)


@dataclass
class DashboardSettings:
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_notifications_enabled: bool = True
    telegram_alert_threshold_percent: float = 25.0
    """텔레그램 알림: 예상 수익(원)이 이 값 이상일 때만 (0이면 미사용)."""
    telegram_min_expected_profit_krw: int = 0
    threshold: float = 25.0
    require_warranty: bool = True
    min_grade: str = "B"
    selected_brands: list[str] = field(default_factory=lambda: list(DEFAULT_BRANDS))
    selected_categories: list[str] = field(default_factory=lambda: list(DEFAULT_CATEGORY_IDS))
    openai_api_key: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, d: dict[str, Any]) -> DashboardSettings:
        return cls(
            telegram_bot_token=str(d.get("telegram_bot_token", "") or ""),
            telegram_chat_id=str(d.get("telegram_chat_id", "") or ""),
            telegram_notifications_enabled=bool(d.get("telegram_notifications_enabled", True)),
            telegram_alert_threshold_percent=float(d.get("telegram_alert_threshold_percent", 25) or 25),
            telegram_min_expected_profit_krw=int(
                d.get("telegram_min_expected_profit_krw", d.get("telegramMinExpectedProfitKrw", 0)) or 0
            ),
            threshold=float(d.get("threshold", 25) or 25),
            require_warranty=bool(d.get("require_warranty", True)),
            min_grade=str(d.get("min_grade", "B") or "B"),
            selected_brands=_coerce_brands_from_dict(d),
            selected_categories=_coerce_categories_from_dict(d),
            openai_api_key=str(d.get("openai_api_key", "") or ""),
        )


def _coerce_brands_from_dict(d: dict[str, Any]) -> list[str]:
    if "selected_brands" not in d:
        return list(DEFAULT_BRANDS)
    raw = d.get("selected_brands")
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return list(DEFAULT_BRANDS)


def _coerce_categories_from_dict(d: dict[str, Any]) -> list[str]:
    if "selected_categories" not in d:
        return list(DEFAULT_CATEGORY_IDS)
    raw = d.get("selected_categories")
    if not isinstance(raw, list):
        return list(DEFAULT_CATEGORY_IDS)
    valid = set(DEFAULT_CATEGORY_IDS)
    out = [str(x) for x in raw if str(x) in valid]
    return out if out else list(DEFAULT_CATEGORY_IDS)


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data = DashboardSettings()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            j = json.loads(raw)
            if isinstance(j, dict):
                with self._lock:
                    self._data = DashboardSettings.from_json_dict(j)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    def _save_unlocked(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        payload = json.dumps(self._data.to_json_dict(), ensure_ascii=False, indent=2)
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self._path)

    def snapshot(self) -> DashboardSettings:
        with self._lock:
            return DashboardSettings(**asdict(self._data))

    def update_from_payload(self, **kwargs: Any) -> DashboardSettings:
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._data, k):
                    setattr(self._data, k, v)
            self._save_unlocked()
            return DashboardSettings(**asdict(self._data))

    def replace_all(self, data: DashboardSettings) -> DashboardSettings:
        with self._lock:
            self._data = data
            self._save_unlocked()
            return DashboardSettings(**asdict(self._data))

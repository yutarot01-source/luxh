"""인메모리 매물 목록 (API + SSE 스냅샷 공유)."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

_LINK_KEY_ALIASES = {"gugus": "gogoose", "gogoose": "gogoose"}
_PLATFORM_PRICE_KEY_ALIASES = {
    "gugus_lowest_krw": "gogoose_lowest_krw",
    "gogoose_lowest_krw": "gogoose_lowest_krw",
}


def _normalize_nested_platform_keys(row: dict[str, Any]) -> dict[str, Any]:
    """API 응답 스키마의 구구스 키는 프론트와 맞춰 ``gogoose`` 로 통일."""
    out = dict(row)
    links = out.get("platformLinks") or out.get("platform_links")
    if isinstance(links, dict):
        norm_links: dict[str, Any] = {}
        for key, value in links.items():
            k = str(key).strip().lower()
            norm_links[_LINK_KEY_ALIASES.get(k, k)] = value
        out["platformLinks"] = norm_links
        out.pop("platform_links", None)

    prices = out.get("platform_prices")
    if isinstance(prices, dict):
        norm_prices: dict[str, Any] = {}
        for key, value in prices.items():
            k = str(key).strip().lower()
            norm_prices[_PLATFORM_PRICE_KEY_ALIASES.get(k, k)] = value
        out["platform_prices"] = norm_prices
    return out


class ListingState:
    """``max_items`` 는 ``replace_all`` / ``prepend`` 시 적용되는 상한."""

    def __init__(self, max_items: int = 80) -> None:
        self._items: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._max = max_items

    @property
    def max_items(self) -> int:
        return self._max

    def has_listing(self, listing_id: str) -> bool:
        if not listing_id:
            return False
        with self._lock:
            return any(x.get("id") == listing_id for x in self._items)

    def replace_all(self, listings: list[dict[str, Any]]) -> None:
        with self._lock:
            self._items = [_normalize_nested_platform_keys(x) for x in listings[: self._max] if x.get("id")]

    def prepend(self, listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """새 id만 앞에 붙이고 전체 목록 반환."""
        with self._lock:
            seen = {x.get("id") for x in self._items}
            fresh = [
                _normalize_nested_platform_keys(x)
                for x in listings
                if x.get("id") and x.get("id") not in seen
            ]
            self._items = (fresh + self._items)[: self._max]
            return list(self._items)

    def add_listing_front(self, row: dict[str, Any]) -> bool:
        """동일 ``id`` 가 있으면 갱신, 없으면 맨 앞에 삽입. 새 행이면 ``True``."""
        row = _normalize_nested_platform_keys(row)
        lid = row.get("id")
        if not lid:
            return False
        with self._lock:
            created = all(x.get("id") != lid for x in self._items)
            self._items = [x for x in self._items if x.get("id") != lid]
            self._items.insert(0, row)
            self._items = self._items[: self._max]
            return created

    def merge_listing(self, listing_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """``id`` 행에 patch 병합 후 병합된 행 반환."""
        if not listing_id or not patch:
            return None
        patch = _normalize_nested_platform_keys(patch)
        with self._lock:
            for i, row in enumerate(self._items):
                if row.get("id") != listing_id:
                    continue
                merged = dict(row)
                for k, v in patch.items():
                    if k == "platform_prices" and isinstance(v, dict):
                        base = dict(row.get("platform_prices") or {})
                        base.update(v)
                        merged["platform_prices"] = base
                    elif k == "platformLinks" and isinstance(v, dict):
                        base = dict(row.get("platformLinks") or {})
                        base.update(v)
                        merged["platformLinks"] = base
                    elif k == "platform_basis" and isinstance(v, dict):
                        base = dict(row.get("platform_basis") or {})
                        base.update(v)
                        merged["platform_basis"] = base
                    else:
                        merged[k] = v
                self._items[i] = merged
                return dict(merged)
        return None

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._items)


class SSEHub:
    """구독자에게 ``dict`` 이벤트 브로드캐스트."""

    def __init__(self) -> None:
        self._subs: list[asyncio.Queue] = []
        self._sub_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def register(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        with self._sub_lock:
            self._subs.append(q)
        return q

    async def unregister(self, q: asyncio.Queue) -> None:
        with self._sub_lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish_from_thread(self, message: dict[str, Any]) -> None:
        loop = self._loop
        if loop is None:
            return

        def _broadcast() -> None:
            with self._sub_lock:
                subs = list(self._subs)
            for q in subs:
                try:
                    q.put_nowait(message)
                except asyncio.QueueFull:
                    pass
                except Exception:
                    pass

        loop.call_soon_threadsafe(_broadcast)

    async def publish(self, message: dict[str, Any]) -> None:
        with self._sub_lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass

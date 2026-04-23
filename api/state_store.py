"""인메모리 매물 목록 (API + SSE 스냅샷 공유)."""

from __future__ import annotations

import asyncio
import threading
from typing import Any


class ListingState:
    """``max_items`` 는 ``replace_all`` / ``prepend`` 시 적용되는 상한."""

    def __init__(self, max_items: int = 80) -> None:
        self._items: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._max = max_items

    @property
    def max_items(self) -> int:
        return self._max

    def replace_all(self, listings: list[dict[str, Any]]) -> None:
        with self._lock:
            self._items = listings[: self._max]

    def prepend(self, listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """새 id만 앞에 붙이고 전체 목록 반환."""
        with self._lock:
            seen = {x["id"] for x in self._items}
            fresh = [x for x in listings if x["id"] not in seen]
            self._items = (fresh + self._items)[: self._max]
            return list(self._items)

    def add_listing_front(self, row: dict[str, Any]) -> None:
        """동일 ``id`` 가 있으면 제거 후 맨 앞에 삽입(실시간 당근 행)."""
        lid = row.get("id")
        if not lid:
            return
        with self._lock:
            self._items = [x for x in self._items if x.get("id") != lid]
            self._items.insert(0, row)
            self._items = self._items[: self._max]

    def merge_listing(self, listing_id: str, patch: dict[str, Any]) -> None:
        """``id`` 행에 필드 병합. ``platform_prices``·``platformLinks`` 는 얕은 병합."""
        if not listing_id or not patch:
            return
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
                    else:
                        merged[k] = v
                self._items[i] = merged
                return

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

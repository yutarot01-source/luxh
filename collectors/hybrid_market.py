"""
타 플랫폼 최저가: **정적 HTTP(stealth=False) 우선**, 결과 없으면 **스텔스** 재시도.

각 페이즈는 ``phase_budget`` 초 안에 끝나도록 ``ThreadPoolExecutor.result(timeout=…)`` 로 상한을 둔다.
"""

from __future__ import annotations

import traceback
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any


def lowest_acceptable_hybrid(
    spider_cls: type[Any],
    query: str,
    *,
    phase_budget: float = 2.35,
) -> tuple[int | None, Any]:
    """
    ``lowest_acceptable_price(query)`` 를 정적 → 스텔스 순으로 호출.
    양의 가격이 나오면 즉시 반환.
    """
    if not (query or "").strip():
        return None, None

    for stealth in (False, True):
        try:
            inst = spider_cls(stealth=stealth)
            with ThreadPoolExecutor(1) as ex:
                fut = ex.submit(inst.lowest_acceptable_price, query.strip()[:120])
                try:
                    p, r = fut.result(timeout=phase_budget)
                except FuturesTimeout:
                    continue
                except Exception:
                    traceback.print_exc()
                    continue
            if isinstance(p, (int, float)) and int(p) > 0:
                return int(p), r
        except Exception:
            traceback.print_exc()
    return None, None

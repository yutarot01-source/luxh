"""
Scrapling StealthyFetcher / DynamicFetcher 용 자동 대기·무한 스크롤 프로파일.

공식 인자 조합
--------------
- ``load_dom=True``: DOM 로드·스크립트 실행 대기
- ``network_idle=True``: ``networkidle`` 로 XHR 물결 이후 안정화
- ``wait_selector`` + ``wait_selector_state``: 리스트(또는 카드)가 붙을 때까지
- ``wait`` (ms): 마지막 추가 안정화
- ``page_action``: 무한 스크롤 트리거 (하단 스크롤 반복)

``Fetcher(stealth=True, …)`` 표기는 코드상 ``StealthyFetcher.fetch(..., **kwargs)`` 로 매핑합니다.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


def make_infinite_scroll_action(
    *,
    max_rounds: int = 5,
    pause_ms: int = 1000,
    product_count_selector: str | None = None,
    networkidle_between: bool = True,
    networkidle_timeout_ms: int = 8_000,
) -> Callable[[Any], None]:
    """
    무한 스크롤 대응 ``page_action``.

    - 기본: 문서 높이가 더 이상 늘지 않으면 종료(2연속 동일).
    - ``product_count_selector`` 가 있으면: 해당 CSS로 잡히는 노드 개수가
      더 이상 늘지 않을 때도 종료(상품이 안 늘어날 때까지).
    """

    sel_json = json.dumps(product_count_selector) if product_count_selector else None

    def page_action(page: Any) -> None:
        last_h = 0
        stable_h = 0
        last_n = -1
        stable_n = 0

        def count_products() -> int:
            if not sel_json:
                return -1
            try:
                return int(page.evaluate(f"() => document.querySelectorAll({sel_json}).length"))
            except Exception:
                return -1

        for _ in range(max_rounds):
            page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
            page.wait_for_timeout(pause_ms)
            if networkidle_between:
                try:
                    page.wait_for_load_state("networkidle", timeout=networkidle_timeout_ms)
                except Exception:
                    pass

            h = page.evaluate("() => document.documentElement.scrollHeight")
            if h <= last_h + 2:
                stable_h += 1
            else:
                stable_h = 0
            last_h = h

            n = count_products()
            if n >= 0:
                if n <= last_n:
                    stable_n += 1
                else:
                    stable_n = 0
                last_n = max(last_n, n)

            if stable_h >= 2:
                break
            if sel_json and stable_n >= 2 and last_n >= 0:
                break

        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(min(1500, pause_ms))

    return page_action


def daangn_auto_wait_fetch_kwargs(
    *,
    timeout_ms: int = 32_000,
    settle_ms: int = 900,
) -> dict[str, Any]:
    """당근 검색: 리스트 카드가 보일 때까지 + 네트워크 유휴."""
    return {
        "load_dom": True,
        "network_idle": True,
        "timeout": timeout_ms,
        "wait": settle_ms,
        # 2026-04 기준 당근 검색은 SSR 카드가 아니라 동적 렌더링이 많아
        # 상세 링크 앵커가 DOM에 등장하는 시점을 기준으로 대기한다.
        "wait_selector": "a[href*='/buy-sell/']",
        "wait_selector_state": "visible",
        "selector_config": {"adaptive": True},
    }


def bunjang_auto_wait_fetch_kwargs(
    *,
    scroll_rounds: int = 5,
    scroll_pause_ms: int = 1_000,
    timeout_ms: int = 95_000,
    settle_ms: int = 2_200,
) -> dict[str, Any]:
    """번개 모바일 검색: 상품 링크 visible → 스크롤로 추가 로딩."""
    return {
        "load_dom": True,
        "network_idle": True,
        "timeout": timeout_ms,
        "wait": settle_ms,
        "wait_selector": "a[href*='/products/']",
        "wait_selector_state": "visible",
        "page_action": make_infinite_scroll_action(
            max_rounds=scroll_rounds,
            pause_ms=scroll_pause_ms,
            product_count_selector="a[href*='/products/']",
            networkidle_between=True,
        ),
        "selector_config": {"adaptive": True},
    }


def feelway_auto_wait_fetch_kwargs(
    *,
    scroll_rounds: int = 5,
    scroll_pause_ms: int = 1_000,
    timeout_ms: int = 100_000,
    settle_ms: int = 2_600,
) -> dict[str, Any]:
    """필웨이 검색: 상품 링크 visible → 스크롤."""
    return {
        "load_dom": True,
        "network_idle": True,
        "timeout": timeout_ms,
        "wait": settle_ms,
        "wait_selector": (
            "a[href*='feelway.com'][href*='goods'], "
            "a[href*='feelway.com'][href*='product'], "
            "main a[href*='feelway'], "
            "[class*='product'] a[href*='feelway']"
        ),
        "wait_selector_state": "visible",
        "page_action": make_infinite_scroll_action(
            max_rounds=scroll_rounds,
            pause_ms=scroll_pause_ms,
            product_count_selector="a[href*='feelway.com']",
            networkidle_between=True,
        ),
        "selector_config": {"adaptive": True},
    }


def gugus_auto_wait_fetch_kwargs(
    *,
    timeout_ms: int = 90_000,
    settle_ms: int = 2_000,
) -> dict[str, Any]:
    """구구스 검색·목록: URL이 자주 바뀌어 '대기'가 길어지면 전체 수집이 멈추므로 보수적으로 짧게."""
    return {
        "load_dom": True,
        "network_idle": True,
        "timeout": min(timeout_ms, 25_000),
        "wait": min(settle_ms, 800),
        # selector wait는 전체를 블로킹시키기 쉬워 제거 (응답만 받아 파싱 시도)
        "selector_config": {"adaptive": True},
    }


BROWSER_ONLY_FETCH_KEYS = frozenset(
    {
        "page_action",
        "page_setup",
        "wait_selector",
        "wait_selector_state",
        "network_idle",
        "load_dom",
        "headless",
        "locale",
        "useragent",
        "solve_cloudflare",
        "capture_xhr",
        "disable_resources",
        "block_ads",
        "blocked_domains",
        "real_chrome",
        "cdp_url",
        "user_data_dir",
        "init_script",
        "extra_flags",
        "dns_over_https",
        "allow_webgl",
        "hide_canvas",
        "block_webrtc",
        "google_search",
        "timezone_id",
        "cookies",
        "proxy",
        "additional_args",
        "selector_config",
        "wait",
        "max_pages",
    }
)


def filter_kwargs_for_static_fetch(kwargs: dict[str, Any]) -> dict[str, Any]:
    """``stealth=False`` 일 때 ``Fetcher.get`` 에 브라우저 전용 키가 섞이지 않도록 제거."""
    return {k: v for k, v in kwargs.items() if k not in BROWSER_ONLY_FETCH_KEYS}

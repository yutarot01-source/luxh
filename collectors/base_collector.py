"""
공통 수집 베이스 (Scrapling 최신 fetch 플래그 반영).

요구사항의 ``Fetcher(stealth=True, load_dom=True)`` 는 라이브러리에서
``StealthyFetcher.fetch(url, load_dom=True, …)`` 형태로 호출합니다.

기본 브라우저 페치 옵션
-----------------------
- ``load_dom=True``
- ``network_idle=True``  … ``FetcherConfig`` 기본값 (문서·XHR 안정화)

``stealth=False`` 이면 ``Fetcher.get`` 만 사용하며, ``dynamic_wait.filter_kwargs_for_static_fetch`` 로
``page_action``, ``network_idle`` 등 브라우저 전용 키를 제거합니다.

StealthyFetcher 의존성(patchright 등)은 **지연 import** 합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .dynamic_wait import filter_kwargs_for_static_fetch
from .text_utils import strip_html_to_description
from .user_agent import pick_user_agent_for_url

if TYPE_CHECKING:
    from scrapling.engines.toolbelt.custom import Response


def _request_has_user_agent(kw: dict[str, Any]) -> bool:
    if kw.get("useragent"):
        return True
    eh = kw.get("extra_headers")
    if isinstance(eh, dict) and eh.get("User-Agent"):
        return True
    hd = kw.get("headers")
    if isinstance(hd, dict) and hd.get("User-Agent"):
        return True
    return False


@dataclass
class FetcherConfig:
    """StealthyFetcher 기본값. ``kwargs``가 덮어씀."""

    locale: str = "ko-KR"
    load_dom: bool = True
    network_idle: bool = True
    timeout: int = 28_000
    wait: int = 800
    headless: bool = True
    """``m.`` / ``mobile.`` 호스트용 모바일 UA. 비우면 내장 기본."""
    mobile_user_agent: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def stealth_fetch(url: str, *, stealth: bool = True, cfg: FetcherConfig | None = None, **kwargs: Any) -> "Response":
    cfg = cfg or FetcherConfig()
    if stealth:
        try:
            from scrapling.fetchers import StealthyFetcher
        except ModuleNotFoundError as e:
            # patchright/playwright 미설치 환경에서도 수집 파이프라인이 "완전히 죽지" 않도록
            # 브라우저 페치를 정적 Fetcher로 폴백한다.
            # (동적 사이트는 결과가 적을 수 있으나, 최소한 루프·API는 살아있어야 한다.)
            print(
                f"[collector] StealthyFetcher unavailable ({e}); falling back to static Fetcher.get",
            )
            stealth = False
        except Exception as e:
            print(f"[collector] StealthyFetcher import failed ({e}); falling back to static Fetcher.get")
            stealth = False

        if stealth:
            merged: dict[str, Any] = {
                "locale": cfg.locale,
                "load_dom": cfg.load_dom,
                "network_idle": cfg.network_idle,
                "timeout": cfg.timeout,
                "wait": cfg.wait,
                "headless": cfg.headless,
                **cfg.extra,
                **kwargs,
            }
            return StealthyFetcher.fetch(url, **merged)
    from scrapling.fetchers import Fetcher

    static_kw = filter_kwargs_for_static_fetch(dict(kwargs))
    # Fetcher.get()는 timeout을 positional/kw로 받기 때문에 중복 전달을 피한다.
    static_kw.pop("timeout", None)
    return Fetcher.get(url, timeout=max(5, int(cfg.timeout // 1000)), **static_kw)


class BaseCollector:
    site_id: str = "base"

    def __init__(self, *, stealth: bool = True, fetcher_cfg: FetcherConfig | None = None) -> None:
        self.stealth = stealth
        self.fetcher_cfg = fetcher_cfg or FetcherConfig()

    def fetch(self, url: str, **kwargs: Any) -> "Response":
        kw = dict(kwargs)
        ua = pick_user_agent_for_url(url, self.fetcher_cfg.mobile_user_agent or None)
        if ua and not _request_has_user_agent(kw):
            if self.stealth:
                kw.setdefault("useragent", ua)
            else:
                headers = dict(kw.get("headers") or {})
                headers.setdefault("User-Agent", ua)
                kw["headers"] = headers
        return stealth_fetch(url, stealth=self.stealth, cfg=self.fetcher_cfg, **kw)

    @staticmethod
    def response_description(response: "Response") -> str:
        html = str(response.html_content)
        return strip_html_to_description(html)

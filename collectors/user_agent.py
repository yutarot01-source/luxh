"""모바일 사이트(m.*) 요청 시 브라우저 UA 정렬."""

from __future__ import annotations

import random
from urllib.parse import urlparse

# Android Chrome 모바일 (최근 계열). 운영 시 주기적 갱신 권장.
DEFAULT_MOBILE_CHROME_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S908N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
)

USER_AGENT_POOL: tuple[str, ...] = (
    DEFAULT_MOBILE_CHROME_UA,
    "Mozilla/5.0 (Linux; Android 14; SM-S921N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
)


def is_mobile_site_url(url: str) -> bool:
    """호스트가 ``m.`` / ``mobile.`` 로 시작하면 모바일 전용 사이트로 간주."""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    if not host:
        return False
    return host.startswith("m.") or host.startswith("mobile.")


def pick_user_agent_for_url(url: str, override: str | None) -> str | None:
    """요청마다 override 또는 풀에서 랜덤 User-Agent 선택."""
    if (override or "").strip():
        return override.strip()
    return random.choice(USER_AGENT_POOL)

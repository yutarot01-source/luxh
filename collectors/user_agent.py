"""모바일 사이트(m.*) 요청 시 브라우저 UA 정렬."""

from __future__ import annotations

from urllib.parse import urlparse

# Android Chrome 모바일 (최근 계열). 운영 시 주기적 갱신 권장.
DEFAULT_MOBILE_CHROME_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S908N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
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
    """모바일 URL이면 ``override`` 또는 기본 모바일 UA, 아니면 None(변경 없음)."""
    if not is_mobile_site_url(url):
        return None
    return (override or "").strip() or DEFAULT_MOBILE_CHROME_UA

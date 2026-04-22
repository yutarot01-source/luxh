"""이미지 프록시 허용 호스트 판별 (당근·번개·필웨이·구구스 등)."""

from __future__ import annotations

from urllib.parse import urlparse


def is_daangn_family_image_url(url: str) -> bool:
    """당근·캐롯 CDN 계열."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    if host.endswith("daangn.com") or host == "daangn.com":
        return True
    if "karrotmarket.com" in host or host.endswith(".karrotmarket.com"):
        return True
    if host.endswith("gcp-karroter.com") or host.endswith("karrotuser.com"):
        return True
    # 당근이 쓰는 CloudFront 오리진(article 이미지)
    if host.endswith("cloudfront.net") and "origin/article" in url:
        return True
    return False


def is_resale_platform_image_url(url: str) -> bool:
    """번개장터·필웨이·구구스(및 CDN) 이미지 — Referer·UA 필요."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    if "bunjang" in host:
        return True
    if "feelway" in host:
        return True
    if "gugus" in host:
        return True
    return False


def is_listing_image_proxy_allowed(url: str) -> bool:
    """``GET /api/image`` 로 프록시할 수 있는 원본 이미지 URL."""
    return is_daangn_family_image_url(url) or is_resale_platform_image_url(url)

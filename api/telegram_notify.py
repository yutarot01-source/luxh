"""텔레그램 Bot API — 신규 매물 알림(멀티 플랫폼·원문 URL·인라인 버튼·이미지 프록시)."""

from __future__ import annotations

import html
import json
import re
import threading
import time
from typing import Any
from urllib.parse import urljoin

import httpx

_SENT_ALERT_TTL_SEC = 60 * 60 * 12
_SENT_ALERTS: dict[str, float] = {}
_SENT_ALERTS_LOCK = threading.Lock()


def _normalize_token(raw: str) -> str:
    return (raw or "").strip().strip("\ufeff").strip()


def _normalize_chat_id(raw: str) -> str | int:
    s = (raw or "").strip().strip("\ufeff")
    s = re.sub(r"\s+", "", s)
    if re.fullmatch(r"-?\d+", s or ""):
        return int(s)
    return s


# 메인 매물 출처(현재 파이프라인은 당근 기준) + 시세 비교 플랫폼 라벨
PLATFORM_BADGE_MAIN: dict[str, str] = {
    "daangn": "[당근마켓]",
    "bunjang": "[번개장터]",
    "gugus": "[구구스]",
    "gogoose": "[구구스]",
    "feelway": "[필웨이]",
}

PLATFORM_BUTTON: dict[str, str] = {
    "daangn": "당근 원문",
    "bunjang": "번개 원문",
    "gogoose": "구구스 원문",
    "feelway": "필웨이 원문",
}

PLATFORM_PRICE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("bunjang", "번개장터", "bunjang_lowest_krw"),
    ("feelway", "필웨이", "feelway_lowest_krw"),
    ("gogoose", "구구스", "gogoose_lowest_krw"),
)


def _primary_article_url(row: dict[str, Any]) -> str:
    for k in ("link", "sourceUrl", "source_url"):
        v = row.get(k)
        if isinstance(v, str) and v.strip().startswith("http"):
            return v.strip()
    return ""


def _alert_dedupe_key(chat_id: str, row: dict[str, Any]) -> str:
    rid = row.get("id")
    if isinstance(rid, str) and rid.strip():
        item = rid.strip()
    else:
        item = _primary_article_url(row) or str(row.get("rawTitle") or row.get("normalizedModel") or "")
    return f"{_normalize_chat_id(chat_id)}:{item}"


def _should_send_alert(chat_id: str, row: dict[str, Any]) -> bool:
    now = time.monotonic()
    key = _alert_dedupe_key(chat_id, row)
    with _SENT_ALERTS_LOCK:
        expired = [k for k, ts in _SENT_ALERTS.items() if now - ts > _SENT_ALERT_TTL_SEC]
        for k in expired:
            _SENT_ALERTS.pop(k, None)
        if key in _SENT_ALERTS:
            return False
        _SENT_ALERTS[key] = now
        return True


def _forget_alert(chat_id: str, row: dict[str, Any]) -> None:
    key = _alert_dedupe_key(chat_id, row)
    with _SENT_ALERTS_LOCK:
        _SENT_ALERTS.pop(key, None)


def _absolute_image_url_for_telegram(image_url: str, public_api_base: str) -> str | None:
    """텔레그램 서버가 받아갈 수 있도록 공개 HTTPS URL로 정규화(상대 ``/api/image`` → 절대)."""
    u = (image_url or "").strip()
    if not u:
        return None
    base = (public_api_base or "").rstrip("/")
    if u.startswith("/"):
        if not base:
            return None
        return urljoin(base + "/", u.lstrip("/"))
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return None


def send_telegram_message(
    token: str,
    chat_id: str,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    reply_markup: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    token = _normalize_token(token)
    chat_id_norm = _normalize_chat_id(chat_id)
    if not token or (isinstance(chat_id_norm, str) and not chat_id_norm):
        return False, "봇 토큰 또는 채팅 ID가 비어 있습니다."
    # int로 파싱된 chat_id라도 0이면 무효
    if isinstance(chat_id_norm, int) and chat_id_norm == 0:
        return False, "채팅 ID가 유효하지 않습니다."
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": chat_id_norm,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        with httpx.Client(timeout=25.0) as client:
            r = client.post(url, json=payload)
        try:
            data = r.json()
        except json.JSONDecodeError:
            return False, f"텔레그램 응답 파싱 실패 (HTTP {r.status_code}): {r.text[:500]}"
        if r.status_code == 200 and isinstance(data, dict) and data.get("ok"):
            return True, "ok"
        if isinstance(data, dict):
            desc = data.get("description") or data.get("error_code")
            if desc:
                return False, str(desc)
        return False, f"HTTP {r.status_code}: {(r.text or '')[:500]}"
    except httpx.HTTPError as e:
        return False, str(e)


def send_telegram_photo(
    token: str,
    chat_id: str,
    photo_url: str,
    caption: str,
    *,
    parse_mode: str | None = "HTML",
    reply_markup: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    token = _normalize_token(token)
    chat_id_norm = _normalize_chat_id(chat_id)
    if not token or (isinstance(chat_id_norm, str) and not chat_id_norm):
        return False, "봇 토큰 또는 채팅 ID가 비어 있습니다."
    if isinstance(chat_id_norm, int) and chat_id_norm == 0:
        return False, "채팅 ID가 유효하지 않습니다."
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    cap = caption[:1020] + ("…" if len(caption) > 1020 else "")
    payload: dict[str, Any] = {
        "chat_id": chat_id_norm,
        "photo": photo_url,
        "caption": cap,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        with httpx.Client(timeout=35.0) as client:
            r = client.post(url, json=payload)
        try:
            data = r.json()
        except json.JSONDecodeError:
            return False, f"텔레그램 응답 파싱 실패 (HTTP {r.status_code}): {r.text[:500]}"
        if r.status_code == 200 and isinstance(data, dict) and data.get("ok"):
            return True, "ok"
        if isinstance(data, dict):
            desc = data.get("description") or data.get("error_code")
            if desc:
                return False, str(desc)
        return False, f"HTTP {r.status_code}: {(r.text or '')[:500]}"
    except httpx.HTTPError as e:
        return False, str(e)


def build_telegram_inline_keyboard(row: dict[str, Any], *, public_api_base: str) -> dict[str, Any] | None:
    """원문 보기 — 플랫폼별 실제 상세 URL (url 버튼)."""
    rows: list[list[dict[str, str]]] = []
    main = _primary_article_url(row)
    if main:
        plat = str(row.get("platform") or "daangn").lower()
        rows.append([{"text": PLATFORM_BUTTON.get(plat, "원문 보기"), "url": main}])

    pl = row.get("platformLinks") or row.get("platform_links") or {}
    if isinstance(pl, dict):
        order = ("bunjang", "feelway", "gogoose")
        row_btns: list[dict[str, str]] = []
        for key in order:
            u = pl.get(key)
            if key == "gogoose" and not u:
                u = pl.get("gugus")
            if not isinstance(u, str) or not u.strip().startswith("http"):
                continue
            label = PLATFORM_BUTTON.get(key, "원문")
            row_btns.append({"text": label, "url": u.strip()})
        if row_btns:
            for i in range(0, len(row_btns), 2):
                rows.append(row_btns[i : i + 2])

    if not rows:
        return None
    _ = public_api_base  # 향후 콜백용 예약
    return {"inline_keyboard": rows}


def format_listing_alert(row: dict[str, Any]) -> str:
    title = row.get("normalized_model_name") or row.get("normalizedModel") or row.get("rawTitle") or "매물"
    brand = row.get("brand") or ""
    price = row.get("price")
    rate = row.get("arbitrageRate")
    loc = row.get("location") or ""
    main_url = _primary_article_url(row)
    price_s = f"{int(price):,}원" if isinstance(price, (int, float)) else str(price)
    rate_value = row.get("profit_rate", rate)
    rate_s = f"{float(rate_value):.1f}%" if isinstance(rate_value, (int, float)) else str(rate_value)
    summary = (row.get("status_summary") or "").strip()
    reasoning = (row.get("reasoning_short") or "").strip()
    grade = (row.get("condition_grade") or "").strip()
    proof = row.get("has_authenticity_proof")
    profit = row.get("expected_profit")
    profit_s = f"{int(profit):,}원" if isinstance(profit, (int, float)) else ""
    ref_price = row.get("market_reference_price") or row.get("reference_price_krw") or row.get("marketPrice")
    ref_price_s = f"{int(ref_price):,}원" if isinstance(ref_price, (int, float)) else str(ref_price or "")
    pp = row.get("platform_prices") or {}
    platform_lines: list[str] = []
    if isinstance(pp, dict):
        for pid, label, field in PLATFORM_PRICE_FIELDS:
            v = pp.get(field)
            price_line = f"{int(v):,}원" if isinstance(v, (int, float)) and int(v) > 0 else "없음"
            basis = ""
            pb = row.get("platform_basis") or {}
            if isinstance(pb, dict) and isinstance(pb.get(pid), dict):
                b = str(pb[pid].get("basis") or "")
                if b == "sold_median":
                    basis = " (거래완료)"
                elif b in ("active_realistic_median", "active_lower20_avg"):
                    basis = " (현실가)"
            platform_lines.append(f"- {label}: {price_line}{basis}")

    plat = str(row.get("platform") or "daangn").lower()
    badge = PLATFORM_BADGE_MAIN.get(plat, "[당근마켓]")
    ref_pf = row.get("reference_platform")
    ref_line = ""
    if isinstance(ref_pf, str) and ref_pf.strip():
        rk = ref_pf.strip().lower()
        ref_label = PLATFORM_BADGE_MAIN.get(rk, f"[{html.escape(ref_pf)}]")
        ref_line = f"시세 기준: {ref_label}"

    title_e = html.escape(str(title))
    brand_e = html.escape(str(brand))
    loc_e = html.escape(str(loc))
    summary_e = html.escape(summary) if summary else ""

    lines = [
        "<b>LuxeFinder · 신규 매물</b>",
        badge,
    ]
    if ref_line:
        lines.append(ref_line)
    lines += [
        f"브랜드: {brand_e}",
        f"모델: {title_e}",
        f"당근 가격: {price_s}",
    ]
    if platform_lines:
        lines.append("3사 가격:")
        lines.extend(platform_lines)
    if ref_price_s:
        lines.append(f"기준 시세: <b>{html.escape(ref_price_s)}</b>")
    lines.append(f"수익률: {rate_s}")
    if profit_s:
        lines.append(f"예상 수익: <b>{profit_s}</b>")
    if grade:
        lines.append(f"상태 등급: {html.escape(str(grade))}")
    if proof is not None:
        lines.append(f"증빙: {'확인' if proof else '없음'}")
    if summary_e:
        lines.append(f"요약: {summary_e}")
    if reasoning:
        lines.append(f"분석: {html.escape(reasoning)}")
    if row.get("is_suspicious"):
        lines.append("⚠️ <i>가품·비정상 의심 플래그</i>")
    if loc_e:
        lines.append(f"위치: {loc_e}")
    lines.append("")
    lines.append("아래 <b>인라인 버튼</b>에서 각 플랫폼 링크로 이동할 수 있습니다.")
    if main_url:
        # Telegram HTML에서 href 속성 인코딩 이슈를 피하려고 인라인 버튼을 1순위로 사용하고,
        # 백업은 "텍스트 URL"로만 노출합니다(<>만 이스케이프).
        safe_url = str(main_url).replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"백업 링크: {safe_url}")
    return "\n".join(lines)


def send_listing_alert_telegram(
    token: str,
    chat_id: str,
    row: dict[str, Any],
    *,
    public_api_base: str,
    dedupe: bool = True,
) -> tuple[bool, str]:
    """캡션 + 인라인 키보드; 이미지 URL이 있으면 ``sendPhoto``(프록시 절대 URL 우선)."""
    if dedupe and not _should_send_alert(chat_id, row):
        return True, "duplicate-skipped"
    text = format_listing_alert(row)
    markup = build_telegram_inline_keyboard(row, public_api_base=public_api_base)
    img = row.get("imageUrl") or row.get("image_url") or ""
    photo = _absolute_image_url_for_telegram(str(img), public_api_base)
    if photo and ("/api/image" in photo or photo.startswith("http")):
        ok, msg = send_telegram_photo(
            token,
            chat_id,
            photo,
            text,
            reply_markup=markup,
        )
        if ok:
            return True, msg
        ok2, msg2 = send_telegram_message(token, chat_id, text, reply_markup=markup)
        if not ok2 and dedupe:
            _forget_alert(chat_id, row)
        return ok2, f"photo:{msg}; fallback:{msg2}"
    ok, msg = send_telegram_message(token, chat_id, text, reply_markup=markup)
    if not ok and dedupe:
        _forget_alert(chat_id, row)
    return ok, msg

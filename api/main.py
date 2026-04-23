"""
FastAPI: ``/api/listings`` JSON + ``/api/listings/stream`` SSE + 이미지 프록시
(``GET /api/image``, ``POST /api/image-binary``).

실행 (저장소 루트 LuxeFinder 에서)::

    pip install -r api/requirements.txt
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api.listing_builder import enriched_to_listing_dict
from api.realtime_scrape import run_incremental_cycle, start_incremental_background_loops
from api.settings_routes import SettingsPayload, TelegramTestPayload
from api.settings_store import DEFAULT_CATEGORY_IDS, DashboardSettings, SettingsStore
from api.state_store import ListingState, SSEHub
from api.telegram_notify import send_telegram_message
from api.telegram_notify import send_listing_alert_telegram
from collectors.models import DaangnEnrichedListing, RawListing

app = FastAPI(title="LuxeFinder API", version="0.1.0")

state = ListingState(max_items=80)
hub = SSEHub()
settings_store = SettingsStore(_ROOT / "data" / "luxefinder_settings.json")

IMAGE_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S908N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
)

_IMAGE_ACCEPT = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"

# 당근·CDN이 핫링크 차단할 때 필수 (Referer 없으면 403 등)
DAANGN_UPSTREAM_IMAGE_HEADERS = {
    "User-Agent": IMAGE_UA,
    "Referer": "https://www.daangn.com",
    "Accept": _IMAGE_ACCEPT,
}


def _upstream_image_headers(target_url: str) -> dict[str, str]:
    """호스트별 Referer·UA — 번개/필웨이/구구스·당근 CDN 차단 회피."""
    try:
        host = (urlparse(target_url).hostname or "").lower()
    except ValueError:
        host = ""
    common = {"User-Agent": IMAGE_UA, "Accept": _IMAGE_ACCEPT}
    if "bunjang" in host:
        return {**common, "Referer": "https://m.bunjang.co.kr/"}
    if "feelway" in host:
        return {**common, "Referer": "https://www.feelway.com/"}
    if "gugus" in host:
        return {**common, "Referer": "https://www.gugus.co.kr/"}
    return dict(DAANGN_UPSTREAM_IMAGE_HEADERS)


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def _public_base() -> str:
    return os.environ.get("LUXEFINDER_PUBLIC_API", "http://127.0.0.1:8000").rstrip("/")


@app.on_event("startup")
async def _startup() -> None:
    hub.set_loop(asyncio.get_running_loop())
    # 동적 사이트(당근/번개/필웨이/구구스)는 브라우저 렌더링이 필요한 경우가 많아 기본 ON.
    # (patchright 미설치 시 BaseCollector가 자동으로 정적 fetch로 폴백)
    stealth = _env_bool("LUXEFINDER_SCRAPE_STEALTH", default=False)
    use_proxy = _env_bool("LUXEFINDER_IMAGE_PROXY", default=True)
    prefix = _public_base()
    if not _env_bool("LUXEFINDER_SCRAPE", default=True):
        print("[startup] LUXEFINDER_SCRAPE=0 → 수집 비활성화(시드 데이터만 반환)")
    print(f"[startup] stealth={stealth} image_proxy={use_proxy} public_base={prefix}")

    # 1:1 실시간: 당근 1건 → 3사 병렬 시세(≤5s) → ``listing_ready`` SSE + 즉시 텔레그램.
    if not _env_bool("LUXEFINDER_SCRAPE", default=True):
        from api.scrape_service import _seed_listings

        state.replace_all(_seed_listings())
        await hub.publish({"type": "snapshot", "listings": state.snapshot()})
    else:
        state.replace_all([])

        async def _initial_incremental() -> None:
            try:
                await asyncio.to_thread(
                    run_incremental_cycle,
                    image_proxy_prefix=prefix,
                    use_image_proxy=use_proxy,
                    stealth=stealth,
                    state=state,
                    hub=hub,
                    settings_store=settings_store,
                    public_api_base=prefix,
                )
                print("[startup] incremental scrape cycle dispatched (per-listing workers)")
            except Exception:
                traceback.print_exc()

        asyncio.create_task(_initial_incremental())
        interval = float(os.environ.get("LUXEFINDER_SCRAPE_INTERVAL", "45"))
        start_incremental_background_loops(
            interval_sec=interval,
            state=state,
            hub=hub,
            image_proxy_prefix=prefix,
            use_image_proxy=use_proxy,
            stealth=stealth,
            settings_store=settings_store,
            public_api_base=prefix,
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _allowed_image_host(url: str) -> bool:
    from api.daangn_media import is_listing_image_proxy_allowed

    return is_listing_image_proxy_allowed(url)


def _normalize_image_target(url: str) -> str:
    raw = unquote(url.strip())
    if not raw.startswith("http"):
        raise HTTPException(status_code=400, detail="invalid url")
    if not _allowed_image_host(raw):
        raise HTTPException(status_code=400, detail="host not allowed")
    return raw


async def _fetch_upstream_image(target_url: str) -> tuple[bytes, str]:
    """원본 호스트에서 이미지를 바이트로 읽어 (body, media_type) 반환."""
    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            r = await client.get(target_url, headers=_upstream_image_headers(target_url))
        r.raise_for_status()
        ct = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not ct.startswith("image/"):
            ct = "image/jpeg"
        return r.content, ct
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


def _payload_to_dashboard(p: SettingsPayload) -> DashboardSettings:
    valid_cats = set(DEFAULT_CATEGORY_IDS)
    raw_cats = list(p.selected_categories or [])
    coerced_cats = [x for x in raw_cats if x in valid_cats] or list(DEFAULT_CATEGORY_IDS)
    return DashboardSettings(
        telegram_bot_token=p.telegram_bot_token.strip(),
        telegram_chat_id=p.telegram_chat_id.strip(),
        openai_api_key=p.openai_api_key.strip(),
        telegram_notifications_enabled=p.telegram_notifications_enabled,
        telegram_alert_threshold_percent=float(p.telegram_alert_threshold_percent),
        telegram_min_expected_profit_krw=int(p.telegram_min_expected_profit_krw or 0),
        threshold=float(p.threshold),
        require_warranty=p.require_warranty,
        min_grade=(p.min_grade or "B").strip() or "B",
        selected_brands=list(p.selected_brands),
        selected_categories=coerced_cats,
    )


def _dashboard_to_api_dict(d: DashboardSettings) -> dict[str, object]:
    return {
        "telegramBotToken": d.telegram_bot_token,
        "telegramChatId": d.telegram_chat_id,
        "openaiApiKey": d.openai_api_key,
        "telegram_realtime_enabled": d.telegram_notifications_enabled,
        "telegram_alert_threshold_percent": d.telegram_alert_threshold_percent,
        "telegramMinExpectedProfitKrw": d.telegram_min_expected_profit_krw,
        "threshold": d.threshold,
        "requireWarranty": d.require_warranty,
        "minGrade": d.min_grade,
        "selectedBrands": d.selected_brands,
        "selectedCategoryIds": d.selected_categories,
    }


class ImageBinaryBody(BaseModel):
    """``POST /api/image-binary`` 요청 본문 — 쿼리 길이 제한·엑박 시 대체용."""

    url: str = Field(
        ...,
        min_length=8,
        description="허용 호스트 이미지 원본 https URL (당근·번개·필웨이·구구스 등)",
    )


@app.get("/api/settings")
async def get_settings() -> dict[str, object]:
    return _dashboard_to_api_dict(settings_store.snapshot())


@app.post("/api/settings")
async def post_settings(body: SettingsPayload) -> dict[str, object]:
    settings_store.replace_all(_payload_to_dashboard(body))
    snap = settings_store.snapshot()
    token_ok = bool(snap.telegram_bot_token.strip())
    chat_ok = bool(snap.telegram_chat_id.strip())
    return {
        "ok": True,
        "telegram_bot_token_saved": token_ok,
        "telegram_chat_id_saved": chat_ok,
        "telegram_ready": token_ok and chat_ok,
    }


def _merge_telegram_credentials(
    body: TelegramTestPayload | None,
    snap: DashboardSettings,
) -> tuple[str, str]:
    """요청 본문에 비어 있지 않은 값이 있으면 우선, 아니면 서버 저장값."""
    t_snap = (snap.telegram_bot_token or "").strip()
    c_snap = (snap.telegram_chat_id or "").strip()
    if body is None:
        return t_snap, c_snap
    t_body = body.telegram_bot_token
    c_body = body.telegram_chat_id
    token = t_body.strip() if isinstance(t_body, str) and t_body.strip() else t_snap
    chat = c_body.strip() if isinstance(c_body, str) and c_body.strip() else c_snap
    return token, chat


@app.post("/api/settings/telegram/test")
async def post_telegram_test(
    body: TelegramTestPayload | None = Body(default=None),
) -> dict[str, object]:
    snap = settings_store.snapshot()
    token, chat = _merge_telegram_credentials(body, snap)
    if not token or not chat:
        raise HTTPException(
            status_code=400,
            detail=(
                "서버(settings JSON)에 봇 토큰·채팅 ID가 없습니다. "
                "대시보드 설정에서 입력 후 저장을 눌러 POST /api/settings 가 성공했는지 확인하세요."
            ),
        )
    # 연결 테스트는 HTML 파싱 오류를 피하기 위해 일반 텍스트로 전송
    text = "LuxeFinder\n연결 성공\n대시보드에 저장된 봇·채팅으로 메시지가 도착했습니다."
    ok, msg = await asyncio.to_thread(
        lambda: send_telegram_message(token, chat, text, parse_mode=None),
    )
    if not ok:
        raise HTTPException(status_code=502, detail=msg)
    return {"ok": True}


@app.get("/api/listings")
async def get_listings() -> dict[str, object]:
    return {"listings": state.snapshot()}


@app.get("/api/test-telegram")
async def test_telegram() -> dict[str, object]:
    """
    저장된 settings의 봇 토큰/채팅 ID로, 현재 메모리(state)에 있는 매물 1건을 강제 발송합니다.
    실패 시 원인을 그대로 반환합니다.
    """
    snap = settings_store.snapshot()
    token, chat = (snap.telegram_bot_token or "").strip(), (snap.telegram_chat_id or "").strip()
    if not token or not chat:
        return {"ok": False, "error": "settings에 telegram_bot_token/telegram_chat_id가 비어 있습니다."}
    rows = state.snapshot()
    if not rows:
        return {"ok": False, "error": "현재 state에 매물이 없습니다. /api/listings 를 먼저 확인하세요."}
    def _is_bad_link(u: object) -> bool:
        if not isinstance(u, str):
            return True
        s = u.strip().rstrip("/")
        return s in ("https://www.daangn.com", "https://www.daangn.com/kr", "https://www.daangn.com/kr/buy-sell")

    one = next((r for r in rows if not _is_bad_link(r.get("link"))), rows[0])
    ok, msg = await asyncio.to_thread(
        lambda: send_listing_alert_telegram(token, chat, one, public_api_base=_public_base()),
    )
    if not ok:
        # 터미널에서도 바로 보이게 로깅
        print(f"[telegram:test] FAILED chat_id={chat!r} msg={msg}", file=sys.stderr)
        return {"ok": False, "error": msg}
    print(f"[telegram:test] OK chat_id={chat!r}")
    return {"ok": True, "result": msg, "listing_link": one.get("link"), "platform": one.get("platform")}


@app.get("/api/debug/run-once")
async def debug_run_once() -> dict[str, object]:
    """즉시 1회 수집 실행 후 state/SSE 갱신."""
    stealth = _env_bool("LUXEFINDER_SCRAPE_STEALTH", default=False)
    use_proxy = _env_bool("LUXEFINDER_IMAGE_PROXY", default=True)
    prefix = _public_base()
    try:
        await asyncio.to_thread(
            run_incremental_cycle,
            image_proxy_prefix=prefix,
            use_image_proxy=use_proxy,
            stealth=stealth,
            state=state,
            hub=hub,
            settings_store=settings_store,
            public_api_base=prefix,
            queries=["샤넬 가방", "루이비통 가방"],
        )
        return {"ok": True, "queued": True}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


@app.get("/api/listings/stream")
async def listings_stream() -> StreamingResponse:
    async def event_gen():
        q = await hub.register()
        try:
            snap = state.snapshot()
            yield f"data: {json.dumps({'type': 'snapshot', 'listings': snap}, ensure_ascii=False)}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=120.0)
                    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            await hub.unregister(q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/image")
async def proxy_image(url: str = Query(..., description="원본 이미지 URL (인코딩됨)")) -> Response:
    target = _normalize_image_target(url)
    data, ct = await _fetch_upstream_image(target)
    return Response(
        content=data,
        media_type=ct,
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.post("/api/image-binary")
async def proxy_image_binary(body: ImageBinaryBody) -> Response:
    """
    원본 URL을 JSON으로 받아 이미지 바이너리를 그대로 응답 본문으로 반환합니다.

    ``GET /api/image?url=`` 로 엑박이 나는 경우(쿼리 길이, 중간 프록시 등) 프론트에서
    ``fetch`` + Blob URL 등으로 이 엔드포인트를 사용할 수 있습니다.
    """
    target = _normalize_image_target(body.url)
    data, ct = await _fetch_upstream_image(target)
    return Response(
        content=data,
        media_type=ct,
        headers={
            "Cache-Control": "public, max-age=300",
            "Content-Disposition": 'inline; filename="image"',
        },
    )


@app.post("/api/debug/push-test")
async def push_test_listing() -> dict[str, object]:
    """SSE 파이프라인 확인용 (운영에서는 제거하거나 인증)."""
    stealth = _env_bool("LUXEFINDER_SCRAPE_STEALTH", default=False)
    use_proxy = _env_bool("LUXEFINDER_IMAGE_PROXY", default=True)
    prefix = _public_base()
    raw = RawListing(
        source="daangn",
        model_name="[테스트 푸시] 수동 트리거",
        price_krw=1_000_000,
        status_text="테스트",
        listing_url="https://www.daangn.com/kr/",
        image_url="",
        description_text="테스트",
    )
    en = DaangnEnrichedListing(
        daangn=raw,
        market_price_krw=1_200_000,
        platform_prices_krw={"bunjang": 1_200_000, "gugus": None, "feelway": 1_250_000},
        reference_platform="bunjang",
        platform_listing_urls={
            "bunjang": "https://m.bunjang.co.kr/products/1",
            "gugus": None,
            "feelway": "https://www.feelway.com/",
        },
    )
    one = enriched_to_listing_dict(
        en,
        use_image_proxy=use_proxy,
        image_proxy_prefix=prefix,
    )
    one["id"] = f"test-{int(time.time() * 1000)}"
    full = state.prepend([one])
    await hub.publish({"type": "snapshot", "listings": full})
    return {"ok": True, "count": len(full)}

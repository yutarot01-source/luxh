/**
 * FastAPI `/api/listings` + SSE `/api/listings/stream`.
 * 개발: Vite `server.proxy` 로 `/api` → `127.0.0.1:8000`.
 * 배포: `VITE_API_URL=https://your-api.example.com` (끝 슬래시 없음).
 */
import { ALL_CATEGORY_FILTER_IDS, BAG_BRANDS, BRANDS } from "./constants";
import { resolveReferencePrice } from "./listingDerived";
import { absolutizeDaangnSourceUrl, resolveApiMediaUrl } from "./listingUrls";
import type {
  AnalysisStatus,
  AiStatus,
  Brand,
  Grade,
  Listing,
  ListingSourcePlatform,
  PlatformDetailLinks,
  PlatformPrices,
  Settings,
} from "./types";

const OFFLINE_SAMPLE_IMG = encodeURIComponent("https://www.daangn.com/apple-touch-icon.png");

const _offlineNow = () => new Date().toISOString();

/** FastAPI가 꺼져 있을 때 카드·필터 UI만 확인용 (동기화·알림 없음). */
export function getOfflinePreviewListings(): Listing[] {
  return [
    {
      id: "local-preview-1",
      brand: "샤넬",
      rawTitle: "[오프라인 미리보기] 서버 연결 없이 UI 확인",
      normalizedModel: "[오프라인] 샤넬 클래식 미듐 블랙",
      price: 8_900_000,
      marketPrice: 12_350_000,
      arbitrageRate: 27.94,
      location: "로컬 미리보기",
      postedMinutesAgo: 0,
      imageUrl: resolveApiMediaUrl(`/api/image?url=${OFFLINE_SAMPLE_IMG}`),
      sourceUrl: absolutizeDaangnSourceUrl("/kr/buy-sell/"),
      platform: "daangn",
      platformLinks: {
        bunjang: "https://m.bunjang.co.kr/",
        feelway: "https://www.feelway.com/",
        gogoose: "https://www.gugus.co.kr/",
      },
      status: "완료",
      ai_status: { warranty: true, receipt: true, condition_grade: "A" },
      platform_prices: {
        gogoose_lowest_krw: 12_400_000,
        feelway_lowest_krw: 0,
        bunjang_lowest_krw: 12_350_000,
      },
      reference_platform: "bunjang",
      reference_price_krw: 12_350_000,
      collectedAt: _offlineNow(),
      status_summary: "A급·영수증 동봉",
      is_suspicious: false,
      expected_profit: 3_450_000,
    },
    {
      id: "local-preview-2",
      brand: "루이비통",
      rawTitle: "[오프라인 미리보기] 서버 연결 없이 UI 확인",
      normalizedModel: "[오프라인] LV 네버풀 MM",
      price: 1_250_000,
      marketPrice: 1_580_000,
      arbitrageRate: 20.89,
      location: "로컬 미리보기",
      postedMinutesAgo: 1,
      imageUrl: resolveApiMediaUrl(`/api/image?url=${OFFLINE_SAMPLE_IMG}`),
      sourceUrl: absolutizeDaangnSourceUrl("/kr/buy-sell/"),
      platform: "daangn",
      platformLinks: {
        bunjang: "https://m.bunjang.co.kr/",
        feelway: "https://www.feelway.com/",
        gogoose: "https://www.gugus.co.kr/",
      },
      status: "완료",
      ai_status: { warranty: false, receipt: true, condition_grade: "A" },
      platform_prices: {
        gogoose_lowest_krw: 1_600_000,
        feelway_lowest_krw: 1_590_000,
        bunjang_lowest_krw: 1_580_000,
      },
      reference_platform: "bunjang",
      reference_price_krw: 1_580_000,
      collectedAt: _offlineNow(),
      status_summary: "생얼·캔버스 양호",
      is_suspicious: false,
      expected_profit: 330_000,
    },
  ];
}

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";

function apiPath(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${p}`;
}

const SETTINGS_STORAGE_KEY = "luxefinder-settings-v1";

/** 앱 기본 설정 (localStorage·API 병합 시 베이스). */
export function defaultSettings(): Settings {
  return {
    threshold: 25,
    requireWarranty: true,
    minGrade: "B",
    telegramBotToken: "",
    telegramChatId: "",
    openaiApiKey: "",
    selectedBrands: [...BAG_BRANDS],
    selectedCategoryIds: [...ALL_CATEGORY_FILTER_IDS],
    telegram_realtime_enabled: true,
    telegram_alert_threshold_percent: 25,
    telegramMinExpectedProfitKrw: 0,
  };
}

/**
 * 서버에 값이 있으면 우선. 서버가 `""`이면 로컬에 값이 있으면 유지(아직 POST 전),
 * 로컬도 비었으면 `""`(의도적 삭제 반영).
 */
function pickSecretFromApi(apiVal: unknown, prev: string): string {
  if (typeof apiVal === "string" && apiVal.length > 0) return apiVal;
  if (apiVal === "") return prev.length > 0 ? prev : "";
  return prev;
}

const GRADES: Grade[] = ["S", "A", "B"];

function isGrade(g: unknown): g is Grade {
  return g === "S" || g === "A" || g === "B";
}

/** ``GET /api/settings`` 응답을 ``Settings``에 병합. */
export function mergeSettingsFromApi(prev: Settings, raw: unknown): Settings {
  const o = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const brands = o.selectedBrands;
  let selectedBrands: Brand[];
  if (!Array.isArray(brands)) {
    selectedBrands = prev.selectedBrands;
  } else if (brands.length === 0) {
    selectedBrands = [];
  } else {
    selectedBrands = brands.filter((b): b is Brand => BRANDS.includes(b as Brand)) as Brand[];
  }
  const minGrade = isGrade(o.minGrade) ? o.minGrade : prev.minGrade;
  const rawCats = o.selectedCategoryIds;
  let selectedCategoryIds: string[];
  if (!Array.isArray(rawCats)) {
    selectedCategoryIds = prev.selectedCategoryIds;
  } else {
    const valid = new Set<string>(ALL_CATEGORY_FILTER_IDS);
    selectedCategoryIds = rawCats.map(String).filter((id) => valid.has(id));
    if (selectedCategoryIds.length === 0) {
      selectedCategoryIds = [...ALL_CATEGORY_FILTER_IDS];
    }
  }
  return {
    ...prev,
    telegramBotToken: pickSecretFromApi(o.telegramBotToken, prev.telegramBotToken),
    telegramChatId: pickSecretFromApi(o.telegramChatId, prev.telegramChatId),
    openaiApiKey: pickSecretFromApi(o.openaiApiKey, prev.openaiApiKey),
    telegram_realtime_enabled:
      typeof o.telegram_realtime_enabled === "boolean"
        ? o.telegram_realtime_enabled
        : prev.telegram_realtime_enabled,
    telegram_alert_threshold_percent:
      typeof o.telegram_alert_threshold_percent === "number"
        ? o.telegram_alert_threshold_percent
        : prev.telegram_alert_threshold_percent,
    telegramMinExpectedProfitKrw:
      typeof o.telegramMinExpectedProfitKrw === "number" && Number.isFinite(o.telegramMinExpectedProfitKrw)
        ? Math.max(0, Math.floor(o.telegramMinExpectedProfitKrw))
        : prev.telegramMinExpectedProfitKrw,
    threshold: typeof o.threshold === "number" ? o.threshold : prev.threshold,
    requireWarranty: typeof o.requireWarranty === "boolean" ? o.requireWarranty : prev.requireWarranty,
    minGrade,
    selectedBrands,
    selectedCategoryIds,
  };
}

export function loadSettingsFromLocalStorage(): Settings | null {
  if (typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return null;
    const j = JSON.parse(raw) as unknown;
    if (!j || typeof j !== "object") return null;
    return mergeSettingsFromApi(defaultSettings(), j);
  } catch {
    return null;
  }
}

export function persistSettingsToLocalStorage(s: Settings): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* quota / 사파리 비공개 등 */
  }
}

export async function fetchSettings(): Promise<unknown> {
  const r = await fetch(apiPath("/api/settings"));
  if (!r.ok) {
    throw new Error(`GET /api/settings failed: ${r.status}`);
  }
  return r.json();
}

export interface SaveSettingsResponse {
  ok?: boolean;
  telegram_bot_token_saved?: boolean;
  telegram_chat_id_saved?: boolean;
  telegram_ready?: boolean;
}

export async function saveSettings(s: Settings): Promise<SaveSettingsResponse> {
  const r = await fetch(apiPath("/api/settings"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(s),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `POST /api/settings failed: ${r.status}`);
  }
  return (await r.json()) as SaveSettingsResponse;
}

function formatFastApiDetail(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "";
  const d = (payload as { detail?: unknown }).detail;
  if (Array.isArray(d)) {
    return d
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg?: string }).msg ?? item);
        }
        return typeof item === "string" ? item : JSON.stringify(item);
      })
      .join(" ");
  }
  if (d != null) return String(d);
  return "";
}

/** 저장값 또는 입력 중인 토큰/채팅 ID로 테스트. */
export async function testTelegramSend(overrides?: {
  telegramBotToken?: string;
  telegramChatId?: string;
}): Promise<void> {
  const r = await fetch(apiPath("/api/settings/telegram/test"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      telegramBotToken: overrides?.telegramBotToken ?? null,
      telegramChatId: overrides?.telegramChatId ?? null,
    }),
  });
  if (!r.ok) {
    const raw = await r.text();
    let detail = `${r.status} ${r.statusText}`;
    try {
      const j = JSON.parse(raw) as unknown;
      const parsed = formatFastApiDetail(j);
      if (parsed) detail = parsed;
      else if (raw) detail = raw.slice(0, 400);
    } catch {
      if (raw) detail = raw.slice(0, 400);
    }
    throw new Error(detail);
  }
}

function normalizeGrade(g: unknown): Grade {
  return GRADES.includes(g as Grade) ? (g as Grade) : "A";
}

const SOURCE_PLATFORMS: readonly ListingSourcePlatform[] = [
  "daangn",
  "bunjang",
  "feelway",
  "gugus",
] as const;

function normalizePlatformLinks(raw: unknown): PlatformDetailLinks | undefined {
  const o = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : null;
  if (!o) return undefined;
  const s = (v: unknown): string | undefined =>
    typeof v === "string" && v.trim() ? v.trim() : undefined;
  const links: PlatformDetailLinks = {};
  const bj = s(o.bunjang);
  const fw = s(o.feelway);
  const gg = s(o.gogoose) ?? s(o.gugus);
  if (bj) links.bunjang = bj;
  if (fw) links.feelway = fw;
  if (gg) links.gogoose = gg;
  return Object.keys(links).length ? links : undefined;
}

function normalizePlatformPrices(raw: unknown): PlatformPrices {
  const o = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const num = (v: unknown): number => {
    if (typeof v === "number" && !Number.isNaN(v)) return v < 0 ? 0 : Math.floor(v);
    if (typeof v === "string" && v.trim() !== "") {
      const x = Math.floor(Number(v));
      return !Number.isNaN(x) && x > 0 ? x : 0;
    }
    return 0;
  };
  return {
    gogoose_lowest_krw: num(o.gogoose_lowest_krw),
    feelway_lowest_krw: num(o.feelway_lowest_krw),
    bunjang_lowest_krw: num(o.bunjang_lowest_krw),
  };
}

function mapApiRowToListing(row: unknown): Listing {
  const o = row as Record<string, unknown>;
  const rawAi = o.ai_status as Partial<AiStatus> | undefined;
  const ai: AiStatus = {
    warranty: Boolean(rawAi?.warranty),
    receipt: Boolean(rawAi?.receipt),
    condition_grade: normalizeGrade(rawAi?.condition_grade),
  };
  const platform_prices = normalizePlatformPrices(o.platform_prices);
  const platformLinks = normalizePlatformLinks(o.platformLinks ?? o.platform_links);
  const platRaw = String(o.platform ?? "").trim() as ListingSourcePlatform;
  const platform: ListingSourcePlatform = SOURCE_PLATFORMS.includes(platRaw)
    ? platRaw
    : "daangn";
  const status = (o.status as AnalysisStatus) || "완료";
  const raw = String(o.brand ?? "").trim();
  const brand: Brand = BRANDS.includes(raw as Brand) ? (raw as Brand) : "기타";
  const price = Number(o.price ?? 0);
  const reference_price_krw =
    typeof o.reference_price_krw === "number" && o.reference_price_krw > 0
      ? o.reference_price_krw
      : null;
  const refResolved = resolveReferencePrice({
    platform_prices,
    reference_price_krw,
  });
  const epRaw = o.expected_profit;
  const expected_profit =
    typeof epRaw === "number" && Number.isFinite(epRaw)
      ? Math.max(0, Math.floor(epRaw))
      : refResolved != null
        ? Math.max(0, refResolved - price)
        : 0;

  return {
    id: String(o.id ?? ""),
    brand,
    rawTitle: String(o.rawTitle ?? ""),
    normalizedModel: String(o.normalizedModel ?? o.rawTitle ?? ""),
    nickname: o.nickname != null ? String(o.nickname) : undefined,
    price,
    marketPrice: Number(o.marketPrice ?? o.price ?? 0),
    arbitrageRate: Number(o.arbitrageRate ?? 0),
    status_summary: String(o.status_summary ?? o.statusSummary ?? "").trim() || "—",
    is_suspicious: Boolean(o.is_suspicious ?? o.isSuspicious),
    expected_profit,
    location: String(o.location ?? "—"),
    postedMinutesAgo: Number(o.postedMinutesAgo ?? 0),
    collectedAt: (() => {
      const s = String(o.collectedAt ?? o.collected_at ?? "").trim();
      return s || undefined;
    })(),
    imageUrl: resolveApiMediaUrl(String(o.imageUrl ?? o.image_url ?? "")),
    sourceUrl: absolutizeDaangnSourceUrl(
      String(o.sourceUrl ?? o.source_url ?? o.link ?? o.url ?? "")
    ),
    link: (() => {
      const u = String(o.link ?? o.sourceUrl ?? o.source_url ?? "").trim();
      return u ? absolutizeDaangnSourceUrl(u) : undefined;
    })(),
    platform,
    platformLinks,
    status,
    excludeReason: o.excludeReason != null ? String(o.excludeReason) : undefined,
    ai_status: ai,
    platform_prices,
    reference_platform: (o.reference_platform as Listing["reference_platform"]) ?? null,
    reference_price_krw,
  };
}

export async function fetchListings(): Promise<Listing[]> {
  const r = await fetch(apiPath("/api/listings"));
  if (!r.ok) {
    throw new Error(`GET /api/listings failed: ${r.status}`);
  }
  const j = (await r.json()) as { listings?: unknown[] };
  const rows = Array.isArray(j.listings) ? j.listings : [];
  return rows.map(mapApiRowToListing);
}

/**
 * ``GET /api/listings/stream`` SSE — 스냅샷마다 ``onListings``로 전체 목록 교체.
 * 연결 끊김 시 지수 백오프로 재연결한다.
 */
export function connectListingsSSE(onListings: (listings: Listing[]) => void): () => void {
  let closed = false;
  let es: EventSource | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  let attempt = 0;

  const applyMessage = (ev: MessageEvent<string>) => {
    try {
      const msg = JSON.parse(ev.data) as { type?: string; listings?: unknown[] };
      if (msg.type === "snapshot" && Array.isArray(msg.listings)) {
        onListings(msg.listings.map(mapApiRowToListing));
      }
    } catch {
      /* ignore malformed chunks */
    }
  };

  const connect = () => {
    if (closed) return;
    es?.close();
    es = new EventSource(apiPath("/api/listings/stream"));
    es.onmessage = applyMessage;
    es.onopen = () => {
      attempt = 0;
    };
    es.onerror = () => {
      es?.close();
      es = null;
      if (closed) return;
      attempt += 1;
      const delayMs = Math.min(30_000, 1000 * 2 ** Math.min(attempt, 6));
      retryTimer = window.setTimeout(connect, delayMs);
    };
  };

  connect();

  return () => {
    closed = true;
    window.clearTimeout(retryTimer);
    es?.close();
    es = null;
  };
}

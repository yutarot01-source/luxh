import type { Brand } from "./constants";

export type { Brand };

export type Grade = "S" | "A" | "B";

export type AnalysisStatus =
  | "analyzing"
  | "market_updating"
  | "finalized"
  | "excluded"
  | "분석중"
  | "완료"
  | "제외됨";

/**
 * FastAPI `platform_prices` — 플랫폼별 최저가(원).
 * **0** 은 아직 시세가 없음( UI에서 '확인 중'), **양수**는 해당 플랫폼 최저가.
 */
export interface PlatformPrices {
  gogoose_lowest_krw: number;
  feelway_lowest_krw: number;
  bunjang_lowest_krw: number;
}

export type PlatformId = "gogoose" | "feelway" | "bunjang";

/** API ``platform`` — 본문 매물이 올라온 출처(현재 파이프라인은 당근 기준 ``daangn``). */
export type ListingSourcePlatform = "daangn" | "bunjang" | "feelway" | "gugus";

/** 시세 비교에 쓰인 타 플랫폼 상세 페이지 URL (있을 때만). */
export type PlatformDetailLinks = Partial<Record<PlatformId, string>>;

/** FastAPI `ai_status` — AI 판별 요약 */
export interface AiStatus {
  warranty: boolean;
  receipt: boolean;
  condition_grade: Grade;
}

export interface Listing {
  id: string;
  title?: string;
  description?: string;
  image?: string;
  url?: string;
  brand: Brand;
  model_name?: string;
  normalized_model_name?: string;
  rawTitle: string;
  normalizedModel: string;
  nickname?: string;
  price: number;
  /** @deprecated UI에서는 기준가(reference) 우선 표시. API 동기화용 레거시 호환 */
  marketPrice: number;
  /** 기준가 대비 차익율(%) — FastAPI에서 내려주거나 프론트에서 기준가로 재계산 */
  arbitrageRate: number;
  /** AI·휴리스틱 상태 한 줄 요약(약 15자) */
  status_summary: string;
  /** 본문·가격상 가품 등 의심 징후 */
  is_suspicious: boolean;
  /** 시세(기준가) − 판매가 (원) */
  expected_profit: number;
  location: string;
  postedMinutesAgo: number;
  /** 서버가 이 행을 조립한 시각(UTC ISO). 실시간 수집 표시용 */
  collectedAt?: string;
  imageUrl: string;
  sourceUrl: string;
  /** API ``link`` 와 동일(원문 상세). */
  link?: string;
  /** 수집 출처 — FastAPI ``platform`` */
  platform?: ListingSourcePlatform;
  /** 번개·필웨이·구구스 시세 매칭 상세 URL — FastAPI ``platformLinks`` */
  platformLinks?: PlatformDetailLinks;
  status: AnalysisStatus;
  excludeReason?: string;
  exclude_reason?: string;
  telegram_status?: "sent" | "below_threshold" | "failed" | "pending" | string;
  updated_at?: string;
  created_at?: string;
  daangn_price?: number;
  bunjang_price?: number;
  feelway_price?: number;
  gugus_price?: number;
  bunjang_url?: string;
  feelway_url?: string;
  gugus_url?: string;
  market_reference_price?: number | null;
  market_reference_source?: string | null;
  market_reference_basis?: string | null;
  profit_rate?: number;
  condition_grade?: Grade | string;
  has_authenticity_proof?: boolean;
  reasoning_short?: string;
  platform_basis?: Record<string, { basis?: string; sold_count?: number; sample_count?: number; status?: string; error?: string }>;

  /** FastAPI `ai_status` */
  ai_status: AiStatus;
  /** FastAPI `platform_prices` */
  platform_prices: PlatformPrices;
  /** API가 이미 최저 플랫폼을 골아낸 경우 */
  reference_platform?: PlatformId | null;
  /** API가 명시하는 기준가(원). 없으면 platform_prices 중 최소값 사용 */
  reference_price_krw?: number | null;
}

/** 편의: ai_status와 동일 의미 */
export function listingWarranty(l: Listing): boolean {
  return l.ai_status.warranty;
}

export function listingReceipt(l: Listing): boolean {
  return l.ai_status.receipt;
}

export function listingGrade(l: Listing): Grade {
  return l.ai_status.condition_grade;
}

export interface NotificationLog {
  id: string;
  listingId: string;
  brand: Brand;
  model: string;
  price: number;
  arbitrageRate: number;
  sentAt: Date;
  success: boolean;
}

/**
 * 앱 설정 — FastAPI 예시 필드 매핑:
 * - `alert_threshold` → telegram_alert_threshold_percent
 * - `telegram_notifications_enabled` → telegram_realtime_enabled
 */
export interface Settings {
  threshold: number;
  requireWarranty: boolean;
  minGrade: Grade;
  telegramBotToken: string;
  telegramChatId: string;
  openaiApiKey: string;
  selectedBrands: Brand[];
  /** 대시보드 실루엣 필터 — `LISTING_CATEGORY_FILTERS` 의 `id` */
  selectedCategoryIds: string[];
  /** 실시간 텔레그램 알림 ON/OFF — FastAPI `telegram_notifications_enabled` */
  telegram_realtime_enabled: boolean;
  /** 알림 발송 기준 차익율(%) — FastAPI `alert_threshold` */
  telegram_alert_threshold_percent: number;
  /** 텔레그램 알림: 예상 수익(원) 최소값 — 0이면 미사용 — FastAPI `telegramMinExpectedProfitKrw` */
  telegramMinExpectedProfitKrw: number;
}

/** FastAPI 설정 JSON과 1:1 대응 시 사용 */
export interface AlertPreferencesPayload {
  alert_threshold: number;
  telegram_notifications_enabled: boolean;
}

export function settingsToAlertPayload(s: Settings): AlertPreferencesPayload {
  return {
    alert_threshold: s.telegram_alert_threshold_percent,
    telegram_notifications_enabled: s.telegram_realtime_enabled,
  };
}

/**
 * FastAPI `GET /listings` 한 행과 필드명을 맞춘 예시 타입 (camelCase 변환 전 JSON)
 */
export interface ListingApiResponse {
  id: string;
  brand: string;
  raw_title?: string;
  normalized_model?: string;
  price: number;
  ai_status: AiStatus;
  platform_prices: PlatformPrices;
  reference_price_krw?: number | null;
  reference_platform?: PlatformId | null;
  arbitrage_rate_pct?: number;
  market_price_krw?: number;
  image_url?: string;
  source_url?: string;
  posted_minutes_ago?: number;
  status?: string;
}

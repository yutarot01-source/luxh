import type { Listing, ListingSourcePlatform, PlatformId, PlatformPrices } from "./types";

export const PLATFORM_ORDER: PlatformId[] = ["gogoose", "feelway", "bunjang"];

/** 시세 카드 플랫폼 로고용 (favicon 서비스 도메인). */
export const PLATFORM_FAVICON_DOMAIN: Record<PlatformId, string> = {
  daangn: "www.daangn.com",
  gogoose: "www.gugus.co.kr",
  feelway: "www.feelway.com",
  bunjang: "m.bunjang.co.kr",
};

/** 본문 매물 출처(원문 버튼 옆 로고). */
export const SOURCE_PLATFORM_FAVICON_DOMAIN: Record<ListingSourcePlatform, string> = {
  daangn: "www.daangn.com",
  bunjang: "m.bunjang.co.kr",
  feelway: "www.feelway.com",
  gugus: "www.gugus.co.kr",
};

export function faviconServiceUrl(domain: string): string {
  const d = (domain || "daangn.com").trim();
  return `https://www.google.com/s2/favicons?sz=32&domain=${encodeURIComponent(d)}`;
}

export const PLATFORM_LABEL_KO: Record<PlatformId, string> = {
  daangn: "당근마켓",
  gogoose: "구구스",
  feelway: "필웨이",
  bunjang: "번개장터",
};

export const PLATFORM_PRICE_KEY: Record<PlatformId, keyof PlatformPrices> = {
  daangn: "daangn_market_lowest_krw",
  gogoose: "gogoose_lowest_krw",
  feelway: "feelway_lowest_krw",
  bunjang: "bunjang_lowest_krw",
};

export function formatCollectedLabel(iso: string | undefined): string | null {
  if (!iso?.trim()) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const sec = Math.floor((Date.now() - t) / 1000);
  if (sec < 8) return "방금 수집";
  if (sec < 60) return `${sec}초 전 수집`;
  if (sec < 3600) return `${Math.floor(sec / 60)}분 전 수집`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}시간 전 수집`;
  return `${Math.floor(sec / 86400)}일 전 수집`;
}

export function minPlatformPrice(pp: PlatformPrices): number | null {
  const vals = PLATFORM_ORDER.map((id) => pp[PLATFORM_PRICE_KEY[id]]).filter(
    (n): n is number => n != null && n > 0
  );
  if (!vals.length) return null;
  return Math.min(...vals);
}

/** API가 reference를 주면 우선, 없으면 플랫폼 최저가 중 최소 */
export function resolveReferencePrice(listing: Pick<Listing, "platform_prices" | "reference_price_krw">): number | null {
  if (listing.reference_price_krw != null && listing.reference_price_krw > 0) {
    return listing.reference_price_krw;
  }
  return minPlatformPrice(listing.platform_prices);
}

export function resolveReferencePlatform(
  listing: Pick<Listing, "platform_prices" | "reference_platform" | "reference_price_krw">
): PlatformId | null {
  if (listing.reference_platform) return listing.reference_platform;
  const ref = resolveReferencePrice(listing);
  if (ref == null) return null;
  for (const p of PLATFORM_ORDER) {
    const v = listing.platform_prices[PLATFORM_PRICE_KEY[p]];
    if (typeof v === "number" && v > 0 && v === ref) return p;
  }
  return null;
}

export function arbitrageFromReference(price: number, reference: number): number {
  if (reference <= 0) return 0;
  return ((reference - price) / reference) * 100;
}

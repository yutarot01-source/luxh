/** 당근 원문 링크·이미지 URL 정규화 (상대 경로·별도 API 오리진 대응). */

const DAANGN_ORIGIN = "https://www.daangn.com";

/** ``public/listing-placeholder.svg`` — 이미지 없음·로드 실패 시 공통 플레이스홀더. */
export const LISTING_IMAGE_PLACEHOLDER = "/listing-placeholder.svg";

export function absolutizeDaangnSourceUrl(url: string): string {
  const u = (url || "").trim();
  if (!u) return `${DAANGN_ORIGIN}/kr/`;
  if (u.startsWith("//")) return `https:${u}`;
  if (u.startsWith("/")) return `${DAANGN_ORIGIN}${u}`;
  if (!/^https?:\/\//i.test(u)) return `${DAANGN_ORIGIN}/${u.replace(/^\//, "")}`;
  return u;
}

/** 매물 원문: 이미 절대 URL(번개·필웨이 등)이면 그대로, 당근 상대 경로만 당근 도메인으로 보강. */
export function resolveListingSourceUrl(url: string): string {
  const u = (url || "").trim();
  if (!u) return `${DAANGN_ORIGIN}/kr/`;
  // Absolute URL from any platform: keep as-is.
  if (/^https?:\/\//i.test(u) || u.startsWith("//")) return u.startsWith("//") ? `https:${u}` : u;
  // Relative URL (or path-only) is treated as Daangn path.
  return absolutizeDaangnSourceUrl(u);
}

/** ``/api/image?...`` 는 배포 시 ``VITE_API_URL`` 앞에 붙인다. */
export function resolveApiMediaUrl(pathOrUrl: string): string {
  const apiBase = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";
  const s = (pathOrUrl || "").trim();
  if (!s) return "";
  if (s.startsWith("http://") || s.startsWith("https://")) return s;
  if (s.startsWith("/")) {
    const base = apiBase.replace(/\/$/, "");
    return base ? `${base}${s}` : s;
  }
  return s;
}

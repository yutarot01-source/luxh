/**
 * 필웨이급 하이엔드 브랜드 — 국문 캐논(`ko`) + 영문 표기(`en`) 쌍.
 * 백엔드 `api/brand_constants.BAG_BRAND_DEFS` 와 동일해야 합니다. (소스 순서 = 매칭 우선순위 참고용)
 */
export const BAG_BRAND_PAIRS = [
  { ko: "반클리프아펠", en: "Van Cleef & Arpels" },
  { ko: "메종마르지엘라", en: "Maison Margiela" },
  { ko: "돌체앤가바나", en: "Dolce&Gabbana" },
  { ko: "메종키츠네", en: "Maison Kitsune" },
  { ko: "피어오브갓", en: "Fear of God" },
  { ko: "루이비통", en: "Louis Vuitton" },
  { ko: "미우미우", en: "Miu Miu" },
  { ko: "생로랑", en: "Saint Laurent" },
  { ko: "알렉산더맥퀸", en: "Alexander McQueen" },
  { ko: "보테가베네타", en: "Bottega Veneta" },
  { ko: "브루넬로쿠치넬리", en: "Brunello Cucinelli" },
  { ko: "파텍필립", en: "Patek Philippe" },
  { ko: "크롬하츠", en: "Chrome Hearts" },
  { ko: "디스퀘어드2", en: "Dsquared2" },
  { ko: "발렌시아가", en: "Balenciaga" },
  { ko: "페라가모", en: "Ferragamo" },
  { ko: "에르메스", en: "HERMES" },
  { ko: "프라다", en: "PRADA" },
  { ko: "셀린느", en: "CELINE" },
  { ko: "로에베", en: "Loewe" },
  { ko: "고야드", en: "GOYARD" },
  { ko: "펜디", en: "FENDI" },
  { ko: "토즈", en: "TODS" },
  { ko: "샤넬", en: "CHANEL" },
  { ko: "구찌", en: "GUCCI" },
  { ko: "디올", en: "DIOR" },
  { ko: "지방시", en: "Givenchy" },
  { ko: "끌로에", en: "Chloe" },
  { ko: "몽클레어", en: "Moncler" },
  { ko: "카르티에", en: "Cartier" },
  { ko: "불가리", en: "BVLGARI" },
  { ko: "버버리", en: "Burberry" },
  { ko: "발렌티노", en: "Valentino" },
  { ko: "발망", en: "Balmain" },
  { ko: "베르사체", en: "Versace" },
  { ko: "톰포드", en: "TOM FORD" },
  { ko: "톰브라운", en: "Thom Browne" },
  { ko: "태그호이어", en: "Tag Heuer" },
  { ko: "오메가", en: "OMEGA" },
  { ko: "롤렉스", en: "Rolex" },
  { ko: "브라이틀링", en: "Breitling" },
  { ko: "다미아니", en: "Damiani" },
  { ko: "티파니", en: "TIFFANY & Co" },
  { ko: "로로피아나", en: "Loro Piana" },
  { ko: "막스마라", en: "Max Mara" },
  { ko: "이자벨마랑", en: "Isabel Marant" },
  { ko: "스톤아일랜드", en: "Stone Island" },
  { ko: "씨피컴퍼니", en: "CP Company" },
  { ko: "골든구스", en: "Golden Goose" },
  { ko: "오프화이트", en: "Off White" },
  { ko: "나이키", en: "Nike" },
  { ko: "아미", en: "Ami" },
  { ko: "비비안웨스트우드", en: "Vivienne Westwood" },
  { ko: "우영미", en: "WOOYOUNGMI" },
] as const;

export type CoreBrand = (typeof BAG_BRAND_PAIRS)[number]["ko"];

export const BAG_BRANDS: readonly CoreBrand[] = BAG_BRAND_PAIRS.map((p) => p.ko);

/** API가 알 수 없는 브랜드 문자열을 줄 때 쓰는 폴백 */
export type Brand = CoreBrand | "기타";

/** 필터 칩·설정 다중 선택용 (기타 포함 — 목록에만 표시) */
export const BRANDS: readonly Brand[] = [...BAG_BRANDS, "기타"];

/** 가방/핸드백 실루엣 — 제목·정규화 모델 문자열 키워드 매칭(다중 선택 시 OR) */
export const LISTING_CATEGORY_FILTERS = [
  {
    id: "tote_shoulder",
    label: "토트·숄더",
    keywords: ["토트", "숄더", "숄더백", "쇼퍼", "네버풀", "neverfull", "갈레리아", "galleria", "book tote", "북토트"],
  },
  {
    id: "crossbody",
    label: "크로스·메신저",
    keywords: ["크로스", "크로스백", "메신저", "슬링", "crossbody", "messenger"],
  },
  {
    id: "clutch_chain",
    label: "클러치·WOC·미니",
    keywords: ["클러치", "woc", "체인백", "미니백", "wallet on chain"],
  },
  {
    id: "top_handle",
    label: "탑핸들·사첼",
    keywords: ["탑핸들", "탑 핸들", "사첼", "투핸들", "top handle"],
  },
  {
    id: "backpack",
    label: "백팩·럭색",
    keywords: ["백팩", "배낭", "럭색", "backpack"],
  },
  {
    id: "bucket_hobo",
    label: "버킷·호보·새들",
    keywords: ["버킷", "호보", "호보백", "새들", "saddle", "bucket"],
  },
] as const;

export type CategoryFilterId = (typeof LISTING_CATEGORY_FILTERS)[number]["id"];

export const ALL_CATEGORY_FILTER_IDS: CategoryFilterId[] = LISTING_CATEGORY_FILTERS.map((c) => c.id);

/** 선택 카테고리가 전부이거나 비어 있으면 필터 생략 */
export function listingMatchesSelectedCategories(
  listing: { rawTitle: string; normalizedModel: string },
  selectedIds: readonly string[],
): boolean {
  const n = LISTING_CATEGORY_FILTERS.length;
  if (selectedIds.length === 0 || selectedIds.length >= n) return true;
  const blob = `${listing.rawTitle} ${listing.normalizedModel}`.toLowerCase();
  return selectedIds.some((id) => {
    const def = LISTING_CATEGORY_FILTERS.find((c) => c.id === id);
    return def?.keywords.some((kw) => blob.includes(kw.toLowerCase())) ?? false;
  });
}

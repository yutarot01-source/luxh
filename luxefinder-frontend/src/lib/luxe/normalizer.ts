import type { Brand } from "./types";

// 비정형 애칭 → 정식 모델명 매핑 (확장 가능)
export const NICKNAME_MAP: Record<string, { brand: Brand; model: string }> = {
  "클미": { brand: "샤넬", model: "Classic Medium Flap" },
  "클래식미듐": { brand: "샤넬", model: "Classic Medium Flap" },
  "보이백": { brand: "샤넬", model: "Boy Bag Medium" },
  "WOC": { brand: "샤넬", model: "Wallet on Chain" },
  "마몬트": { brand: "구찌", model: "GG Marmont Small" },
  "마몬트 마틀라세": { brand: "구찌", model: "GG Marmont Matelassé" },
  "디올북토트": { brand: "디올", model: "Book Tote Medium" },
  "레이디디올": { brand: "디올", model: "Lady Dior Medium" },
  "네버풀": { brand: "루이비통", model: "Neverfull MM" },
  "스피디": { brand: "루이비통", model: "Speedy 25" },
  "삭드주르": { brand: "생로랑", model: "Sac de Jour Small" },
  "루루": { brand: "생로랑", model: "LouLou Medium" },
  "버킨": { brand: "에르메스", model: "Birkin 30" },
  "켈리": { brand: "에르메스", model: "Kelly 28" },
  "갈레리아": { brand: "프라다", model: "Galleria Saffiano" },
  "재투": { brand: "보테가베네타", model: "Jodie Mini" },
  "조디": { brand: "보테가베네타", model: "Jodie Medium" },
  "러기지": { brand: "셀린느", model: "Luggage Micro" },
  "생루이": { brand: "고야드", model: "Saint Louis PM" },
  "아르투아": { brand: "고야드", model: "Artois MM" },
  "바게트": { brand: "펜디", model: "Baguette Medium" },
  "피카부": { brand: "펜디", model: "Peekaboo Medium" },
  "아워글래스": { brand: "발렌시아가", model: "Hourglass Small" },
  "앤티고나": { brand: "지방시", model: "Antigona Medium" },
  "세르펜티": { brand: "불가리", model: "Serpenti Forever" },
};

// 부정어 (자동 제외)
export const NEGATIVE_KEYWORDS = [
  "보증서 없음", "보증서없음", "영수증 분실", "영수증없음",
  "단품", "가품문의 사절", "가품의심", "흠집많음", "오염심함",
  "수선필요", "찢어짐", "사용감 매우",
];

// 긍정 시그널
export const WARRANTY_KEYWORDS = ["보증서", "개런티", "게런티카드", "정품보증"];
export const RECEIPT_KEYWORDS = ["영수증", "정품영수증", "구매영수증"];

export function detectExclusion(text: string): string | null {
  const found = NEGATIVE_KEYWORDS.find((k) => text.includes(k));
  return found || null;
}

export function detectWarranty(text: string): boolean {
  return WARRANTY_KEYWORDS.some((k) => text.includes(k));
}

export function detectReceipt(text: string): boolean {
  return RECEIPT_KEYWORDS.some((k) => text.includes(k));
}

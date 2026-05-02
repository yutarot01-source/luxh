import { ExternalLink, ShieldCheck, X } from "lucide-react";
import type { Listing } from "@/lib/luxe/types";
import { cn } from "@/lib/utils";

const won = (v?: number | null) =>
  v == null || Number.isNaN(Number(v)) ? "확인 중" : `${Math.round(Number(v)).toLocaleString("ko-KR")}원`;
const pct = (v?: number | null) => `${Number(v ?? 0).toFixed(1)}%`;
const metricWon = (v?: number | null) => (v && v > 0 ? won(v) : "확인 중");
const metricPct = (v?: number | null) => (v && v > 0 ? pct(v) : "확인 중");
const isExcluded = (listing: Listing) => listing.status === "excluded" || listing.status === "제외됨";
const referenceText = (listing: Listing, v?: number | null) => {
  if (v && v > 0) return won(v);
  if (isExcluded(listing)) return "제외";
  if (listing.status === "finalized" || listing.status === "완료") return "거래완료가 없음";
  return "확인 중";
};

export function ListingDetailModal({ listing, onClose }: { listing: Listing | null; onClose: () => void }) {
  if (!listing) return null;
  const profit = Number(listing.expected_profit ?? 0);
  const rate = Number(listing.profit_rate ?? listing.arbitrageRate ?? 0);
  const gauge = Math.max(0, Math.min(100, rate));
  const img = listing.image || listing.imageUrl;
  const basis = listing.market_reference_basis || listing.market_reference_source || "";
  const basisText = basis === "sold" || basis.includes("sold") ? "거래완료가 기준" : "거래완료가 없음";

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/75 p-2 backdrop-blur-sm sm:items-center sm:p-3"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="my-2 max-h-[calc(100dvh-1rem)] w-full max-w-6xl overflow-y-auto rounded-lg border border-white/10 bg-[#08111f] text-slate-100 shadow-2xl sm:my-0 sm:max-h-[94dvh]">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-white/10 bg-[#08111f]/95 px-5 py-4 backdrop-blur">
          <div>
            <h2 className="text-lg font-black">{listing.title || listing.rawTitle}</h2>
            <p className="text-xs text-slate-400">{listing.brand} · {listing.normalized_model_name || listing.normalizedModel}</p>
          </div>
          <button className="rounded-md p-2 text-slate-400 hover:bg-white/10 hover:text-white" onClick={onClose} type="button">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="grid gap-5 p-5 lg:grid-cols-[420px_1fr]">
          <section className="space-y-4">
            <div className="aspect-square overflow-hidden rounded-lg border border-white/10 bg-[#111827]">
              {img ? <img src={img} alt={listing.title || listing.rawTitle} className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center text-slate-500">이미지 없음</div>}
            </div>
            <InfoGrid listing={listing} />
            <a
              href={listing.url || listing.link || listing.sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-orange-400 px-4 py-3 text-sm font-black text-slate-950 hover:bg-orange-300"
            >
              당근 원본 매물 보기 <ExternalLink className="h-4 w-4" />
            </a>
          </section>

          <section className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3">
              <Metric label="당근 판매가" value={won(listing.daangn_price ?? listing.price)} />
              <Metric label="거래완료 기준 시세" value={referenceText(listing, listing.market_reference_price ?? listing.reference_price_krw)} sub={basisText} />
              <Metric label="기준 시세 수익률" value={metricPct(rate)} sub={metricWon(profit)} tone={profit > 0 ? "good" : "bad"} />
            </div>

            <div className="rounded-lg border border-white/10 bg-[#0b1120] p-4">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400">기준 플랫폼</p>
                  <p className="text-sm font-black text-slate-300">{platformLabel(listing.reference_platform)}</p>
                  <p className="mt-1 text-xs text-slate-500">{basisText}</p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-slate-400">기준 시세 수익률</p>
                  <p className={cn("text-sm font-black", profit > 0 ? "text-emerald-300" : "text-rose-300")}>{metricPct(rate)}</p>
                </div>
                <div className="text-right text-xs text-slate-400">
                  <p>기준 차익 {metricWon(profit)}</p>
                  <p>최저/최고 시세 {won(minPlatform(listing))} / {won(maxPlatform(listing))}</p>
                </div>
              </div>
              <div className="h-3 overflow-hidden rounded-full bg-white/10">
                <div className="h-full rounded-full bg-emerald-400" style={{ width: `${gauge}%` }} />
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <PlatformCard name="번개장터" platform="bunjang" price={listing.bunjang_active_price ?? listing.bunjang_price} url={listing.bunjang_active_url ?? listing.bunjang_url} listing={listing} />
              <PlatformCard name="필웨이" platform="feelway" price={listing.feelway_active_price ?? listing.feelway_price} url={listing.feelway_active_url ?? listing.feelway_url} listing={listing} />
              <PlatformCard name="구구스" platform="gogoose" price={listing.gugus_active_price ?? listing.gugus_price} url={listing.gugus_active_url ?? listing.gugus_url} listing={listing} />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <Panel title="한눈에 요약">
                <p>보증서 {listing.has_authenticity_proof ? "확인" : "미확인"} · 상태 {listing.condition_grade || listing.ai_status.condition_grade}</p>
                <p>기준가: {basisText}</p>
                <p>텔레그램: {listing.telegram_status || "대기 중"}</p>
                {listing.excludeReason || listing.exclude_reason ? <p className="text-rose-300">제외 사유: {listing.excludeReason || listing.exclude_reason}</p> : null}
              </Panel>
              <Panel title="AI 분석 코멘트">
                <p>{listing.reasoning_short || listing.status_summary || "분석 코멘트 대기 중"}</p>
                <p className="mt-2">판매 전략 추천: 기준 시세보다 충분히 낮다면 원본 링크 확인 후 즉시 연락, 증빙 사진 재확인을 권장합니다.</p>
              </Panel>
            </div>

            <Panel title="실시간 추이 차트">
              <div className="relative h-28 overflow-hidden rounded-md bg-[#111827]">
                <svg viewBox="0 0 500 120" className="h-full w-full">
                  <polyline fill="none" stroke="#34d399" strokeWidth="4" points="0,92 70,84 130,88 200,55 280,62 360,35 500,24" />
                  <polyline fill="none" stroke="#60a5fa" strokeWidth="3" strokeDasharray="6 6" points="0,75 90,74 180,70 270,58 390,48 500,42" />
                </svg>
              </div>
            </Panel>
          </section>
        </div>
      </div>
    </div>
  );
}

function platformLabel(platform?: string | null) {
  if (platform === "daangn") return "당근마켓";
  if (platform === "bunjang") return "번개장터";
  if (platform === "feelway") return "필웨이";
  if (platform === "gogoose" || platform === "gugus") return "구구스";
  return "확인 중";
}

function InfoGrid({ listing }: { listing: Listing }) {
  const rows = [
    ["브랜드", listing.brand],
    ["모델명", listing.normalized_model_name || listing.normalizedModel],
    ["상품 상태", listing.condition_grade || listing.ai_status.condition_grade],
    ["구매 연도", "원문 확인"],
    ["구성품", listing.has_authenticity_proof ? "보증서/영수증 언급" : "확인 필요"],
    ["보증서", listing.has_authenticity_proof ? "있음" : "없음"],
    ["사이즈/소재", "원문 확인"],
  ];
  return (
    <div className="grid grid-cols-2 gap-2 text-xs">
      {rows.map(([label, value]) => (
        <div key={label} className="rounded-md border border-white/10 bg-white/[0.04] p-3">
          <p className="text-slate-500">{label}</p>
          <p className="mt-1 font-semibold text-slate-100">{value}</p>
        </div>
      ))}
    </div>
  );
}

function Metric({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "good" | "bad" }) {
  return (
    <div className="rounded-lg border border-white/10 bg-[#0b1120] p-4">
      <p className="text-xs text-slate-400">{label}</p>
      <p className={cn("mt-2 text-sm font-black", tone === "good" && "text-emerald-300", tone === "bad" && "text-rose-300")}>{value}</p>
      {sub ? <p className="mt-1 text-[11px] text-slate-500">{sub}</p> : null}
    </div>
  );
}

function platformPriceText(listing: Listing, platform: "bunjang" | "feelway" | "gogoose", price?: number | null) {
  if (price && price > 0) return won(price);
  if (isExcluded(listing)) return "제외";
  const basis = listing.platform_basis?.[platform];
  if (basis?.status === "failed") return "결과 없음";
  if (basis?.basis === "no_reference" || basis?.status === "ok") return "결과 없음";
  if (listing.status === "finalized") return "결과 없음";
  return "확인 중";
}

function PlatformCard({ name, platform, price, url, listing }: { name: string; platform: "bunjang" | "feelway" | "gogoose"; price?: number | null; url?: string; listing: Listing }) {
  const hasPlatformPrice = Boolean(price && price > 0);
  const activePrice = price || 0;
  const profit = hasPlatformPrice ? activePrice - listing.price : null;
  const rate = profit != null && activePrice ? (profit / activePrice) * 100 : null;
  return (
    <div className="rounded-lg border border-white/10 bg-[#0b1120] p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="font-bold">{name}</p>
        <ShieldCheck className="h-4 w-4 text-emerald-300" />
      </div>
      <p className="text-xs text-slate-500">현재 판매중 가격</p>
      <p className="mt-1 text-sm font-black">{platformPriceText(listing, platform, price)}</p>
      <p className="mt-2 text-xs text-slate-400">판매중 참고차익 {metricWon(profit)} · {metricPct(rate)}</p>
      {url ? (
        <a href={url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-xs font-bold text-sky-300">
          바로가기 <ExternalLink className="h-3 w-3" />
        </a>
      ) : (
        <p className="mt-3 text-xs text-slate-500">시세 확인 중</p>
      )}
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-white/10 bg-[#0b1120] p-4 text-sm text-slate-300">
      <h3 className="mb-3 text-xs font-black uppercase tracking-[0.18em] text-slate-500">{title}</h3>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function platformValues(listing: Listing) {
  return [listing.bunjang_price, listing.feelway_price, listing.gugus_price].filter((v): v is number => Boolean(v && v > 0));
}
const minPlatform = (listing: Listing) => {
  const vals = platformValues(listing);
  return vals.length ? Math.min(...vals) : null;
};
const maxPlatform = (listing: Listing) => {
  const vals = platformValues(listing);
  return vals.length ? Math.max(...vals) : null;
};

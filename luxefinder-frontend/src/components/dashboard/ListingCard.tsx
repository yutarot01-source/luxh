import { AlertTriangle, CheckCircle2, Clock, ExternalLink, Send, TrendingDown, TrendingUp } from "lucide-react";
import type { Listing } from "@/lib/luxe/types";
import { cn } from "@/lib/utils";

const won = (v?: number | null) =>
  v == null || Number.isNaN(Number(v)) ? "확인 중" : `${Math.round(Number(v)).toLocaleString("ko-KR")}원`;
const pct = (v?: number | null) => `${Number(v ?? 0).toFixed(1)}%`;

function ageLabel(listing: Listing) {
  const raw = listing.created_at || listing.collectedAt;
  if (!raw) return "방금 전";
  const diff = Math.max(0, Math.floor((Date.now() - Date.parse(raw)) / 1000));
  if (diff < 60) return `${diff}초 전`;
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
  return `${Math.floor(diff / 3600)}시간 전`;
}

function statusText(listing: Listing) {
  if (listing.status === "finalized" || listing.status === "완료") return "finalized";
  if (listing.status === "market_updating") return "market_updating";
  if (listing.status === "excluded" || listing.status === "제외됨") return "excluded";
  return "analyzing";
}

function telegramText(v?: string) {
  if (v === "sent") return "알림 발송됨";
  if (v === "below_threshold") return "조건 미달";
  if (v === "failed") return "발송 실패";
  return "대기 중";
}

export function ListingCard({ listing, onClick }: { listing: Listing; onClick: () => void }) {
  const profit = Number(listing.expected_profit ?? 0);
  const rate = Number(listing.profit_rate ?? listing.arbitrageRate ?? 0);
  const positive = profit >= 0;
  const basis = listing.market_reference_basis || listing.market_reference_source || "";
  const basisLabel = basis.includes("sold") ? "거래완료가 기준" : basis ? "판매중 가격 참고" : "기준 산정 중";
  const img = listing.image || listing.imageUrl;

  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex h-full min-h-[360px] w-full flex-col overflow-hidden rounded-lg border border-white/10 bg-[#111827]/90 text-left shadow-[0_12px_40px_rgba(0,0,0,0.25)] transition duration-200 hover:-translate-y-1 hover:border-emerald-400/40 hover:shadow-[0_20px_54px_rgba(16,185,129,0.16)]"
    >
      <div className="relative aspect-[4/3] overflow-hidden bg-[#182033]">
        {img ? (
          <img
            src={img}
            alt={listing.title || listing.rawTitle}
            className="h-full w-full object-cover transition duration-300 group-hover:scale-105"
            onError={(e) => {
              e.currentTarget.style.display = "none";
            }}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-slate-500">이미지 대기</div>
        )}
        <div className="absolute left-3 top-3 rounded-full bg-emerald-400 px-2 py-1 text-[10px] font-black text-slate-950">NEW</div>
        <div className="absolute right-3 top-3 rounded-full bg-black/70 px-2 py-1 text-[10px] font-semibold text-white">{ageLabel(listing)}</div>
      </div>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-center justify-between gap-2">
          <span className="rounded-full bg-orange-400/15 px-2 py-1 text-[10px] font-bold text-orange-300">당근 {won(listing.daangn_price ?? listing.price)}</span>
          <span className="flex items-center gap-1 rounded-full bg-slate-900 px-2 py-1 text-[10px] text-slate-300">
            <Clock className="h-3 w-3" /> {statusText(listing)}
          </span>
        </div>

        <div>
          <h3 className="line-clamp-2 text-sm font-bold leading-5 text-white">{listing.title || listing.rawTitle}</h3>
          <p className="mt-1 line-clamp-1 text-xs text-slate-400">
            {listing.brand} · {listing.normalized_model_name || listing.normalizedModel}
          </p>
        </div>

        <div className="grid gap-2 text-xs">
          <PriceRow label="번개장터" value={listing.bunjang_price} platform="bunjang" listing={listing} />
          <PriceRow label="필웨이" value={listing.feelway_price} platform="feelway" listing={listing} />
          <PriceRow label="구구스" value={listing.gugus_price} platform="gogoose" listing={listing} />
        </div>

        <div className="mt-auto rounded-lg border border-white/10 bg-[#0b1120] p-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-slate-400">예상 시세차익</span>
            <span className={cn("flex items-center gap-1 text-sm font-black", positive ? "text-emerald-300" : "text-rose-300")}>
              {positive ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
              {won(profit)}
            </span>
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span className="text-[11px] text-slate-500">{basisLabel}</span>
            <span className={cn("text-lg font-black", positive ? "text-emerald-300" : "text-rose-300")}>{pct(rate)}</span>
          </div>
        </div>

        <div className="flex items-center justify-between text-[11px] text-slate-400">
          <span className="flex items-center gap-1">
            {listing.has_authenticity_proof ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-300" /> : <AlertTriangle className="h-3.5 w-3.5 text-amber-300" />}
            보증서 {listing.has_authenticity_proof ? "확인" : "미확인"} · {listing.condition_grade || listing.ai_status.condition_grade}
          </span>
          <span className="flex items-center gap-1">
            <Send className="h-3.5 w-3.5" /> {telegramText(listing.telegram_status)}
          </span>
        </div>

        {listing.excludeReason || listing.exclude_reason ? (
          <p className="rounded-md bg-rose-500/10 p-2 text-[11px] text-rose-200">{listing.excludeReason || listing.exclude_reason}</p>
        ) : null}
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-sky-300">
          상세 분석 보기 <ExternalLink className="h-3 w-3" />
        </span>
      </div>
    </button>
  );
}

function platformPriceText(listing: Listing, platform: "bunjang" | "feelway" | "gogoose", value?: number | null) {
  if (value && value > 0) return won(value);
  const basis = listing.platform_basis?.[platform];
  if (basis?.status === "failed") return "조회 실패";
  if (basis?.basis === "no_reference" || basis?.status === "ok") return "결과 없음";
  if (listing.status === "finalized") return "결과 없음";
  return "확인 중";
}

function PriceRow({ label, value, platform, listing }: { label: string; value?: number | null; platform: "bunjang" | "feelway" | "gogoose"; listing: Listing }) {
  return (
    <div className="flex items-center justify-between rounded-md bg-white/[0.04] px-3 py-2">
      <span className="text-slate-400">{label}</span>
      <span className="font-semibold text-slate-100">{platformPriceText(listing, platform, value)}</span>
    </div>
  );
}

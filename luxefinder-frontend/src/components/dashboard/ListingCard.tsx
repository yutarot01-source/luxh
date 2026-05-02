import { AlertTriangle, CheckCircle2, ExternalLink, Heart, Send, TrendingDown, TrendingUp } from "lucide-react";
import type { Listing } from "@/lib/luxe/types";
import { cn } from "@/lib/utils";

const won = (v?: number | null) =>
  v == null || Number.isNaN(Number(v)) ? "확인 중" : `${Math.round(Number(v)).toLocaleString("ko-KR")}원`;
const pct = (v?: number | null) => `${Number(v ?? 0).toFixed(1)}%`;
const metricWon = (v?: number | null) => (v && v > 0 ? won(v) : "확인 중");
const metricPct = (v?: number | null) => (v && v > 0 ? pct(v) : "확인 중");
const isExcluded = (listing: Listing) => listing.status === "excluded" || listing.status === "제외됨";

function statusText(listing: Listing) {
  if (listing.status === "finalized" || listing.status === "완료") return "완료";
  if (listing.status === "market_updating") return "시세 확인";
  if (listing.status === "excluded" || listing.status === "제외됨") return "제외";
  return "분석 중";
}

function telegramText(v?: string) {
  if (v === "sent") return "발송";
  if (v === "skipped_condition" || v === "below_threshold") return "조건 미달";
  if (v === "failed") return "대기";
  return "대기";
}

export function ListingCard({
  listing,
  onClick,
  isFavorite = false,
  onToggleFavorite,
}: {
  listing: Listing;
  onClick: () => void;
  isFavorite?: boolean;
  onToggleFavorite?: () => void;
}) {
  const profit = Number(listing.expected_profit ?? 0);
  const rate = Number(listing.profit_rate ?? listing.arbitrageRate ?? 0);
  const positive = profit > 0;
  const img = listing.image || listing.imageUrl;
  const model = listing.normalized_model_name || listing.normalizedModel || listing.model_name;
  const sourceHref = listing.link || listing.sourceUrl || listing.url;
  const referencePrice = listing.market_reference_price ?? listing.reference_price_krw ?? null;

  return (
    <article className="group flex h-full min-h-[390px] flex-col overflow-hidden rounded-lg border border-white/10 bg-[#0b1120] text-left shadow-[0_12px_34px_rgba(0,0,0,0.18)] transition duration-200 hover:-translate-y-1 hover:border-white/20 hover:shadow-[0_20px_48px_rgba(0,0,0,0.28)]">
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
          <div className="flex h-full items-center justify-center text-xs text-slate-500">이미지 확인 중</div>
        )}
        <span className="absolute left-3 top-3 rounded-full bg-black/65 px-2.5 py-1 text-[10px] font-bold text-white">{statusText(listing)}</span>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onToggleFavorite?.();
          }}
          className={cn(
            "absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full border border-white/15 bg-black/55 text-white transition hover:bg-black/75",
            isFavorite && "border-rose-300/70 bg-rose-400/20 text-rose-200",
          )}
          aria-label="관심매물"
        >
          <Heart className={cn("h-4 w-4", isFavorite && "fill-current")} />
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-4 p-4">
        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="rounded-md border border-white/10 px-2 py-1 text-[11px] font-bold text-slate-300">{listing.brand}</span>
          </div>
          <h3 className="line-clamp-2 text-sm font-bold leading-5 text-white">{listing.title || listing.rawTitle}</h3>
          <p className="mt-1 line-clamp-1 text-xs text-slate-400">{model}</p>
        </div>

        <div className="rounded-lg border border-white/10 bg-[#07111f] p-4">
          <p className="text-[11px] font-semibold text-slate-500">예상 차익</p>
          <div className="mt-1 flex items-end justify-between gap-3">
            <span className={cn("text-sm font-black leading-none", positive ? "text-sky-300" : "text-slate-300")}>{metricWon(profit)}</span>
            <span className={cn("flex items-center gap-1 text-sm font-black", positive ? "text-emerald-300" : "text-rose-300")}>
              {positive ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
              {metricPct(rate)}
            </span>
          </div>
          <div className="mt-3 border-t border-white/10 pt-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[11px] font-semibold text-slate-500">기준 시세 차익</span>
              <span className="text-[11px] text-slate-500">{platformLabel(listing.reference_platform)}</span>
            </div>
            <div className="mt-1 flex items-end justify-between gap-3">
              <span className={cn("text-sm font-black", profit > 0 ? "text-sky-300" : "text-slate-400")}>{metricWon(profit)}</span>
              <span className={cn("text-xs font-black", profit > 0 ? "text-sky-300" : "text-slate-400")}>{metricPct(rate)}</span>
            </div>
          </div>
        </div>

        <div className="grid gap-2 text-xs">
          <PriceRow label="당근마켓 판매가" value={listing.daangn_price ?? listing.price} />
          <PriceRow label="거래완료 기준 시세" value={referencePrice} listing={listing} reference />
          <PriceRow label="번개장터 판매중" value={listing.bunjang_active_price ?? listing.bunjang_price} platform="bunjang" listing={listing} />
          <PriceRow label="필웨이 판매중" value={listing.feelway_active_price ?? listing.feelway_price} platform="feelway" listing={listing} />
          <PriceRow label="구구스 판매중" value={listing.gugus_active_price ?? listing.gugus_price} platform="gogoose" listing={listing} />
        </div>

        <div className="mt-auto flex items-center justify-between gap-3 text-[11px] text-slate-400">
          <span className="flex min-w-0 items-center gap-1">
            {listing.has_authenticity_proof ? <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-300" /> : <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-300" />}
            <span className="truncate">보증서 {listing.has_authenticity_proof ? "확인" : "미확인"} · {listing.condition_grade || listing.ai_status.condition_grade}</span>
          </span>
          <span className="flex shrink-0 items-center gap-1">
            <Send className="h-3.5 w-3.5" /> {telegramText(listing.telegram_status)}
          </span>
        </div>

        {listing.excludeReason || listing.exclude_reason ? (
          <p className="rounded-md bg-rose-500/10 p-2 text-[11px] text-rose-200">{listing.excludeReason || listing.exclude_reason}</p>
        ) : null}

        <div className="grid grid-cols-2 gap-2">
          {sourceHref ? (
            <a
              href={sourceHref}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] text-xs font-bold text-slate-200 transition hover:bg-white/[0.08]"
            >
              원문 보기 <ExternalLink className="h-3.5 w-3.5" />
            </a>
          ) : (
            <span className="inline-flex h-9 items-center justify-center rounded-lg border border-white/5 bg-white/[0.02] text-xs font-semibold text-slate-500">
              원문 없음
            </span>
          )}
          <button
            type="button"
            onClick={onClick}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/[0.04] text-xs font-bold text-sky-200 transition hover:bg-white/[0.08]"
          >
            상세 분석 <ExternalLink className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </article>
  );
}

function platformLabel(platform?: string | null) {
  if (platform === "daangn") return "당근마켓";
  if (platform === "bunjang") return "번개장터";
  if (platform === "feelway") return "필웨이";
  if (platform === "gogoose" || platform === "gugus") return "구구스";
  return "확인 중";
}

function platformPriceText(listing: Listing, platform: "bunjang" | "feelway" | "gogoose", value?: number | null) {
  if (value && value > 0) return won(value);
  if (isExcluded(listing)) return "제외";
  const basis = listing.platform_basis?.[platform];
  if (basis?.status === "failed") return "결과 없음";
  if (basis?.basis === "no_reference" || basis?.status === "ok") return "결과 없음";
  if (listing.status === "finalized") return "결과 없음";
  return "확인 중";
}

function referencePriceText(listing: Listing, value?: number | null) {
  if (value && value > 0) return won(value);
  if (isExcluded(listing)) return "제외";
  if (listing.status === "finalized" || listing.status === "완료") return "거래완료가 없음";
  return "확인 중";
}

function PriceRow({ label, value, platform, listing, reference = false }: { label: string; value?: number | null; platform?: "bunjang" | "feelway" | "gogoose"; listing?: Listing; reference?: boolean }) {
  const text = platform && listing ? platformPriceText(listing, platform, value) : reference && listing ? referencePriceText(listing, value) : won(value);
  return (
    <div className="flex items-center justify-between rounded-md border border-white/5 bg-white/[0.03] px-3 py-2">
      <span className="text-slate-400">{label}</span>
      <span className="font-semibold text-slate-100">{text}</span>
    </div>
  );
}

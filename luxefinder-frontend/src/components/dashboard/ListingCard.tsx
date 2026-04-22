import { useState } from "react";
import { Heart, ExternalLink, Send, ShieldCheck, Receipt, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Listing, ListingSourcePlatform, PlatformId } from "@/lib/luxe/types";
import { listingGrade, listingReceipt, listingWarranty } from "@/lib/luxe/types";
import {
  PLATFORM_FAVICON_DOMAIN,
  PLATFORM_LABEL_KO,
  PLATFORM_ORDER,
  PLATFORM_PRICE_KEY,
  SOURCE_PLATFORM_FAVICON_DOMAIN,
  faviconServiceUrl,
  formatCollectedLabel,
  resolveReferencePlatform,
  resolveReferencePrice,
} from "@/lib/luxe/listingDerived";
import { LISTING_IMAGE_PLACEHOLDER, resolveApiMediaUrl, resolveListingSourceUrl } from "@/lib/luxe/listingUrls";

interface Props {
  listing: Listing;
  meetsAlertCriteria: boolean;
  onSendTelegram: (l: Listing) => void;
}

const ICON_BADGE =
  "flex items-center justify-center rounded-md border border-border bg-background shadow-inner";

const gradeStyle: Record<string, string> = {
  S: "bg-grade-s/15 text-grade-s ring-1 ring-grade-s/35",
  A: "bg-grade-a/15 text-grade-a ring-1 ring-grade-a/35",
  B: "bg-grade-b/15 text-grade-b ring-1 ring-grade-b/35",
};

export function ListingCard({ listing, meetsAlertCriteria, onSendTelegram }: Props) {
  const grade = listingGrade(listing);
  const ref = resolveReferencePrice(listing);
  const refPlatform = resolveReferencePlatform(listing);
  const minutes = listing.postedMinutesAgo;
  const timeAgo =
    minutes < 60 ? `${minutes}분 전` : `${Math.floor(minutes / 60)}시간 전`;
  const collectedLabel = formatCollectedLabel(listing.collectedAt);
  const articleUrl = (listing.link ?? listing.sourceUrl ?? "").trim();
  const sourceHref = resolveListingSourceUrl(articleUrl);
  const mainPlatform = listing.platform ?? "daangn";
  const imageSrc = resolveApiMediaUrl(listing.imageUrl);
  const profitStr = listing.expected_profit.toLocaleString("ko-KR");

  return (
    <article className="group flex h-full min-h-[520px] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-card transition-all hover:-translate-y-0.5 hover:shadow-card-hover">
      <div className="relative aspect-square w-full shrink-0 overflow-hidden bg-muted">
        <ListingImage src={imageSrc} alt={listing.normalizedModel} />

        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/25 via-transparent to-transparent" />

        <div className="pointer-events-none absolute left-3 top-3 z-[1]">
          <span className={cn(ICON_BADGE, "h-10 w-10")}>
            <img
              src={faviconServiceUrl(SOURCE_PLATFORM_FAVICON_DOMAIN[mainPlatform])}
              alt=""
              width={22}
              height={22}
              className="h-5 w-5 opacity-75 brightness-[0.92] contrast-[0.95] saturate-[0.72]"
            />
          </span>
        </div>

        <div className="pointer-events-none absolute right-3 top-3 z-[1] max-w-[60%] text-right">
          <p className="text-[10px] font-semibold text-foreground/80">예상 수익</p>
          <p className="text-lg font-black leading-tight text-primary drop-shadow-sm sm:text-xl">
            +{profitStr}원
          </p>
        </div>

        {listing.is_suspicious ? (
          <span className="absolute left-3 top-[3.35rem] z-[1] max-w-[calc(100%-1.5rem)] rounded-md border border-destructive/35 bg-destructive/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-destructive shadow-md backdrop-blur-sm">
            가품·비정상 의심
          </span>
        ) : null}

        <span
          className={cn(
            "absolute bottom-3 right-3 z-[1] rounded-md px-2 py-1 text-[10px] font-bold backdrop-blur-sm",
            gradeStyle[grade],
          )}
        >
          {grade}급
        </span>

        <div className="pointer-events-none absolute bottom-12 left-3 right-3 flex flex-wrap gap-1.5">
          <AiChip
            ok={listingWarranty(listing)}
            icon={<ShieldCheck className="h-3 w-3" />}
            label="보증서"
          />
          <AiChip
            ok={listingReceipt(listing)}
            icon={<Receipt className="h-3 w-3" />}
            label="영수증"
          />
        </div>

        {meetsAlertCriteria && (
          <span className="absolute bottom-3 left-3 z-[1] inline-flex items-center gap-1 rounded-full bg-primary px-2.5 py-1 text-[10px] font-bold text-primary-foreground shadow-glow">
            🔔 알림 대상
          </span>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-2 p-4">
        <div className="min-h-0 flex-1 space-y-2">
          <h3 className="line-clamp-2 text-sm font-bold leading-snug text-foreground">
            {listing.normalizedModel}
          </h3>
          <p className="text-xs text-muted-foreground">
            <span className="text-foreground/70">원문:</span> {listing.rawTitle}
          </p>

          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <MapPin className="h-3 w-3" />
            <span>{listing.location}</span>
            <span>·</span>
            <span>{timeAgo}</span>
            {collectedLabel ? (
              <>
                <span>·</span>
                <span className="font-semibold text-primary">{collectedLabel}</span>
              </>
            ) : null}
          </div>

          {listing.status_summary && listing.status_summary !== "—" ? (
            <p className="line-clamp-1 rounded-lg bg-secondary px-2 py-2 text-[11px] font-medium text-muted-foreground">
              상태 · {listing.status_summary}
            </p>
          ) : null}

          <PlatformCompareStrip listing={listing} refPlatform={refPlatform} />

          <p className="text-[10px] leading-relaxed text-muted-foreground">
            차익율은 세 플랫폼 중 <span className="font-medium text-foreground/85">최저 시세(기준가)</span>를 분모로
            계산합니다.
          </p>
        </div>

        <div className="mt-auto grid shrink-0 grid-cols-2 gap-2 border-t border-border pt-3">
          <Button
            asChild
            variant="outline"
            size="sm"
            className="h-9 text-xs"
          >
            <a
              href={sourceHref}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center gap-1.5"
            >
              <span className={cn(ICON_BADGE, "h-6 w-6")}>
                <img
                  src={faviconServiceUrl(SOURCE_PLATFORM_FAVICON_DOMAIN[mainPlatform])}
                  alt=""
                  width={14}
                  height={14}
                  className="h-3.5 w-3.5 opacity-70 saturate-[0.85]"
                />
              </span>
              <ExternalLink className="h-3 w-3 shrink-0 opacity-70" />
              원문
            </a>
          </Button>
          <Button
            size="sm"
            onClick={() => onSendTelegram(listing)}
            className="h-9 bg-primary text-xs hover:bg-primary/90"
          >
            <Send className="mr-1 h-3 w-3" />
            전송
          </Button>
        </div>
      </div>
    </article>
  );
}

function ListingImage({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false);
  const usePlaceholder = !src.trim() || failed;
  const effectiveSrc = usePlaceholder ? LISTING_IMAGE_PLACEHOLDER : src;

  return (
    <img
      src={effectiveSrc}
      alt={usePlaceholder ? "" : alt}
      loading="lazy"
      width={800}
      height={800}
      className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.02]"
      onError={() => setFailed((prev) => (prev ? prev : true))}
    />
  );
}

function AiChip({ ok, icon, label }: { ok: boolean; icon: React.ReactNode; label: string }) {
  return (
    <span
      className={cn(
        "pointer-events-none inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold ring-1 backdrop-blur-sm",
        ok
          ? "bg-emerald-600/15 text-emerald-700 ring-emerald-600/25"
          : "bg-background/70 text-subtle ring-border/70",
      )}
    >
      {icon}
      {label} {ok ? "있음" : "없음"}
    </span>
  );
}

function PlatformCompareStrip({
  listing,
  refPlatform,
}: {
  listing: Listing;
  refPlatform: PlatformId | null;
}) {
  return (
    <div className="rounded-[var(--radius)] border border-border/70 bg-background/80 p-2.5">
      <p className="mb-2 text-[9px] font-semibold uppercase tracking-[0.2em] text-subtle">시세 비교</p>
      <div className="flex gap-2 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {PLATFORM_ORDER.map((pid) => {
          const amount = listing.platform_prices[PLATFORM_PRICE_KEY[pid]];
          const isRef = refPlatform === pid && amount != null && amount > 0;
          const detailHref = listing.platformLinks?.[pid]?.trim();
          return (
            <div
              key={pid}
              className={cn(
                "min-w-[5.25rem] shrink-0 rounded-md border px-1.5 py-1.5 text-center transition-colors",
                isRef
                  ? "border-primary/25 bg-primary-soft/70 shadow-sm ring-1 ring-primary/10"
                  : "border-border/70 bg-card",
              )}
            >
              <p className="flex items-center justify-center gap-1 text-[8px] font-semibold text-subtle">
                <span className={cn(ICON_BADGE, "h-6 w-6")}>
                  <img
                    src={faviconServiceUrl(PLATFORM_FAVICON_DOMAIN[pid])}
                    alt=""
                    width={12}
                    height={12}
                    className="h-2.5 w-2.5 opacity-70 saturate-[0.85]"
                  />
                </span>
                {PLATFORM_LABEL_KO[pid]}
              </p>
              <p className="mt-0.5 font-display text-[10px] font-bold tracking-wide text-foreground">
                {amount != null && amount > 0 ? `${(amount / 10_000).toFixed(0)}만` : "—"}
              </p>
              {isRef && (
                <p className="mt-0.5 rounded-sm border border-primary/20 bg-background/70 px-1 py-0.5 text-[7px] font-semibold uppercase tracking-wider text-primary">
                  기준가
                </p>
              )}
              {detailHref ? (
                <a
                  href={detailHref}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-0.5 inline-flex items-center justify-center gap-0.5 text-[7px] font-semibold text-subtle underline-offset-2 hover:text-primary hover:underline"
                >
                  <ExternalLink className="h-2 w-2" />
                  원문
                </a>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

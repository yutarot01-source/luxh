import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  CheckCircle2,
  Heart,
  LayoutDashboard,
  ListChecks,
  Menu,
  Search,
  Settings,
  SlidersHorizontal,
} from "lucide-react";
import { ListingCard } from "@/components/dashboard/ListingCard";
import { ListingDetailModal } from "@/components/dashboard/ListingDetailModal";
import { SettingsDrawer } from "@/components/dashboard/SettingsDrawer";
import { useListingsSSE } from "@/hooks/useListingsSSE";
import {
  defaultSettings,
  fetchSettings,
  loadSettingsFromLocalStorage,
  mergeSettingsFromApi,
  persistSettingsToLocalStorage,
  saveSettings,
  testTelegramSend,
} from "@/lib/luxe/api";
import type { Listing, Settings as SettingsType } from "@/lib/luxe/types";
import { toast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

type View = "dashboard" | "listings" | "favorites";
type SortMode = "recent" | "rate" | "profit" | "price";

const BRANDS = ["샤넬", "루이비통", "구찌"] as const;
const RATES = [10, 20, 30, 50] as const;
const GRADES = ["S", "A", "B"] as const;
const LIST_PAGE_SIZE = 16;
const FILTER_STORAGE_KEY = "luxefinder.ui.filters.v1";
const FAVORITES_STORAGE_KEY = "luxefinder.ui.favorites.v1";

type PersistedFilters = {
  query: string;
  brandFilters: string[];
  minRate: number | null;
  minPrice: string;
  maxPrice: string;
  gradeFilters: string[];
  requireProof: boolean;
  sort: SortMode;
};

const defaultFilterState: PersistedFilters = {
  query: "",
  brandFilters: [],
  minRate: null,
  minPrice: "",
  maxPrice: "",
  gradeFilters: [],
  requireProof: false,
  sort: "rate",
};

const won = (v?: number | null) =>
  v == null || Number.isNaN(Number(v)) ? "확인 중" : `${Math.round(Number(v)).toLocaleString("ko-KR")}원`;
const pct = (v?: number | null) => (v == null || Number.isNaN(Number(v)) ? "확인 중" : `${Number(v).toFixed(1)}%`);
const metricWon = (v?: number | null) => (v && v > 0 ? won(v) : "확인 중");
const metricPct = (v?: number | null) => (v && v > 0 ? pct(v) : "확인 중");
const referenceWon = (listing: Listing, v?: number | null) => {
  if (v && v > 0) return won(v);
  if (isExcluded(listing)) return "제외";
  if (listing.status === "finalized" || listing.status === "완료") return "거래완료가 없음";
  return "확인 중";
};

function useDebouncedValue<T>(value: T, delay = 300) {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(id);
  }, [value, delay]);

  return debounced;
}

function searchBlob(listing: Listing) {
  return [
    listing.title,
    listing.rawTitle,
    listing.model_name,
    listing.normalized_model_name,
    listing.normalizedModel,
    listing.brand,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function isExcluded(listing: Listing) {
  return listing.status === "excluded" || listing.status === "제외됨";
}

function listingRate(listing: Listing) {
  return Number(listing.profit_rate ?? listing.arbitrageRate ?? 0);
}

function listingProfit(listing: Listing) {
  return Number(listing.expected_profit ?? 0);
}

function listingOpportunityProfit(listing: Listing) {
  return listingProfit(listing);
}

function listingPrice(listing: Listing) {
  return Number(listing.daangn_price ?? listing.price ?? 0);
}

function listingGrade(listing: Listing) {
  return String(listing.condition_grade || listing.ai_status?.condition_grade || "").toUpperCase();
}

function listingTime(listing: Listing) {
  return Date.parse(listing.created_at || listing.collectedAt || "0");
}

function platformPrice(listing: Listing, platform: "daangn" | "bunjang" | "feelway" | "gogoose") {
  if (platform === "daangn") return listing.daangn_price ?? listing.price ?? 0;
  if (platform === "bunjang") return listing.bunjang_active_price ?? listing.bunjang_price ?? 0;
  if (platform === "feelway") return listing.feelway_active_price ?? listing.feelway_price ?? 0;
  return listing.gugus_active_price ?? listing.gugus_price ?? 0;
}

function platformState(listings: Listing[], platform: "daangn" | "bunjang" | "feelway" | "gogoose") {
  if (platform === "daangn") return "정상";
  const active = listings.filter((item) => !isExcluded(item));
  if (active.some((item) => platformPrice(item, platform) > 0)) return "정상";
  if (active.some((item) => item.platform_basis?.[platform]?.status === "failed")) return "실패";
  return "조회중";
}

function notificationText(listing: Listing) {
  if (listing.telegram_status === "sent") return "텔레그램 발송됨";
  if (listing.telegram_status === "skipped_condition" || listing.telegram_status === "below_threshold") return "조건 미달";
  if (listing.telegram_status === "failed") return "분석 실패";
  if (isExcluded(listing)) return "분석 실패";
  return "대기";
}

function loadFilterState(): PersistedFilters {
  if (typeof window === "undefined") return defaultFilterState;
  try {
    const raw = window.localStorage.getItem(FILTER_STORAGE_KEY);
    if (!raw) return defaultFilterState;
    const parsed = JSON.parse(raw) as Partial<PersistedFilters>;
    return {
      query: typeof parsed.query === "string" ? parsed.query : defaultFilterState.query,
      brandFilters: Array.isArray(parsed.brandFilters) ? parsed.brandFilters.filter(Boolean) : [],
      minRate: typeof parsed.minRate === "number" ? parsed.minRate : null,
      minPrice: typeof parsed.minPrice === "string" ? parsed.minPrice : "",
      maxPrice: typeof parsed.maxPrice === "string" ? parsed.maxPrice : "",
      gradeFilters: Array.isArray(parsed.gradeFilters) ? parsed.gradeFilters.filter(Boolean) : [],
      requireProof: Boolean(parsed.requireProof),
      sort: parsed.sort === "recent" || parsed.sort === "profit" || parsed.sort === "price" || parsed.sort === "rate" ? parsed.sort : "rate",
    };
  } catch {
    return defaultFilterState;
  }
}

function loadFavoriteIds() {
  if (typeof window === "undefined") return new Set<string>();
  try {
    const raw = window.localStorage.getItem(FAVORITES_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : []);
  } catch {
    return new Set<string>();
  }
}

export default function Index() {
  const { listings, state, error, summary } = useListingsSSE();
  const [initialFilters] = useState(loadFilterState);
  const [selected, setSelected] = useState<Listing | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [view, setView] = useState<View>("dashboard");
  const [query, setQuery] = useState(initialFilters.query);
  const [brandFilters, setBrandFilters] = useState<string[]>(initialFilters.brandFilters);
  const [minRate, setMinRate] = useState<number | null>(initialFilters.minRate);
  const [minPrice, setMinPrice] = useState(initialFilters.minPrice);
  const [maxPrice, setMaxPrice] = useState(initialFilters.maxPrice);
  const [gradeFilters, setGradeFilters] = useState<string[]>(initialFilters.gradeFilters);
  const [requireProof, setRequireProof] = useState(initialFilters.requireProof);
  const [sort, setSort] = useState<SortMode>(initialFilters.sort);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(loadFavoriteIds);
  const [settings, setSettings] = useState<SettingsType>(() => loadSettingsFromLocalStorage() ?? defaultSettings());
  const [page, setPage] = useState(1);
  const debouncedQuery = useDebouncedValue(query, 300);

  useEffect(() => {
    void fetchSettings()
      .then((raw) => setSettings((prev) => mergeSettingsFromApi(prev, raw)))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    persistSettingsToLocalStorage(settings);
  }, [settings]);

  useEffect(() => {
    window.localStorage.setItem(
      FILTER_STORAGE_KEY,
      JSON.stringify({ query, brandFilters, minRate, minPrice, maxPrice, gradeFilters, requireProof, sort }),
    );
  }, [brandFilters, gradeFilters, maxPrice, minPrice, minRate, query, requireProof, sort]);

  useEffect(() => {
    window.localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify([...favoriteIds]));
  }, [favoriteIds]);

  const visibleListings = useMemo(() => listings, [listings]);
  const analyzableListings = useMemo(() => listings.filter((item) => !isExcluded(item)), [listings]);

  const filtered = useMemo(() => {
    const q = debouncedQuery.trim().toLowerCase();
    const min = Number(minPrice || 0);
    const max = Number(maxPrice || 0);
    const base = view === "favorites" ? visibleListings.filter((item) => favoriteIds.has(item.id)) : visibleListings;
    const arr = base.filter((listing) => {
      if (q && !searchBlob(listing).includes(q)) return false;
      if (brandFilters.length > 0 && !brandFilters.includes(String(listing.brand))) return false;
      if (minRate !== null && listingRate(listing) < minRate) return false;
      if (min > 0 && listingPrice(listing) < min) return false;
      if (max > 0 && listingPrice(listing) > max) return false;
      if (gradeFilters.length > 0 && !gradeFilters.includes(listingGrade(listing))) return false;
      if (requireProof && !listing.has_authenticity_proof && !listing.ai_status?.warranty && !listing.ai_status?.receipt) return false;
      return true;
    });

    arr.sort((a, b) => {
      if (sort === "recent") return listingTime(b) - listingTime(a);
      if (sort === "profit") return listingProfit(b) - listingProfit(a);
      if (sort === "price") return listingPrice(a) - listingPrice(b);
      return listingRate(b) - listingRate(a);
    });
    return arr;
  }, [brandFilters, debouncedQuery, favoriteIds, gradeFilters, maxPrice, minPrice, minRate, requireProof, sort, view, visibleListings]);

  useEffect(() => {
    setPage(1);
  }, [debouncedQuery, brandFilters, minRate, minPrice, maxPrice, gradeFilters, requireProof, sort, view]);

  const topListings = useMemo(
    () =>
      [...analyzableListings]
        .sort((a, b) => listingOpportunityProfit(b) - listingOpportunityProfit(a) || listingRate(b) - listingRate(a))
        .slice(0, 3),
    [analyzableListings],
  );
  const recentListings = useMemo(() => [...visibleListings].sort((a, b) => listingTime(b) - listingTime(a)).slice(0, 10), [visibleListings]);
  const notificationRows = useMemo(() => listings.slice(0, 5), [listings]);
  const rateRows = useMemo(() => analyzableListings.filter((item) => listingRate(item) > 0), [analyzableListings]);
  const averageRate = rateRows.length
    ? rateRows.reduce((sum, item) => sum + listingRate(item), 0) / rateRows.length
    : 0;
  const totalPages = view === "dashboard" ? 1 : Math.max(1, Math.ceil(filtered.length / LIST_PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pagedItems = filtered.slice((currentPage - 1) * LIST_PAGE_SIZE, currentPage * LIST_PAGE_SIZE);
  const activeFilters =
    query ||
    brandFilters.length > 0 ||
    minRate !== null ||
    minPrice ||
    maxPrice ||
    gradeFilters.length > 0 ||
    requireProof ||
    sort !== "rate";

  const liveLabel = state === "live" ? "LIVE" : state === "reconnecting" ? "reconnecting" : state === "connecting" ? "connecting" : "offline";
  const liveTone = state === "live" ? "bg-sky-400/15 text-sky-200" : state === "reconnecting" ? "bg-amber-400/15 text-amber-200" : "bg-rose-500/15 text-rose-200";
  const title = view === "dashboard" ? "Dashboard" : view === "favorites" ? "관심매물" : "매물목록";

  const resetFilters = () => {
    setQuery("");
    setBrandFilters([]);
    setMinRate(null);
    setMinPrice("");
    setMaxPrice("");
    setGradeFilters([]);
    setRequireProof(false);
    setSort("rate");
  };

  const toggleFavorite = (id: string) => {
    setFavoriteIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="min-h-screen bg-[#060b13] text-slate-100">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 border-r border-white/10 bg-[#08111d] px-4 py-6 lg:block">
        <div className="mb-10 flex items-center gap-3 px-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04]">
            <LayoutDashboard className="h-4 w-4 text-sky-200" />
          </div>
          <p className="text-sm font-black">LuxeFinder</p>
        </div>
        <nav className="space-y-2 text-sm">
          <SideNavItem active={view === "dashboard"} icon={<LayoutDashboard />} label="대시보드" onClick={() => setView("dashboard")} />
          <SideNavItem active={view === "listings"} icon={<ListChecks />} label="매물목록" onClick={() => setView("listings")} />
          <SideNavItem active={view === "favorites"} icon={<Heart />} label="관심매물" onClick={() => setView("favorites")} />
        </nav>
      </aside>

      <main className="lg:pl-60">
        <header className="sticky top-0 z-20 border-b border-white/10 bg-[#060b13]/90 px-4 py-4 backdrop-blur lg:px-8">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <button className="rounded-lg border border-white/10 p-2 lg:hidden" type="button">
                <Menu className="h-5 w-5" />
              </button>
              <div>
                <h1 className="text-xl font-black tracking-tight md:text-2xl">{title}</h1>
                {view !== "dashboard" ? <p className="text-xs text-slate-500">{`${filtered.length.toLocaleString("ko-KR")}개 매물`}</p> : null}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className={cn("rounded-full border border-current/20 px-3 py-1 text-xs font-black", liveTone)}>{liveLabel}</span>
              <button type="button" onClick={() => setSettingsOpen(true)} className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs font-bold text-slate-200 hover:bg-white/[0.07]">
                <Settings className="h-4 w-4" /> 설정
              </button>
            </div>
          </div>
        </header>

        <section className="space-y-5 p-4 lg:p-6">
          {error ? <Notice>SSE 오류: {error}</Notice> : null}

          {view === "dashboard" ? (
            <DashboardView
              query={query}
              setQuery={setQuery}
              summary={summary}
              averageRate={averageRate}
              recentListings={recentListings}
              visibleListings={visibleListings}
              onOpenListing={setSelected}
            />
          ) : (
            <ExplorerView
              view={view}
              query={query}
              setQuery={setQuery}
              brandFilters={brandFilters}
              setBrandFilters={setBrandFilters}
              minRate={minRate}
              setMinRate={setMinRate}
              minPrice={minPrice}
              setMinPrice={setMinPrice}
              maxPrice={maxPrice}
              setMaxPrice={setMaxPrice}
              gradeFilters={gradeFilters}
              setGradeFilters={setGradeFilters}
              requireProof={requireProof}
              setRequireProof={setRequireProof}
              sort={sort}
              setSort={setSort}
              resetFilters={resetFilters}
              activeFilters={Boolean(activeFilters)}
              items={pagedItems}
              page={currentPage}
              totalPages={totalPages}
              setPage={setPage}
              favoriteIds={favoriteIds}
              toggleFavorite={toggleFavorite}
              onOpenListing={setSelected}
            />
          )}
        </section>
      </main>

      <ListingDetailModal listing={selected} onClose={() => setSelected(null)} />
      <SettingsDrawer
        open={settingsOpen}
        settings={settings}
        onChange={setSettings}
        onClose={() => setSettingsOpen(false)}
        onSave={() => {
          persistSettingsToLocalStorage(settings);
          void saveSettings(settings).then(() => toast({ title: "설정 저장 완료" })).catch((e) => toast({ title: "설정 저장 실패", description: String(e), variant: "destructive" }));
        }}
        onTest={() => {
          void testTelegramSend({ telegramBotToken: settings.telegramBotToken, telegramChatId: settings.telegramChatId })
            .then(() => toast({ title: "테스트 발송 완료" }))
            .catch((e) => toast({ title: "테스트 실패", description: String(e), variant: "destructive" }));
        }}
      />
    </div>
  );
}

function DashboardView({
  query,
  setQuery,
  summary,
  averageRate,
  recentListings,
  visibleListings,
  onOpenListing,
}: {
  query: string;
  setQuery: (value: string) => void;
  summary: { today: number; finalized: number; maxProfit: number };
  averageRate: number;
  recentListings: Listing[];
  visibleListings: Listing[];
  onOpenListing: (listing: Listing) => void;
}) {
  const quick = query.trim().toLowerCase();
  const recent = quick ? recentListings.filter((item) => searchBlob(item).includes(quick)) : recentListings;
  const best = [...visibleListings].sort((a, b) => listingOpportunityProfit(b) - listingOpportunityProfit(a) || listingRate(b) - listingRate(a))[0];

  return (
    <div className="space-y-4">
      <SearchBox value={query} onChange={setQuery} placeholder="모델명, 브랜드 빠른 검색..." />

      <div className="grid gap-3 md:grid-cols-3">
        <Stat label="최근 신규 매물" value={`${visibleListings.length.toLocaleString("ko-KR")}건`} />
        <Stat label="분석 완료" value={`${summary.finalized.toLocaleString("ko-KR")}건`} />
        <Stat label="평균 수익률" value={pct(averageRate)} tone="good" />
      </div>

      {visibleListings.length === 0 ? (
        <EmptyState title="새로운 매물을 탐색 중 입니다." description="수집과 분석이 진행되면 이곳에 핵심 기회가 표시됩니다." />
      ) : (
        <>
          {best && listingOpportunityProfit(best) > 0 ? (
            <Panel>
              <SectionTitle title="오늘의 최고 차익" />
              <div className="mt-3">
                <DashboardListingRow listing={best} onOpenListing={onOpenListing} compact />
              </div>
            </Panel>
          ) : null}

          <Panel>
            <SectionTitle title="최근 신규 매물 10개" />
            <div className="mt-3 space-y-2">
              {recent.map((listing) => (
                <DashboardListingRow key={listing.id} listing={listing} onOpenListing={onOpenListing} />
              ))}
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}

function ExplorerView({
  view,
  query,
  setQuery,
  brandFilters,
  setBrandFilters,
  minRate,
  setMinRate,
  minPrice,
  setMinPrice,
  maxPrice,
  setMaxPrice,
  gradeFilters,
  setGradeFilters,
  requireProof,
  setRequireProof,
  sort,
  setSort,
  resetFilters,
  activeFilters,
  items,
  page,
  totalPages,
  setPage,
  favoriteIds,
  toggleFavorite,
  onOpenListing,
}: {
  view: View;
  query: string;
  setQuery: (value: string) => void;
  brandFilters: string[];
  setBrandFilters: (value: string[]) => void;
  minRate: number | null;
  setMinRate: (value: number | null) => void;
  minPrice: string;
  setMinPrice: (value: string) => void;
  maxPrice: string;
  setMaxPrice: (value: string) => void;
  gradeFilters: string[];
  setGradeFilters: (value: string[]) => void;
  requireProof: boolean;
  setRequireProof: (value: boolean) => void;
  sort: SortMode;
  setSort: (value: SortMode) => void;
  resetFilters: () => void;
  activeFilters: boolean;
  items: Listing[];
  page: number;
  totalPages: number;
  setPage: (page: number) => void;
  favoriteIds: Set<string>;
  toggleFavorite: (id: string) => void;
  onOpenListing: (listing: Listing) => void;
}) {
  return (
    <div className="space-y-5">
      <FilterPanel
        query={query}
        setQuery={setQuery}
        brandFilters={brandFilters}
        setBrandFilters={setBrandFilters}
        minRate={minRate}
        setMinRate={setMinRate}
        minPrice={minPrice}
        setMinPrice={setMinPrice}
        maxPrice={maxPrice}
        setMaxPrice={setMaxPrice}
        gradeFilters={gradeFilters}
        setGradeFilters={setGradeFilters}
        requireProof={requireProof}
        setRequireProof={setRequireProof}
        sort={sort}
        setSort={setSort}
        resetFilters={resetFilters}
        activeFilters={activeFilters}
      />

      {items.length === 0 ? (
        <EmptyState title="새로운 매물을 탐색 중 입니다." description={view === "favorites" ? "저장한 관심매물이 생기면 이곳에 표시됩니다." : "검색어나 필터 조건에 맞는 매물을 기다리는 중입니다."} />
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {items.map((listing) => (
            <ListingCard
              key={listing.id}
              listing={listing}
              isFavorite={favoriteIds.has(listing.id)}
              onToggleFavorite={() => toggleFavorite(listing.id)}
              onClick={() => onOpenListing(listing)}
            />
          ))}
        </div>
      )}

      {totalPages > 1 ? <PaginationBar page={page} totalPages={totalPages} onPageChange={setPage} /> : null}
    </div>
  );
}

function FilterPanel({
  query,
  setQuery,
  brandFilters,
  setBrandFilters,
  minRate,
  setMinRate,
  minPrice,
  setMinPrice,
  maxPrice,
  setMaxPrice,
  gradeFilters,
  setGradeFilters,
  requireProof,
  setRequireProof,
  sort,
  setSort,
  resetFilters,
  activeFilters,
}: {
  query: string;
  setQuery: (value: string) => void;
  brandFilters: string[];
  setBrandFilters: (value: string[]) => void;
  minRate: number | null;
  setMinRate: (value: number | null) => void;
  minPrice: string;
  setMinPrice: (value: string) => void;
  maxPrice: string;
  setMaxPrice: (value: string) => void;
  gradeFilters: string[];
  setGradeFilters: (value: string[]) => void;
  requireProof: boolean;
  setRequireProof: (value: boolean) => void;
  sort: SortMode;
  setSort: (value: SortMode) => void;
  resetFilters: () => void;
  activeFilters: boolean;
}) {
  const toggle = (items: string[], value: string) => (items.includes(value) ? items.filter((item) => item !== value) : [...items, value]);

  return (
    <Panel>
      <SearchBox value={query} onChange={setQuery} placeholder="모델명, 브랜드, 키워드 검색..." />
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <FilterButton active={brandFilters.length === 0} onClick={() => setBrandFilters([])}>전체</FilterButton>
        {BRANDS.map((brand) => (
          <FilterButton key={brand} active={brandFilters.includes(brand)} onClick={() => setBrandFilters(toggle(brandFilters, brand))}>
            {brand}
          </FilterButton>
        ))}
        <Divider />
        <FilterButton active={minRate === null} onClick={() => setMinRate(null)}>전체</FilterButton>
        {RATES.map((rate) => (
          <FilterButton key={rate} active={minRate === rate} onClick={() => setMinRate(minRate === rate ? null : rate)}>
            {rate}%+
          </FilterButton>
        ))}
        <Divider />
        {GRADES.map((grade) => (
          <FilterButton key={grade} active={gradeFilters.includes(grade)} onClick={() => setGradeFilters(toggle(gradeFilters, grade))}>
            {grade}
          </FilterButton>
        ))}
        <FilterButton active={requireProof} onClick={() => setRequireProof(!requireProof)}>
          <CheckCircle2 className="h-3.5 w-3.5" /> 보증서 있음
        </FilterButton>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-[1fr_1fr_1fr_auto]">
        <NumberInput value={minPrice} onChange={setMinPrice} placeholder="최소 가격" />
        <NumberInput value={maxPrice} onChange={setMaxPrice} placeholder="최대 가격" />
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortMode)}
          className="h-10 rounded-lg border border-white/10 bg-[#07111f] px-3 text-xs font-semibold text-slate-100 outline-none"
        >
          <option value="recent">최신순</option>
          <option value="rate">수익률순</option>
          <option value="profit">차익금액순</option>
          <option value="price">가격 낮은순</option>
        </select>
        <button
          type="button"
          onClick={resetFilters}
          disabled={!activeFilters}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-white/10 px-3 text-xs font-bold text-slate-300 transition hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <SlidersHorizontal className="h-3.5 w-3.5" /> 필터 초기화
        </button>
      </div>
    </Panel>
  );
}

function SideNavItem({ active, icon, label, onClick }: { active: boolean; icon: ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-slate-400 transition hover:bg-white/[0.06] hover:text-white",
        active && "bg-white/[0.08] text-white",
      )}
    >
      <span className="h-4 w-4">{icon}</span>
      <span className="font-semibold">{label}</span>
    </button>
  );
}

function SearchBox({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <label className="relative block">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-11 w-full rounded-lg border border-white/10 bg-[#07111f] pl-10 pr-4 text-sm text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-sky-300/50"
      />
    </label>
  );
}

function NumberInput({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value.replace(/[^\d]/g, ""))}
      placeholder={placeholder}
      inputMode="numeric"
      className="h-10 rounded-lg border border-white/10 bg-[#07111f] px-3 text-xs font-semibold text-slate-100 outline-none placeholder:text-slate-500 focus:border-sky-300/50"
    />
  );
}

function Panel({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-white/10 bg-[#0b1120] p-4 shadow-[0_10px_24px_rgba(0,0,0,0.16)]">{children}</div>;
}

function SectionTitle({ title, description }: { title: string; description?: string }) {
  return (
    <div>
      <h2 className="text-sm font-black text-white">{title}</h2>
      {description ? <p className="mt-1 text-xs text-slate-500">{description}</p> : null}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "good" }) {
  return (
    <div className="rounded-lg border border-white/10 bg-[#0b1120] p-3 transition hover:-translate-y-0.5 hover:border-white/20">
      <p className="text-[11px] font-semibold text-slate-500">{label}</p>
      <p className={cn("mt-2 truncate text-lg font-black", tone === "good" ? "text-sky-200" : "text-white")}>{value}</p>
    </div>
  );
}

function DashboardListingRow({
  listing,
  onOpenListing,
  compact = false,
}: {
  listing: Listing;
  onOpenListing: (listing: Listing) => void;
  compact?: boolean;
}) {
  const img = listing.image || listing.imageUrl;
  const sourceHref = listing.link || listing.sourceUrl || listing.url;
  const referencePrice = listing.market_reference_price ?? listing.reference_price_krw ?? null;
  const model = listing.normalized_model_name || listing.normalizedModel || listing.model_name || listing.rawTitle || listing.title;
  const profit = listingProfit(listing);
  const rate = listingRate(listing);
  const status = listing.status === "finalized" || listing.status === "완료" ? "완료" : listing.status === "market_updating" ? "조회중" : isExcluded(listing) ? "제외" : "분석중";

  return (
    <div
      className={cn(
        "grid gap-3 rounded-lg border border-white/10 bg-white/[0.025] p-3 transition hover:border-white/20 hover:bg-white/[0.045] md:items-center",
        compact
          ? "md:grid-cols-[52px_minmax(0,1.5fr)_100px_100px_100px_70px_70px_130px]"
          : "md:grid-cols-[52px_minmax(0,1.5fr)_100px_100px_100px_70px_70px_130px]",
      )}
    >
      <div className="h-12 w-12 overflow-hidden rounded-md bg-[#111827]">
        {img ? <img src={img} alt={String(listing.rawTitle || listing.title || "")} className="h-full w-full object-cover" /> : null}
      </div>

      <div className="min-w-0">
        <p className="text-[11px] font-bold text-slate-400">{listing.brand}</p>
        <p className="truncate text-sm font-bold text-white">{model}</p>
      </div>

      <MetricText label="당근 가격" value={won(listingPrice(listing))} />
      <MetricText label="거래완료 기준 시세" value={referenceWon(listing, referencePrice)} />
      <MetricText label="예상 차익" value={metricWon(profit)} emphasized={profit > 0} />
      <MetricText label="수익률" value={metricPct(rate)} emphasized={rate > 0} />

      <span
        className={cn(
          "inline-flex h-7 items-center justify-center rounded-full border px-2 text-[11px] font-bold",
          status === "완료" && "border-sky-300/30 bg-sky-300/10 text-sky-200",
          status === "조회중" && "border-amber-300/30 bg-amber-300/10 text-amber-200",
          status === "제외" && "border-rose-300/25 bg-rose-300/10 text-rose-200",
          status === "분석중" && "border-white/10 bg-white/[0.04] text-slate-300",
        )}
      >
        {status}
      </span>

      <div className="grid grid-cols-2 gap-2">
        {sourceHref ? (
          <a
            href={sourceHref}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="inline-flex h-8 items-center justify-center rounded-md border border-white/10 px-2 text-xs font-bold text-slate-200 transition hover:bg-white/[0.08]"
          >
            원문
          </a>
        ) : (
          <span className="inline-flex h-8 items-center justify-center rounded-md border border-white/5 px-2 text-xs font-semibold text-slate-500">원문</span>
        )}
        <button
          type="button"
          onClick={() => onOpenListing(listing)}
          className="inline-flex h-8 items-center justify-center rounded-md border border-white/10 bg-white/[0.03] px-2 text-xs font-bold text-sky-200 transition hover:bg-white/[0.08]"
        >
          상세
        </button>
      </div>
    </div>
  );
}

function MetricText({ label, value, emphasized = false }: { label: string; value: string; emphasized?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-semibold text-slate-500">{label}</p>
      <p className={cn("truncate text-xs font-bold text-slate-200", emphasized && "text-sky-200")}>{value}</p>
    </div>
  );
}

function OpportunityCard({ listing, onClick }: { listing: Listing; onClick: () => void }) {
  const img = listing.image || listing.imageUrl;
  return (
    <button type="button" onClick={onClick} className="group overflow-hidden rounded-lg border border-white/10 bg-[#0b1120] text-left transition hover:-translate-y-1 hover:border-white/20">
      <div className="aspect-[16/7] bg-[#111827]">
        {img ? <img src={img} alt={listing.rawTitle} className="h-full w-full object-cover transition group-hover:scale-[1.03]" /> : null}
      </div>
      <div className="space-y-2.5 p-4">
        <div className="flex items-center justify-between gap-3">
          <span className="rounded-md border border-white/10 px-2 py-1 text-[11px] font-bold text-slate-300">{listing.brand}</span>
          <span className="text-sm font-black text-sky-200">{pct(listingRate(listing))}</span>
        </div>
        <p className="line-clamp-2 min-h-10 text-sm font-bold text-white">{listing.rawTitle || listing.title}</p>
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="text-[11px] text-slate-500">예상 차익</p>
            <p className="text-base font-black text-white">{won(listingProfit(listing))}</p>
          </div>
          <p className="text-xs text-slate-400">당근 {won(listingPrice(listing))}</p>
        </div>
      </div>
    </button>
  );
}

function RecentRow({ listing, onClick }: { listing: Listing; onClick: () => void }) {
  const img = listing.image || listing.imageUrl;
  return (
    <button type="button" onClick={onClick} className="flex w-full items-center gap-3 rounded-lg border border-white/8 bg-white/[0.02] p-3 text-left transition hover:bg-white/[0.05]">
      <div className="h-14 w-14 shrink-0 overflow-hidden rounded-md bg-[#111827]">
        {img ? <img src={img} alt={listing.rawTitle} className="h-full w-full object-cover" /> : null}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-bold text-slate-300">{listing.brand}</p>
        <p className="truncate text-sm font-semibold text-white">{listing.rawTitle || listing.title}</p>
      </div>
      <div className="text-right">
        <p className="text-sm font-black text-white">{won(listingPrice(listing))}</p>
        <p className="text-xs font-bold text-sky-200">{pct(listingRate(listing))}</p>
      </div>
    </button>
  );
}

function PlatformStatus({ label, status }: { label: string; status: string }) {
  const tone = status === "정상" ? "bg-sky-400/15 text-sky-200" : status === "조회중" ? "bg-amber-400/15 text-amber-200" : "bg-rose-400/15 text-rose-200";
  return (
    <div className="flex items-center justify-between rounded-lg border border-white/8 bg-white/[0.02] px-3 py-2">
      <span className="text-sm font-semibold text-slate-300">{label}</span>
      <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-black", tone)}>{status}</span>
    </div>
  );
}

function NotificationRow({ listing }: { listing: Listing }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-white/8 bg-white/[0.02] px-3 py-2">
      <div className="min-w-0">
        <p className="truncate text-xs font-bold text-slate-300">{listing.rawTitle || listing.title}</p>
        <p className="text-[11px] text-slate-500">{listing.brand}</p>
      </div>
      <span className="shrink-0 text-[11px] font-bold text-slate-300">{notificationText(listing)}</span>
    </div>
  );
}

function PaginationBar({ page, totalPages, onPageChange }: { page: number; totalPages: number; onPageChange: (page: number) => void }) {
  const pages = Array.from({ length: totalPages }, (_, i) => i + 1);
  return (
    <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
      <button type="button" onClick={() => onPageChange(Math.max(1, page - 1))} disabled={page <= 1} className="h-9 rounded-lg border border-white/10 px-3 text-xs font-bold text-slate-300 transition hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-40">
        이전
      </button>
      {pages.map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onPageChange(n)}
          className={cn(
            "h-9 min-w-9 rounded-lg border px-3 text-xs font-black transition",
            n === page ? "border-sky-300/60 bg-sky-300/10 text-sky-200" : "border-white/10 bg-white/[0.03] text-slate-400 hover:bg-white/[0.07] hover:text-white",
          )}
        >
          {n}
        </button>
      ))}
      <button type="button" onClick={() => onPageChange(Math.min(totalPages, page + 1))} disabled={page >= totalPages} className="h-9 rounded-lg border border-white/10 px-3 text-xs font-bold text-slate-300 transition hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-40">
        다음
      </button>
    </div>
  );
}

function FilterButton({ active, children, onClick }: { active: boolean; children: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex h-9 items-center gap-1.5 rounded-lg border px-3 text-xs font-bold transition",
        active ? "border-sky-300/60 bg-sky-300/10 text-sky-200" : "border-white/10 bg-white/[0.03] text-slate-400 hover:bg-white/[0.07] hover:text-white",
      )}
    >
      {children}
    </button>
  );
}

function Divider() {
  return <span className="mx-1 hidden h-5 w-px bg-white/10 md:inline-block" />;
}

function EmptyState({ title, description = "수집과 분석이 진행되면 자동으로 표시됩니다." }: { title: string; description?: string }) {
  return (
    <div className="flex min-h-[300px] flex-col items-center justify-center rounded-lg border border-dashed border-white/15 bg-[#0b1120] p-8 text-center">
      <Search className="mb-4 h-8 w-8 text-slate-500" />
      <p className="text-lg font-black">{title}</p>
      <p className="mt-2 max-w-md text-sm text-slate-400">{description}</p>
    </div>
  );
}

function Notice({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-100">{children}</div>;
}

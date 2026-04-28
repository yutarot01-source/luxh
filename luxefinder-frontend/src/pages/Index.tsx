import { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  Bell,
  Clock,
  Filter,
  Heart,
  LayoutDashboard,
  ListChecks,
  Menu,
  RefreshCw,
  Settings,
  ShieldAlert,
  SlidersHorizontal,
  TrendingUp,
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

const won = (v?: number | null) => `${Math.round(v || 0).toLocaleString("ko-KR")}원`;

export default function Index() {
  const { listings, state, error, summary } = useListingsSSE();
  const [selected, setSelected] = useState<Listing | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sort, setSort] = useState("profit");
  const [now, setNow] = useState(() => new Date());
  const [settings, setSettings] = useState<SettingsType>(() => loadSettingsFromLocalStorage() ?? defaultSettings());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    void fetchSettings()
      .then((raw) => setSettings((prev) => mergeSettingsFromApi(prev, raw)))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    persistSettingsToLocalStorage(settings);
  }, [settings]);

  const sorted = useMemo(() => {
    const arr = [...listings];
    if (sort === "rate") arr.sort((a, b) => Number(b.profit_rate ?? b.arbitrageRate) - Number(a.profit_rate ?? a.arbitrageRate));
    else if (sort === "recent") arr.sort((a, b) => Date.parse(b.created_at || b.collectedAt || "0") - Date.parse(a.created_at || a.collectedAt || "0"));
    else arr.sort((a, b) => Number(b.expected_profit || 0) - Number(a.expected_profit || 0));
    return arr;
  }, [listings, sort]);

  const liveLabel = state === "live" ? "LIVE" : state === "reconnecting" ? "재연결 중" : state === "connecting" ? "연결 중" : "연결 끊김";
  const liveTone = state === "live" ? "bg-emerald-400 text-slate-950" : state === "reconnecting" ? "bg-amber-400 text-slate-950" : "bg-rose-500 text-white";

  const platformStatus = listings.some((item) => item.status === "market_updating") ? "시세 조회 중" : state === "live" ? "정상" : "대기";

  return (
    <div className="min-h-screen bg-[#050b16] text-slate-100">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-white/10 bg-[#07111f] p-4 lg:block">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-400 text-slate-950">
            <LayoutDashboard className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-black">LuxeFinder</p>
            <p className="text-xs text-slate-500">PoC Control</p>
          </div>
        </div>
        <nav className="space-y-1 text-sm">
          {[
            ["대시보드", LayoutDashboard],
            ["매물 목록", ListChecks],
            ["관심 매물", Heart],
            ["알림 설정", Bell],
            ["분석 리포트", ShieldAlert],
            ["통계 차트", BarChart3],
            ["설정", Settings],
          ].map(([label, Icon]) => (
            <button
              key={String(label)}
              type="button"
              onClick={() => String(label) === "설정" && setSettingsOpen(true)}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-slate-400 hover:bg-white/[0.06] hover:text-white"
            >
              <Icon className="h-4 w-4" /> {String(label)}
            </button>
          ))}
        </nav>
      </aside>

      <main className="lg:pl-64">
        <header className="sticky top-0 z-20 border-b border-white/10 bg-[#050b16]/90 px-4 py-4 backdrop-blur lg:px-6">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div className="flex items-center gap-3">
              <button className="rounded-lg border border-white/10 p-2 lg:hidden" type="button">
                <Menu className="h-5 w-5" />
              </button>
              <div>
                <h1 className="text-xl font-black tracking-tight md:text-2xl">명품 시세 실시간 대시보드</h1>
                <p className="text-xs text-slate-400">당근마켓 기준 · 실시간 크롤링 및 비교 분석</p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className={`rounded-full px-3 py-1 font-black ${liveTone}`}>{liveLabel}</span>
              <span className="inline-flex items-center gap-1 rounded-full border border-white/10 px-3 py-1 text-slate-300">
                <Clock className="h-3.5 w-3.5" /> {now.toLocaleTimeString("ko-KR")}
              </span>
              <span className="rounded-full border border-white/10 px-3 py-1 text-slate-300">자동 새로고침 {state === "live" ? "ON" : "대기"}</span>
              <button type="button" onClick={() => setSettingsOpen(true)} className="inline-flex items-center gap-1 rounded-lg bg-white/10 px-3 py-2 font-bold hover:bg-white/15">
                <Filter className="h-4 w-4" /> 필터
              </button>
              <select value={sort} onChange={(e) => setSort(e.target.value)} className="rounded-lg border border-white/10 bg-[#0b1120] px-3 py-2 text-slate-100">
                <option value="profit">차익순</option>
                <option value="rate">수익률순</option>
                <option value="recent">최신순</option>
              </select>
            </div>
          </div>
        </header>

        <section className="space-y-5 p-4 lg:p-6">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            <Stat label="실시간 검색 매물" value={`${summary.total}건`} icon={<RefreshCw />} />
            <Stat label="분석 완료 매물" value={`${summary.finalized}건`} icon={<ListChecks />} />
            <Stat label="평균 시세차익" value={won(summary.averageProfit)} icon={<TrendingUp />} tone="good" />
            <Stat label="오늘 신규 매물" value={`${summary.today}건`} icon={<Bell />} />
            <Stat label="최대 시세차익" value={won(summary.maxProfit)} icon={<BarChart3 />} tone="good" />
            <Stat label="플랫폼 상태" value={platformStatus} icon={<SlidersHorizontal />} />
          </div>

          {error ? (
            <div className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-100">
              SSE 오류: {error}
            </div>
          ) : null}

          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-black">실시간 매물 카드</h2>
              <p className="text-xs text-slate-500">분석 통과 매물만 표시되며, 시세는 id 기준 부분 업데이트됩니다.</p>
            </div>
            <span className="text-xs text-slate-500">최대 100개 표시</span>
          </div>

          {sorted.length === 0 ? (
            <div className="flex min-h-[380px] flex-col items-center justify-center rounded-lg border border-dashed border-white/15 bg-[#0b1120] p-8 text-center">
              <RefreshCw className="mb-4 h-8 w-8 animate-spin text-slate-500" />
              <p className="text-lg font-black">실시간 수집 대기 중</p>
              <p className="mt-2 max-w-md text-sm text-slate-400">아직 분석/필터를 통과한 매물이 없습니다. 보증서 없음, 상태 B 이하, 모델명 불명확, 수익률 미달 매물은 표시되지 않을 수 있습니다.</p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-5">
              {sorted.map((listing) => (
                <ListingCard key={listing.id} listing={listing} onClick={() => setSelected(listing)} />
              ))}
            </div>
          )}

          <div className="rounded-lg border border-white/10 bg-[#07111f] p-3 text-xs text-slate-400">
            하단 안내: 기준 시세는 거래완료가 우선입니다. 거래완료 샘플이 부족하면 판매중 가격 참고로 표시됩니다.
          </div>
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

function Stat({ label, value, icon, tone }: { label: string; value: string; icon: React.ReactNode; tone?: "good" }) {
  return (
    <div className="rounded-lg border border-white/10 bg-[#0b1120] p-4 shadow-[0_10px_35px_rgba(0,0,0,0.22)]">
      <div className="mb-3 flex items-center justify-between text-slate-500">
        <span className="text-[11px] font-bold uppercase tracking-[0.12em]">{label}</span>
        <span className="h-4 w-4">{icon}</span>
      </div>
      <p className={`truncate text-xl font-black ${tone === "good" ? "text-emerald-300" : "text-slate-100"}`}>{value}</p>
    </div>
  );
}

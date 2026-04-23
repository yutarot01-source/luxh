import { useMemo, useState, useEffect } from "react";
import { CatalogFilterPanel } from "@/components/dashboard/CatalogFilterPanel";
import { Header } from "@/components/dashboard/Header";
import { FilterBar } from "@/components/dashboard/FilterBar";
import { ListingCard } from "@/components/dashboard/ListingCard";
import { NotificationLog } from "@/components/dashboard/NotificationLog";
import { SettingsModal } from "@/components/dashboard/SettingsModal";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  connectListingsSSE,
  defaultSettings,
  fetchListings,
  fetchSettings,
  getOfflinePreviewListings,
  loadSettingsFromLocalStorage,
  mergeSettingsFromApi,
  persistSettingsToLocalStorage,
  saveSettings,
  testTelegramSend,
} from "@/lib/luxe/api";
import { BAG_BRANDS, listingMatchesSelectedCategories } from "@/lib/luxe/constants";
import type { Brand, Grade, Listing, NotificationLog as Log, Settings } from "@/lib/luxe/types";
import { listingGrade, listingWarranty } from "@/lib/luxe/types";
import { toast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { TrendingUp, Package, Bell as BellIcon, WifiOff, RefreshCw } from "lucide-react";

const gradeRank: Record<Grade, number> = { S: 3, A: 2, B: 1 };

const Index = () => {
  const [listings, setListings] = useState<Listing[]>([]);
  const [listingsLoading, setListingsLoading] = useState(true);
  const [listingsFeedError, setListingsFeedError] = useState<string | null>(null);
  const [usingOfflinePreview, setUsingOfflinePreview] = useState(false);
  /** ``GET /api/listings`` 성공 후에만 ``POST /api/settings`` 자동 동기화 (서버 꺼짐 시 토스트 스팸 방지). */
  const [listingsApiOk, setListingsApiOk] = useState(false);
  const [feedRetryKey, setFeedRetryKey] = useState(0);
  const [logs, setLogs] = useState<Log[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const [settings, setSettings] = useState<Settings>(
    () => loadSettingsFromLocalStorage() ?? defaultSettings()
  );

  useEffect(() => {
    let cancelled = false;
    let closeSse = () => {};
    setListingsLoading(true);
    setListingsFeedError(null);
    /** 첫 GET이 막혀도 UI가 무한 로딩에 걸리지 않도록 상한(실시간은 SSE가 이어 받음). */
    const loadingCap = window.setTimeout(() => {
      if (!cancelled) setListingsLoading(false);
    }, 2000);
    closeSse = connectListingsSSE({
      onSnapshot: setListings,
      onListingReady: (listing) => {
        setListings((prev) => {
          const i = prev.findIndex((x) => x.id === listing.id);
          if (i >= 0) {
            const next = [...prev];
            next[i] = listing;
            return next;
          }
          return [listing, ...prev];
        });
      },
    });
    void (async () => {
      try {
        const data = await fetchListings();
        if (cancelled) return;
        setListings(data);
        setListingsFeedError(null);
        setUsingOfflinePreview(false);
        setListingsApiOk(true);
      } catch (e) {
        if (cancelled) return;
        setListings(getOfflinePreviewListings());
        setListingsFeedError(
          e instanceof Error ? e.message : "API에 연결할 수 없습니다. (네트워크 또는 서버 미기동)"
        );
        setUsingOfflinePreview(true);
        setListingsApiOk(false);
      } finally {
        window.clearTimeout(loadingCap);
        if (!cancelled) setListingsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      window.clearTimeout(loadingCap);
      closeSse();
    };
  }, [feedRetryKey]);

  useEffect(() => {
    void fetchSettings()
      .then((raw) => {
        setSettings((prev) => mergeSettingsFromApi(prev, raw));
      })
      .catch(() => {
        toast({
          title: "설정 불러오기 실패",
          description: "GET /api/settings — 서버가 꺼져 있으면 localStorage 값만 사용합니다.",
          variant: "destructive",
        });
      });
  }, []);

  useEffect(() => {
    persistSettingsToLocalStorage(settings);
  }, [settings]);

  useEffect(() => {
    if (!listingsApiOk) return;
    const id = window.setTimeout(() => {
      void saveSettings(settings).catch(() => {
        toast({
          title: "설정 동기화 실패",
          description: "POST /api/settings — 서버가 잠시 내려갔을 수 있습니다.",
          variant: "destructive",
        });
      });
    }, 1500);
    return () => window.clearTimeout(id);
  }, [settings, listingsApiOk]);

  const toggleBrand = (b: Brand | "__all__") => {
    if ((b as string) === "__all__") {
      setSettings((s) => ({
        ...s,
        selectedBrands:
          s.selectedBrands.length === BAG_BRANDS.length &&
          BAG_BRANDS.every((x) => s.selectedBrands.includes(x as Brand))
            ? []
            : [...BAG_BRANDS],
      }));
      return;
    }
    setSettings((s) => ({
      ...s,
      selectedBrands: s.selectedBrands.includes(b as Brand)
        ? s.selectedBrands.filter((x) => x !== b)
        : [...s.selectedBrands, b as Brand],
    }));
  };

  const filtered = useMemo(() => {
    return listings.filter((l) => {
      if (!settings.selectedBrands.includes(l.brand)) return false;
      return listingMatchesSelectedCategories(l, settings.selectedCategoryIds);
    });
  }, [listings, settings.selectedBrands, settings.selectedCategoryIds]);

  // 데이터는 있는데(=수집 성공) 필터 초기값/매핑 문제로 0건처럼 보이는 상황 방지:
  // 우선 화면에는 원본 listings를 보여주고, 필터는 정상 동작 여부를 별도로 점검한다.
  const visibleListings = useMemo(() => {
    if (filtered.length > 0) return filtered;
    if (listings.length > 0) return listings;
    return filtered;
  }, [filtered, listings]);

  const effectiveAlertThreshold = settings.telegram_realtime_enabled
    ? settings.telegram_alert_threshold_percent
    : settings.threshold;

  const meets = (l: Listing) =>
    l.arbitrageRate >= effectiveAlertThreshold &&
    (!settings.requireWarranty || listingWarranty(l)) &&
    gradeRank[listingGrade(l)] >= gradeRank[settings.minGrade];

  const alertCount = visibleListings.filter(meets).length;
  const avgRate = visibleListings.length
    ? visibleListings.reduce((a, b) => a + b.arbitrageRate, 0) / visibleListings.length
    : 0;

  const onSendTelegram = (l: Listing) => {
    const log: Log = {
      id: `log-${Date.now()}`,
      listingId: l.id,
      brand: l.brand,
      model: l.normalizedModel,
      price: l.price,
      arbitrageRate: l.arbitrageRate,
      sentAt: new Date(),
      success: true,
    };
    setLogs((prev) => [log, ...prev]);

    toast({
      title: "알림 기록됨",
      description: `${l.normalizedModel} · 차익율 ${l.arbitrageRate.toFixed(1)}% — 조건 충족 시 수집 주기마다 서버가 텔레그램으로 발송합니다.`,
    });
  };

  return (
    <div className="min-h-screen bg-background">
      <Header
        onOpenSettings={() => setSettingsOpen(true)}
        liveCount={visibleListings.length}
        onTelegramTestSaved={async () => {
          try {
            await testTelegramSend();
            toast({ title: "연결 성공", description: "텔레그램에 ‘연결 성공’ 메시지를 보냈습니다. 채팅을 확인하세요." });
          } catch (e) {
            toast({
              title: "테스트 실패",
              description: e instanceof Error ? e.message : String(e),
              variant: "destructive",
            });
          }
        }}
      />

      <main className="container space-y-6 py-6">
        {/* Stats */}
        <section className="grid gap-3 sm:grid-cols-3">
          <Stat icon={<Package className="h-4 w-4" />} label="실시간 매물" value={`${visibleListings.length}건`} />
          <Stat icon={<TrendingUp className="h-4 w-4" />} label="평균 차익율" value={`${avgRate.toFixed(1)}%`} accent />
          <Stat icon={<BellIcon className="h-4 w-4" />} label="알림 대상" value={`${alertCount}건`} />
        </section>

        <div className="grid gap-6 lg:grid-cols-[minmax(260px,300px)_1fr] lg:items-start">
          <aside className="space-y-4 lg:sticky lg:top-4 lg:z-20 lg:max-h-[calc(100dvh-1rem)] lg:self-start lg:overflow-y-auto lg:pr-1">
            <CatalogFilterPanel
              selectedBrands={settings.selectedBrands}
              toggleBrand={toggleBrand}
              selectedCategoryIds={settings.selectedCategoryIds}
              setSelectedCategoryIds={(ids) => setSettings((s) => ({ ...s, selectedCategoryIds: ids }))}
            />
          </aside>

          <div className="min-w-0 space-y-6">
            <FilterBar
              threshold={settings.threshold}
              setThreshold={(n) => setSettings((s) => ({ ...s, threshold: n }))}
              requireWarranty={settings.requireWarranty}
              setRequireWarranty={(v) => setSettings((s) => ({ ...s, requireWarranty: v }))}
              minGrade={settings.minGrade}
              setMinGrade={(g) => setSettings((s) => ({ ...s, minGrade: g }))}
              telegramRealtimeEnabled={settings.telegram_realtime_enabled}
              setTelegramRealtimeEnabled={(v) => setSettings((s) => ({ ...s, telegram_realtime_enabled: v }))}
              telegramAlertThresholdPercent={settings.telegram_alert_threshold_percent}
              setTelegramAlertThresholdPercent={(n) =>
                setSettings((s) => ({ ...s, telegram_alert_threshold_percent: n }))
              }
            />

            <div className="grid gap-6 xl:grid-cols-[1fr_300px]">
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-display text-base font-bold uppercase tracking-luxe text-foreground">
                실시간 매물 피드
              </h2>
              <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                AI 분석 완료된 매물 {visibleListings.length}건
                {usingOfflinePreview ? " · 오프라인 미리보기" : ""}
              </p>
            </div>

            {listingsFeedError ? (
              <Alert variant="destructive" className="mb-4 border-destructive/40">
                <WifiOff className="h-4 w-4" />
                <AlertTitle>FastAPI 서버에 연결되지 않았습니다</AlertTitle>
                <AlertDescription className="space-y-3 text-left">
                  <p className="text-destructive/90">{listingsFeedError}</p>
                  <p className="text-xs text-destructive/80">
                    저장소 루트(LuxeFinder)에서 아래를 실행한 뒤 <strong>다시 시도</strong>하세요. 프론트는{" "}
                    <code className="rounded bg-muted px-1 py-0.5 text-foreground">npm run dev</code> (8080)일 때{" "}
                    <code className="rounded bg-muted px-1 py-0.5 text-foreground">/api</code>가 8000으로 프록시됩니다.
                  </p>
                  <pre className="overflow-x-auto rounded-md bg-background/80 p-3 text-[11px] text-foreground">
                    {`cd LuxeFinder
pip install -r api/requirements.txt
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000`}
                  </pre>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="gap-2"
                    onClick={() => setFeedRetryKey((k) => k + 1)}
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    다시 연결
                  </Button>
                </AlertDescription>
              </Alert>
            ) : null}

            {usingOfflinePreview ? (
              <p className="mb-3 text-xs font-medium text-muted-foreground">
                아래 카드는 API 없이 보는 UI 미리보기입니다. 텔레그램·설정 저장은 서버가 켜진 뒤에만 동작합니다.
              </p>
            ) : null}

            {listingsLoading ? (
              <div className="rounded-2xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">
                매물 목록을 불러오는 중입니다…
              </div>
            ) : visibleListings.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">
                {listings.length === 0 ? (
                  <>
                    <p className="font-medium text-foreground">표시할 매물이 없습니다.</p>
                    <p className="mt-2">
                      서버가 켜져 있다면 수집 결과가 비어 있을 수 있습니다. 위 <strong>다시 연결</strong>을 눌러
                      새로고침해 보세요.
                    </p>
                  </>
                ) : (
                  "선택한 브랜드·카테고리 조건에 맞는 매물이 없어요. 왼쪽 필터를 조정해 보세요."
                )}
              </div>
            ) : (
              <div className="grid items-stretch gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {visibleListings.map((l) => (
                  <div key={l.id} className="h-full min-h-0">
                    <ListingCard listing={l} meetsAlertCriteria={meets(l)} onSendTelegram={onSendTelegram} />
                  </div>
                ))}
              </div>
            )}
          </section>

          <NotificationLog logs={logs} />
            </div>
          </div>
        </div>
      </main>

      <SettingsModal
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        settings={settings}
        onSave={(draft) => {
          setSettings(draft);
          void saveSettings(draft)
            .then((res) => {
              const ready = Boolean(res.telegram_ready);
              toast({
                title: "설정이 서버에 저장되었습니다.",
                description: ready
                  ? "텔레그램 봇 토큰·채팅 ID가 SettingsStore(JSON)에 반영되었습니다. 테스트 전송을 눌러 확인하세요."
                  : "텔레그램 토큰/채팅 ID가 비어 있으면 알림·연결 테스트를 쓸 수 없습니다.",
              });
            })
            .catch((e) =>
              toast({
                title: "저장 실패",
                description: e instanceof Error ? e.message : String(e),
                variant: "destructive",
              })
            );
        }}
        onTestDraftTelegram={async (draft) => {
          await testTelegramSend({
            telegramBotToken: draft.telegramBotToken,
            telegramChatId: draft.telegramChatId,
          });
        }}
      />
    </div>
  );
};

function Stat({ icon, label, value, accent }: { icon: React.ReactNode; label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-border bg-card p-4 shadow-card">
      <div
        className={cn(
          "flex h-10 w-10 items-center justify-center rounded-xl",
          accent
            ? "bg-gradient-primary text-primary-foreground"
            : "bg-secondary/90 text-foreground",
        )}
      >
        {icon}
      </div>
      <div>
        <p className="text-[11px] font-medium text-muted-foreground">{label}</p>
        <p
          className={cn(
            "text-xl font-black",
            accent ? "text-primary" : "text-foreground",
          )}
        >
          {value}
        </p>
      </div>
    </div>
  );
}

export default Index;

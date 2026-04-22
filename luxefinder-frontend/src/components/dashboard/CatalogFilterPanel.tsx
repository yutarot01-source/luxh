import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { ALL_CATEGORY_FILTER_IDS, BAG_BRAND_PAIRS, BAG_BRANDS, LISTING_CATEGORY_FILTERS } from "@/lib/luxe/constants";
import type { Brand } from "@/lib/luxe/types";
import { ChevronDown, Layers, Search, Tag } from "lucide-react";
import { cn } from "@/lib/utils";

const SELECT_ALL_BTN =
  "h-9 shrink-0 rounded-md border border-primary/25 bg-primary-soft/70 px-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-primary shadow-sm hover:border-primary/35 hover:bg-primary-soft";

interface Props {
  selectedBrands: Brand[];
  toggleBrand: (b: Brand | "__all__") => void;
  selectedCategoryIds: string[];
  setSelectedCategoryIds: (ids: string[]) => void;
}

export function CatalogFilterPanel(p: Props) {
  const [brandSearch, setBrandSearch] = useState("");
  const [catOpen, setCatOpen] = useState(false);
  const [brandOpen, setBrandOpen] = useState(false);

  /** 가나다(국문) 우선, 동일 시 ABC(영문) */
  const brandsSorted = useMemo(
    () =>
      [...BAG_BRAND_PAIRS].sort((a, b) => {
        const c = a.ko.localeCompare(b.ko, "ko");
        return c !== 0 ? c : a.en.localeCompare(b.en, "en", { sensitivity: "base" });
      }),
    [],
  );

  const filteredBrandPairs = useMemo(() => {
    const q = brandSearch.trim().toLowerCase();
    if (!q) return brandsSorted;
    return brandsSorted.filter(
      (pair) =>
        pair.ko.toLowerCase().includes(q) ||
        pair.en.toLowerCase().includes(q) ||
        pair.en.toLowerCase().replace(/\s+/g, "").includes(q.replace(/\s+/g, "")),
    );
  }, [brandSearch, brandsSorted]);

  const coreSelected = BAG_BRANDS.filter((b) => p.selectedBrands.includes(b as Brand)).length;
  const catSelected = p.selectedCategoryIds.length;
  const catTotal = ALL_CATEGORY_FILTER_IDS.length;
  const allCats = catSelected >= catTotal;

  const toggleCategory = (id: string, checked: boolean) => {
    const set = new Set(p.selectedCategoryIds);
    if (checked) set.add(id);
    else set.delete(id);
    let next = [...set];
    if (next.length === 0) next = [...ALL_CATEGORY_FILTER_IDS];
    p.setSelectedCategoryIds(next);
  };

  const selectAllCategories = () => p.setSelectedCategoryIds([...ALL_CATEGORY_FILTER_IDS]);

  return (
    <section className="rounded-[var(--radius)] bg-card p-5 shadow-card sm:p-6">
      <div className="mb-1 flex items-center gap-2">
        <Tag className="h-3.5 w-3.5 text-primary" />
        <p className="text-[9px] font-semibold uppercase tracking-[0.28em] text-muted-foreground">Catalog</p>
      </div>
      <h2 className="font-display text-xs font-bold uppercase tracking-[0.22em] text-foreground">필터</h2>
      <p className="mb-6 mt-2 text-[11px] leading-relaxed text-muted-foreground">
        가방·핸드백 실루엣과 브랜드를 고릅니다. 브랜드가 많을 때는 검색창으로 좁혀 보세요.
      </p>

      <div className="space-y-0">
        {/* 실루엣 */}
        <div className="pb-6">
          <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
            <div className="min-w-0">
              <p className="text-[9px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">Silhouette</p>
              <h3 className="font-display text-xs font-bold uppercase tracking-[0.18em] text-foreground">실루엣</h3>
            </div>
            <Button type="button" className={SELECT_ALL_BTN} onClick={selectAllCategories}>
              실루엣 전체
            </Button>
          </div>
          <Popover open={catOpen} onOpenChange={setCatOpen}>
            <PopoverTrigger asChild>
              <Button
                type="button"
                variant="outline"
                className="h-11 w-full justify-between font-semibold tracking-wide text-foreground"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <Layers className="h-4 w-4 shrink-0 text-primary" />
                  <span className="truncate text-left text-sm">실루엣 선택</span>
                  <span className="shrink-0 rounded-md bg-secondary px-1.5 py-0.5 text-[10px] font-bold text-muted-foreground">
                    {allCats ? "전체" : `${catSelected}/${catTotal}`}
                  </span>
                </span>
                <ChevronDown className="h-4 w-4 shrink-0 opacity-60" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[min(100vw-2rem,20rem)] p-0" align="start">
              <div className="border-b border-border/80 px-3 py-2">
                <Label className="text-[9px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  실루엣 (복수 선택)
                </Label>
              </div>
              <ScrollArea className="h-[min(55vh,280px)]">
                <ul className="space-y-0.5 p-2">
                  {LISTING_CATEGORY_FILTERS.map((c) => {
                    const checked = p.selectedCategoryIds.includes(c.id);
                    return (
                      <li key={c.id}>
                        <label
                          className={cn(
                            "flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-sm transition hover:bg-secondary/80",
                            checked && "bg-primary-soft/50",
                          )}
                        >
                          <Checkbox
                            checked={checked}
                            onCheckedChange={(v) => toggleCategory(c.id, v === true)}
                          />
                          <span className="font-medium leading-tight">{c.label}</span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </ScrollArea>
            </PopoverContent>
          </Popover>
        </div>

        <Separator className="bg-border/70" />

        {/* 브랜드 */}
        <div className="pt-6">
          <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
            <div className="min-w-0">
              <p className="text-[9px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">Maison</p>
              <h3 className="font-display text-xs font-bold uppercase tracking-[0.18em] text-foreground">브랜드</h3>
            </div>
            <Button type="button" className={SELECT_ALL_BTN} onClick={() => p.toggleBrand("__all__" as Brand)}>
              브랜드 전체
            </Button>
          </div>
          <Popover open={brandOpen} onOpenChange={setBrandOpen}>
            <PopoverTrigger asChild>
              <Button
                type="button"
                variant="outline"
                className="h-11 w-full justify-between font-semibold tracking-wide text-foreground"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <Tag className="h-4 w-4 shrink-0 text-primary" />
                  <span className="truncate text-left text-sm">브랜드 선택</span>
                  <span className="shrink-0 rounded-md bg-secondary px-1.5 py-0.5 text-[10px] font-bold text-muted-foreground">
                    {coreSelected}/{BAG_BRANDS.length}
                  </span>
                </span>
                <ChevronDown className="h-4 w-4 shrink-0 opacity-60" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[min(100vw-2rem,22rem)] p-0" align="start">
              <div className="space-y-2 border-b border-border/80 p-3">
                <Label className="text-[9px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                  브랜드 검색
                </Label>
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="국문·영문 검색 (예: 프라다, Rolex, Thom Browne)"
                    value={brandSearch}
                    onChange={(e) => setBrandSearch(e.target.value)}
                    className="h-9 pl-8 text-sm"
                    autoComplete="off"
                    spellCheck={false}
                  />
                </div>
              </div>
              <ScrollArea className="h-[min(55vh,320px)]">
                <ul className="space-y-0.5 p-2">
                  {filteredBrandPairs.length === 0 ? (
                    <li className="px-2 py-6 text-center text-xs text-muted-foreground">검색 결과가 없습니다.</li>
                  ) : (
                    filteredBrandPairs.map((pair) => {
                      const brand = pair.ko as Brand;
                      const checked = p.selectedBrands.includes(brand);
                      return (
                        <li key={pair.ko}>
                          <label
                            className={cn(
                              "flex cursor-pointer items-start gap-2 rounded-lg px-2 py-2 text-sm transition hover:bg-secondary/80",
                              checked && "bg-primary-soft/50",
                            )}
                          >
                            <Checkbox
                              checked={checked}
                              onCheckedChange={() => p.toggleBrand(brand)}
                              className="mt-0.5"
                            />
                            <span className="min-w-0 flex-1 leading-snug">
                              <span className="font-semibold text-foreground">{pair.ko}</span>
                              <span className="mt-0.5 block text-[11px] font-medium text-muted-foreground">
                                {pair.en}
                              </span>
                            </span>
                          </label>
                        </li>
                      );
                    })
                  )}
                  {brandSearch.trim() === "" ? (
                    <li key="기타">
                      <label
                        className={cn(
                          "flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-sm transition hover:bg-secondary/80",
                          p.selectedBrands.includes("기타") && "bg-primary-soft/50",
                        )}
                      >
                        <Checkbox
                          checked={p.selectedBrands.includes("기타")}
                          onCheckedChange={() => p.toggleBrand("기타")}
                        />
                        <span className="font-medium text-muted-foreground">기타 (미분류 브랜드)</span>
                      </label>
                    </li>
                  ) : null}
                </ul>
              </ScrollArea>
            </PopoverContent>
          </Popover>
        </div>
      </div>
    </section>
  );
}

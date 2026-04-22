import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type { Grade } from "@/lib/luxe/types";
import { Send } from "lucide-react";

interface Props {
  threshold: number;
  setThreshold: (n: number) => void;
  requireWarranty: boolean;
  setRequireWarranty: (v: boolean) => void;
  minGrade: Grade;
  setMinGrade: (g: Grade) => void;
  telegramRealtimeEnabled: boolean;
  setTelegramRealtimeEnabled: (v: boolean) => void;
  telegramAlertThresholdPercent: number;
  setTelegramAlertThresholdPercent: (n: number) => void;
}

export function FilterBar(p: Props) {
  return (
    <section className="space-y-4 rounded-2xl border border-border bg-card p-5 shadow-card">
      <div className="grid gap-5 md:grid-cols-3">
        <div className="md:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <Label className="text-sm font-semibold">최소 차익율</Label>
            <span className="text-base font-black text-primary">{p.threshold}%</span>
          </div>
          <Slider
            value={[p.threshold]}
            min={0}
            max={50}
            step={1}
            onValueChange={(v) => p.setThreshold(v[0])}
            className="[&_[role=slider]]:border-primary [&_[role=slider]]:bg-primary"
          />
          <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
            <span>0%</span><span>25%</span><span>50%</span>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between rounded-lg bg-secondary px-3 py-2">
            <Label htmlFor="warranty" className="text-sm font-medium">보증서 필수</Label>
            <Switch id="warranty" checked={p.requireWarranty} onCheckedChange={p.setRequireWarranty} />
          </div>
          <div className="flex items-center justify-between rounded-lg bg-secondary px-3 py-2">
            <Label className="text-sm font-medium">최소 등급</Label>
            <div className="flex gap-1">
              {(["S", "A", "B"] as Grade[]).map((g) => (
                <button
                  key={g}
                  type="button"
                  onClick={() => p.setMinGrade(g)}
                  className={cn(
                    "h-7 w-7 rounded-md text-xs font-bold transition",
                    p.minGrade === g
                      ? "bg-primary text-primary-foreground"
                      : "bg-background text-muted-foreground hover:bg-muted"
                  )}
                >
                  {g}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card p-4">
        <div className="mb-3 flex items-center gap-2">
          <Send className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-bold">텔레그램 연동</h3>
        </div>
        <div className="grid gap-4 md:grid-cols-2 md:items-end">
          <div>
            <div className="mb-2 flex items-center justify-between gap-2">
              <Label className="text-sm font-semibold">알림 기준 차익율</Label>
              <span className="text-base font-black text-primary">{p.telegramAlertThresholdPercent}%</span>
            </div>
            <Slider
              value={[p.telegramAlertThresholdPercent]}
              min={0}
              max={50}
              step={1}
              onValueChange={(v) => p.setTelegramAlertThresholdPercent(v[0])}
              className="[&_[role=slider]]:border-primary [&_[role=slider]]:bg-primary"
            />
            <p className="mt-1 text-[10px] text-muted-foreground">
              이 비율 이상일 때 실시간 알림을 보냅니다. 백엔드 JSON 필드 alert_threshold와 동일 의미로 매핑하면 됩니다.
            </p>
          </div>
          <div className="flex items-center justify-between rounded-lg bg-secondary px-3 py-3">
            <div>
              <Label htmlFor="tg-live" className="text-sm font-medium">실시간 알림</Label>
              <p className="text-[10px] text-muted-foreground">ON일 때 기준 차익율로 알림 대상 판정</p>
            </div>
            <Switch
              id="tg-live"
              checked={p.telegramRealtimeEnabled}
              onCheckedChange={p.setTelegramRealtimeEnabled}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

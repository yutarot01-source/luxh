import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Send, Bot, KeyRound, Loader2 } from "lucide-react";
import type { Settings } from "@/lib/luxe/types";
import { useState, useEffect } from "react";
import { toast } from "@/hooks/use-toast";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  settings: Settings;
  onSave: (s: Settings) => void;
  /** 입력 중인 토큰/채팅 ID로 즉시 테스트 (저장하지 않아도 됨) */
  onTestDraftTelegram?: (draft: Settings) => Promise<void>;
}

export function SettingsModal({ open, onOpenChange, settings, onSave, onTestDraftTelegram }: Props) {
  const [draft, setDraft] = useState(settings);
  const [testing, setTesting] = useState(false);
  useEffect(() => setDraft(settings), [settings, open]);

  const handleTestDraft = async () => {
    if (!onTestDraftTelegram) return;
    setTesting(true);
    try {
      await onTestDraftTelegram(draft);
      toast({ title: "연결 성공", description: "텔레그램에 ‘연결 성공’ 메시지를 보냈습니다." });
    } catch (e) {
      toast({
        title: "테스트 실패",
        description: e instanceof Error ? e.message : String(e),
        variant: "destructive",
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg rounded-lg border-border/80">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-lg font-bold tracking-luxe-tight text-foreground">
            <Bot className="h-5 w-5 text-primary" />
            알림 & API 설정
          </DialogTitle>
          <DialogDescription>
            텔레그램 봇과 OpenAI API를 연결하면 실시간 알림을 받을 수 있어요.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-2">
          <section className="space-y-3 rounded-lg border border-border/60 bg-secondary/70 p-4">
            <div className="flex items-center justify-between">
              <Label className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                최소 차익율 (알림 기준)
              </Label>
              <span className="font-display text-base font-bold tracking-wide text-profit">{draft.threshold}%</span>
            </div>
            <Slider
              value={[draft.threshold]}
              min={0}
              max={50}
              step={1}
              onValueChange={(v) => setDraft({ ...draft, threshold: v[0] })}
            />
          </section>

          <section className="space-y-3">
            <h3 className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              <Send className="h-4 w-4 text-primary" /> 텔레그램 봇
            </h3>
            <div className="space-y-1.5">
              <Label htmlFor="bot" className="text-xs text-muted-foreground">Bot Token</Label>
              <Input
                id="bot"
                placeholder="123456:ABC-DEF1234ghIkl..."
                value={draft.telegramBotToken}
                onChange={(e) => setDraft({ ...draft, telegramBotToken: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="chat" className="text-xs text-muted-foreground">Chat ID</Label>
              <Input
                id="chat"
                placeholder="-1001234567890"
                value={draft.telegramChatId}
                onChange={(e) => setDraft({ ...draft, telegramChatId: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tg-min-profit" className="text-xs text-muted-foreground">
                텔레그램 알림 — 최소 예상 수익 (원)
              </Label>
              <Input
                id="tg-min-profit"
                type="number"
                min={0}
                step={100000}
                placeholder="0 = 제한 없음"
                value={draft.telegramMinExpectedProfitKrw}
                onChange={(e) => {
                  const raw = e.target.value;
                  const v = raw === "" ? 0 : Math.max(0, Math.floor(Number(raw)));
                  setDraft({ ...draft, telegramMinExpectedProfitKrw: Number.isNaN(v) ? 0 : v });
                }}
              />
              <p className="text-[10px] text-muted-foreground">
                대시보드에서 선택한 브랜드·실루엣과 동일하게 필터링되며, 예상 수익이 이 금액 이상일 때만 알림이 갑니다.
              </p>
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              <KeyRound className="h-4 w-4 text-primary" /> AI 분석 (OpenAI / Gemini)
            </h3>
            <div className="space-y-1.5">
              <Label htmlFor="api" className="text-xs text-muted-foreground">API Key</Label>
              <Input
                id="api"
                type="password"
                placeholder="sk-..."
                value={draft.openaiApiKey}
                onChange={(e) => setDraft({ ...draft, openaiApiKey: e.target.value })}
              />
              <p className="text-[11px] text-muted-foreground">
                설정은 브라우저 <code className="text-[10px]">localStorage</code>와 FastAPI{" "}
                <code className="text-[10px]">data/luxefinder_settings.json</code>에 함께 저장되어 새로고침 후에도
                유지됩니다.
              </p>
            </div>
          </section>
        </div>

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <div className="flex w-full flex-wrap gap-2 sm:mr-auto">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              취소
            </Button>
            {onTestDraftTelegram ? (
              <Button
                type="button"
                variant="secondary"
                className="gap-2"
                disabled={testing}
                onClick={() => void handleTestDraft()}
              >
                {testing ? <Loader2 className="h-4 w-4 shrink-0 animate-spin" /> : null}
                테스트 메시지 전송
              </Button>
            ) : null}
          </div>
          <Button
            className="bg-primary hover:bg-primary/90"
            onClick={() => {
              onSave(draft);
              onOpenChange(false);
            }}
          >
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

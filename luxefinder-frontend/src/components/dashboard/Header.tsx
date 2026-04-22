import { Settings as SettingsIcon, Sparkles, Send } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  onOpenSettings: () => void;
  /** 서버에 저장된 봇 설정으로 테스트 메시지 전송 */
  onTelegramTestSaved?: () => void | Promise<void>;
  liveCount: number;
}

export function Header({ onOpenSettings, onTelegramTestSaved, liveCount }: Props) {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur-md">
      <div className="container flex h-16 items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-primary text-primary-foreground shadow-glow">
            <Sparkles className="h-5 w-5" />
          </div>
          <div className="flex items-baseline gap-2">
            <h1 className="text-xl font-black tracking-tight text-foreground">
              Luxe<span className="text-primary">Finder</span>
            </h1>
            <span className="hidden text-xs font-medium text-muted-foreground sm:inline">
              · 명품 가방 시세차익 분석
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-2 rounded-full bg-primary-soft px-3 py-1.5 sm:flex">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
            </span>
            <span className="text-xs font-semibold text-accent-foreground">
              실시간 {liveCount}건 분석중
            </span>
          </div>
          {onTelegramTestSaved ? (
            <Button
              variant="outline"
              size="sm"
              className="hidden gap-1.5 sm:inline-flex"
              type="button"
              onClick={() => void onTelegramTestSaved()}
            >
              <Send className="h-3.5 w-3.5" />
              테스트 전송
            </Button>
          ) : null}
          <Button variant="ghost" size="icon" onClick={onOpenSettings} aria-label="설정">
            <SettingsIcon className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </header>
  );
}

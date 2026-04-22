import { Bell, CheckCircle2 } from "lucide-react";
import type { NotificationLog as Log } from "@/lib/luxe/types";

interface Props { logs: Log[]; }

export function NotificationLog({ logs }: Props) {
  return (
    <aside className="sticky top-20 rounded-2xl border border-border bg-card shadow-card">
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-soft text-primary">
            <Bell className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-foreground">알림 이력</h2>
            <p className="text-[11px] text-muted-foreground">텔레그램 전송 로그</p>
          </div>
        </div>
        <span className="rounded-full bg-primary px-2 py-0.5 text-[10px] font-bold text-primary-foreground">
          {logs.length}
        </span>
      </div>

      <ul className="max-h-[600px] divide-y divide-border overflow-y-auto">
        {logs.length === 0 && (
          <li className="px-5 py-10 text-center text-sm text-muted-foreground">
            아직 전송된 알림이 없어요
          </li>
        )}
        {logs.map((l) => (
          <li key={l.id} className="flex items-start gap-3 px-5 py-3 transition hover:bg-secondary">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary-soft text-xs font-black text-primary">
              {l.brand.slice(0, 2)}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-foreground">{l.model}</p>
              <p className="text-[11px] text-muted-foreground">
                {l.price.toLocaleString()}원 · 차익{" "}
                <span className="font-bold text-primary">{l.arbitrageRate.toFixed(1)}%</span>
              </p>
              <p className="mt-0.5 text-[10px] text-muted-foreground">
                {timeAgo(l.sentAt)}
              </p>
            </div>
            {l.success && <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />}
          </li>
        ))}
      </ul>
    </aside>
  );
}

function timeAgo(d: Date) {
  const m = Math.floor((Date.now() - d.getTime()) / 60000);
  if (m < 1) return "방금 전";
  if (m < 60) return `${m}분 전`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}시간 전`;
  return `${Math.floor(h / 24)}일 전`;
}

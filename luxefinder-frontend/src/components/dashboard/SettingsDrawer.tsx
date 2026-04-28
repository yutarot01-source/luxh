import { X, Send, Save } from "lucide-react";
import type { Settings } from "@/lib/luxe/types";

export function SettingsDrawer({
  open,
  settings,
  onChange,
  onClose,
  onSave,
  onTest,
}: {
  open: boolean;
  settings: Settings;
  onChange: (settings: Settings) => void;
  onClose: () => void;
  onSave: () => void;
  onTest: () => void;
}) {
  return (
    <div className={`fixed inset-0 z-40 ${open ? "" : "pointer-events-none"}`}>
      <div className={`absolute inset-0 bg-black/50 transition ${open ? "opacity-100" : "opacity-0"}`} onClick={onClose} />
      <aside
        className={`absolute right-0 top-0 h-full w-full max-w-md overflow-y-auto border-l border-white/10 bg-[#08111f] p-5 text-slate-100 shadow-2xl transition-transform duration-300 sm:w-[420px] ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-black">설정 / 필터</h2>
            <p className="text-xs text-slate-400">PoC 범위는 가방 · 샤넬/루이비통/구찌 고정입니다.</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-2 text-slate-400 hover:bg-white/10 hover:text-white">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-5">
          <Section title="카테고리 / 브랜드">
            <ReadonlyPill label="카테고리" value="가방 고정" />
            <ReadonlyPill label="브랜드" value="샤넬 · 루이비통 · 구찌" />
          </Section>

          <Section title="수익 조건">
            <Field label="최소 시세차익">
              <input
                type="number"
                min={0}
                className="input-dark"
                value={settings.telegramMinExpectedProfitKrw}
                onChange={(e) => onChange({ ...settings, telegramMinExpectedProfitKrw: Math.max(0, Number(e.target.value) || 0) })}
              />
            </Field>
            <Field label="최소 수익률 (%)">
              <input
                type="number"
                min={0}
                max={100}
                className="input-dark"
                value={settings.telegram_alert_threshold_percent}
                onChange={(e) => onChange({ ...settings, telegram_alert_threshold_percent: Math.max(0, Number(e.target.value) || 0) })}
              />
            </Field>
            <label className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.04] p-3 text-sm">
              <span>알림 ON/OFF</span>
              <input
                type="checkbox"
                checked={settings.telegram_realtime_enabled}
                onChange={(e) => onChange({ ...settings, telegram_realtime_enabled: e.target.checked })}
              />
            </label>
          </Section>

          <Section title="API / Telegram">
            <Field label="API Key">
              <input className="input-dark" type="password" value={settings.openaiApiKey} onChange={(e) => onChange({ ...settings, openaiApiKey: e.target.value })} />
            </Field>
            <Field label="Telegram Bot Token">
              <input className="input-dark" value={settings.telegramBotToken} onChange={(e) => onChange({ ...settings, telegramBotToken: e.target.value })} />
            </Field>
            <Field label="Telegram Chat ID">
              <input className="input-dark" value={settings.telegramChatId} onChange={(e) => onChange({ ...settings, telegramChatId: e.target.value })} />
            </Field>
          </Section>

          <div className="grid grid-cols-2 gap-3">
            <button type="button" onClick={onSave} className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-400 px-4 py-3 text-sm font-black text-slate-950 hover:bg-emerald-300">
              <Save className="h-4 w-4" /> 저장
            </button>
            <button type="button" onClick={onTest} className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/10 px-4 py-3 text-sm font-bold text-slate-100 hover:bg-white/10">
              <Send className="h-4 w-4" /> 테스트 발송
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 rounded-lg border border-white/10 bg-[#0b1120] p-4">
      <h3 className="text-xs font-black uppercase tracking-[0.18em] text-slate-500">{title}</h3>
      {children}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5 text-sm">
      <span className="text-xs text-slate-400">{label}</span>
      {children}
    </label>
  );
}

function ReadonlyPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.04] p-3 text-sm">
      <span className="text-slate-400">{label}</span>
      <span className="font-bold">{value}</span>
    </div>
  );
}

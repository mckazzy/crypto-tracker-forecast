import { useEffect, useState } from 'react'
import { Bell, CheckCircle2, Clock, XCircle } from 'lucide-react'
import { fetchAlerts, type Alert } from '../lib/trading'

export function AlertsPanel() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = () => {
      fetchAlerts()
        .then((a) => {
          if (!cancelled) {
            setAlerts(a)
            setError(null)
          }
        })
        .catch((e) => {
          if (!cancelled) setError(String(e.message ?? e))
        })
    }
    load()
    const t = setInterval(load, 30_000)
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [])

  return (
    <div className="space-y-4">
      {error && (
        <div role="alert" className="text-xs text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded-lg px-3 py-2">
          {error}
        </div>
      )}
      <section className="surface-card overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
          <div className="flex items-center gap-2">
            <Bell className="w-4 h-4 text-amber-500" />
            <h3 className="text-sm font-bold text-[var(--color-text-main)] uppercase tracking-wide">Alerts Feed</h3>
          </div>
          <span className="text-xs text-[var(--color-text-muted)] font-mono">{alerts.length} signals</span>
        </div>

        {alerts.length === 0 ? (
          <div className="py-10 text-center text-[var(--color-text-muted)] text-xs flex flex-col items-center gap-1.5">
            <Clock className="w-6 h-6 text-[var(--color-text-muted)]" />
            <span>No alerts yet</span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-[var(--color-surface-2)] text-left text-[var(--color-text-muted)] uppercase tracking-wider border-b border-[var(--color-border)] font-semibold">
                  <th className="py-3 px-4">Symbol</th>
                  <th className="py-3 px-4">Dir</th>
                  <th className="py-3 px-4 text-right">Entry</th>
                  <th className="py-3 px-4">Channel</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Sent</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border-subtle)] font-mono tabular-nums">
                {alerts.map((a) => (
                  <tr key={a.id} data-testid="alert-row" className="hover:bg-[var(--color-surface-2)]/60 transition-colors">
                    <td className="py-3 px-4 font-sans font-bold text-[var(--color-text-main)]">{a.symbol}</td>
                    <td className="py-3 px-4 font-sans">
                      <span
                        className={`px-2 py-0.5 rounded-md text-[11px] font-bold ${
                          a.direction === 'LONG'
                            ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                            : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                        }`}
                      >
                        {a.direction}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right text-[var(--color-text-main)]">{a.entry?.toFixed(2) ?? '—'}</td>
                    <td className="py-3 px-4 font-sans">
                      <span className="px-2 py-0.5 rounded-md bg-[var(--color-surface-2)] text-[var(--color-text-muted)] text-[11px] border border-[var(--color-border)]">
                        {a.channel}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-sans">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold capitalize ${
                          a.status === 'sent'
                            ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                            : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                        }`}
                      >
                        {a.status === 'sent' ? <CheckCircle2 className="w-3 h-3 text-emerald-500" /> : <XCircle className="w-3 h-3 text-rose-500" />}
                        {a.status}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right text-[var(--color-text-muted)] text-[11px]">
                      {a.sent_at ? new Date(a.sent_at).toISOString().slice(0, 16).replace('T', ' ') : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

export default AlertsPanel

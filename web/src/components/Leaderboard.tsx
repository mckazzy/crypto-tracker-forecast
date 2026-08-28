import { useEffect, useState } from 'react'
import {
  AlertCircle,
  Filter,
  Sparkles,
  Trophy,
} from 'lucide-react'
import { fetchLeaderboard, type LeaderboardEntry } from '../lib/leaderboard'

const TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d', '1w']
const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']

function Leaderboard() {
  const [symbol, setSymbol] = useState('')
  const [timeframe, setTimeframe] = useState('')
  const [rows, setRows] = useState<LeaderboardEntry[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = () => {
      fetchLeaderboard(symbol || undefined, timeframe || undefined)
        .then((r) => {
          if (!cancelled) {
            setRows(r.providers)
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
  }, [symbol, timeframe])

  // Sort by ok_signals / signals accuracy if available
  const sortedRows = [...rows].sort((a, b) => {
    const accA = a.signals > 0 ? a.ok_signals / a.signals : 0
    const accB = b.signals > 0 ? b.ok_signals / b.signals : 0
    return accB - accA || b.ok_signals - a.ok_signals
  })

  return (
    <div className="space-y-6">
      {/* Top Banner / Filter Toolbar - 9Router Surface Card */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 surface-card">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-[var(--color-primary)]/10 border border-[var(--color-primary)]/20 text-[var(--color-primary)]">
            <Trophy className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-[var(--color-text-main)] flex items-center gap-2">
              Model Leaderboard
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-[var(--color-primary)]/10 text-[var(--color-primary)] border border-[var(--color-primary)]/20">
                AI Benchmark
              </span>
            </h2>
            <p className="text-xs text-[var(--color-text-muted)]">
              Evaluated prediction models ranked by signal accuracy and execution performance
            </p>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[var(--color-surface-2)] border border-[var(--color-border)] text-xs">
            <Filter className="w-3.5 h-3.5 text-[var(--color-text-muted)]" />
            <select
              aria-label="Leaderboard symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="bg-transparent text-[var(--color-text-main)] focus:outline-none cursor-pointer"
            >
              <option value="" className="bg-[var(--color-surface)] text-[var(--color-text-main)]">All symbols</option>
              {SYMBOLS.map((s) => (
                <option key={s} value={s} className="bg-[var(--color-surface)] text-[var(--color-text-main)]">
                  {s}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[var(--color-surface-2)] border border-[var(--color-border)] text-xs">
            <select
              aria-label="Leaderboard timeframe"
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="bg-transparent text-[var(--color-text-main)] focus:outline-none cursor-pointer"
            >
              <option value="" className="bg-[var(--color-surface)] text-[var(--color-text-main)]">All timeframes</option>
              {TIMEFRAMES.map((tf) => (
                <option key={tf} value={tf} className="bg-[var(--color-surface)] text-[var(--color-text-main)]">
                  {tf}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {error && (
        <div role="alert" className="flex items-center gap-2.5 p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-600 dark:text-rose-400 text-xs shadow-sm">
          <AlertCircle className="w-4 h-4 text-rose-500 shrink-0" />
          <span>Load failed: {error}</span>
        </div>
      )}

      {/* Main Ranking Table */}
      <div className="surface-card overflow-hidden">
        {rows.length === 0 ? (
          <div data-testid="leaderboard-empty" className="py-16 text-center text-[var(--color-text-muted)] text-sm flex flex-col items-center gap-2">
            <Sparkles className="w-8 h-8 text-[var(--color-primary)] animate-pulse" />
            <p className="font-semibold text-[var(--color-text-main)]">No models evaluated yet</p>
            <span className="text-xs text-[var(--color-text-muted)]">Run forecast models or paper trade to generate evaluation records.</span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-[var(--color-surface-2)] text-left text-[var(--color-text-muted)] uppercase tracking-wider border-b border-[var(--color-border)] font-semibold">
                  <th className="py-3.5 px-4"># Rank</th>
                  <th className="py-3.5 px-4">Provider</th>
                  <th className="py-3.5 px-4">Type</th>
                  <th className="py-3.5 px-4 text-right">Signals</th>
                  <th className="py-3.5 px-4 text-right">OK</th>
                  <th className="py-3.5 px-4 text-right">Win Rate</th>
                  <th className="py-3.5 px-4 text-right">Token cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border-subtle)] font-mono tabular-nums">
                {sortedRows.map((r, idx) => {
                  const accuracy = r.signals > 0 ? (r.ok_signals / r.signals) * 100 : 0
                  return (
                    <tr
                      key={r.name}
                      data-testid="leaderboard-row"
                      className="hover:bg-[var(--color-surface-2)]/60 transition-colors"
                    >
                      <td className="py-3.5 px-4 font-sans font-bold text-[var(--color-text-main)]">
                        {idx === 0 ? '🥇 1' : idx === 1 ? '🥈 2' : idx === 2 ? '🥉 3' : `#${idx + 1}`}
                      </td>
                      <td className="py-3.5 px-4 font-sans font-semibold text-[var(--color-text-main)]">
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 rounded-full bg-[var(--color-primary)] shadow-sm" />
                          <span>{r.name}</span>
                        </div>
                      </td>
                      <td className="py-3.5 px-4 text-[var(--color-text-muted)] font-sans">
                        <span className="px-2 py-0.5 rounded-md bg-[var(--color-surface-2)] text-[var(--color-text-main)] text-[11px] border border-[var(--color-border)]">
                          {r.model_type ?? '—'}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 text-right text-[var(--color-text-main)]">{r.signals}</td>
                      <td className="py-3.5 px-4 text-right text-emerald-600 dark:text-emerald-400 font-bold">{r.ok_signals}</td>
                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <span className="text-[var(--color-text-main)] font-bold">{accuracy.toFixed(1)}%</span>
                          <div className="w-12 bg-[var(--color-surface-3)] rounded-full h-1.5 hidden sm:block overflow-hidden">
                            <div
                              className="bg-emerald-500 dark:bg-emerald-400 h-full rounded-full"
                              style={{ width: `${accuracy}%` }}
                            />
                          </div>
                        </div>
                      </td>
                      <td className="py-3.5 px-4 text-right text-[var(--color-text-main)] font-mono">
                        {r.total_token_cost > 0 ? (
                          <span className="px-2 py-0.5 rounded-md bg-[var(--color-surface-2)] text-[var(--color-primary)] text-[11px] font-semibold border border-[var(--color-border)]">
                            {r.total_token_cost.toLocaleString()}
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[11px] font-semibold border border-emerald-500/20">
                            0 (local)
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default Leaderboard

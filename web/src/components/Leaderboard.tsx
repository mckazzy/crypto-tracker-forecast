import { useEffect, useState } from 'react'
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

  return (
    <div className="p-6">
      <header className="flex flex-wrap items-center gap-3 mb-6">
        <h2 className="text-xl font-bold mr-4">Model Leaderboard</h2>
        <select
          aria-label="Leaderboard symbol"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded px-2 py-1"
        >
          <option value="">All symbols</option>
          {SYMBOLS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          aria-label="Leaderboard timeframe"
          value={timeframe}
          onChange={(e) => setTimeframe(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded px-2 py-1"
        >
          <option value="">All timeframes</option>
          {TIMEFRAMES.map((tf) => (
            <option key={tf} value={tf}>
              {tf}
            </option>
          ))}
        </select>
      </header>

      {error && (
        <div role="alert" className="mb-4 p-3 bg-red-900/50 border border-red-700 rounded text-red-200">
          Load failed: {error}
        </div>
      )}

      {rows.length === 0 ? (
        <div data-testid="leaderboard-empty" className="p-6 text-center text-slate-400">
          No models evaluated yet
        </div>
      ) : (
        <table className="w-full text-sm bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
          <thead>
            <tr className="bg-slate-800 text-left text-slate-300">
              <th className="p-2">Provider</th>
              <th className="p-2">Signals</th>
              <th className="p-2">OK</th>
              <th className="p-2">Token cost</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} data-testid="leaderboard-row" className="border-t border-slate-800">
                <td className="p-2">{r.name}</td>
                <td className="p-2 tabular-nums">{r.signals}</td>
                <td className="p-2 tabular-nums">{r.ok_signals}</td>
                <td className="p-2 tabular-nums">
                  {r.total_token_cost > 0 ? r.total_token_cost.toLocaleString() : '0 (local)'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default Leaderboard

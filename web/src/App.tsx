import { useCallback, useEffect, useState } from 'react'
import {
  fetchKlines,
  fetchSymbols,
  type Kline,
  type SymbolCoverage,
} from './lib/api'

const TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d', '1w']

function fmtPrice(n: number): string {
  return n.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

function CandleChart({ candles }: { candles: Kline[] }) {
  if (candles.length < 2) return null
  const lows = Math.min(...candles.map((c) => c.low))
  const highs = Math.max(...candles.map((c) => c.high))
  const span = highs - lows || 1
  const W = 1000
  const H = 300
  const step = W / (candles.length - 1)
  const points = candles
    .map((c, i) => `${(i * step).toFixed(1)},${(H - ((c.close - lows) / span) * H).toFixed(1)}`)
    .join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-64" data-testid="price-chart">
      <polyline
        points={points}
        fill="none"
        stroke="#22c55e"
        strokeWidth="2"
      />
    </svg>
  )
}

function App() {
  const [symbols, setSymbols] = useState<SymbolCoverage[]>([])
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [timeframe, setTimeframe] = useState('1h')
  const [candles, setCandles] = useState<Kline[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchSymbols()
      .then(setSymbols)
      .catch(() => setSymbols([]))
  }, [])

  const load = useCallback(() => {
    setError(null)
    fetchKlines(symbol, timeframe)
      .then((r) => setCandles(r.data))
      .catch((e) => setError(String(e.message ?? e)))
  }, [symbol, timeframe])

  useEffect(() => {
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [load])

  const last = candles.length > 0 ? candles[candles.length - 1] : null

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6">
      <header className="flex flex-wrap items-center gap-3 mb-6">
        <h1 className="text-2xl font-bold mr-4">Crypto Tracker</h1>
        <label className="flex items-center gap-2">
          <span className="text-slate-400">Symbol</span>
          <select
            aria-label="Symbol"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded px-2 py-1"
          >
            {(symbols.length > 0 ? symbols.map((s) => s.symbol) : [symbol]).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <div role="group" aria-label="Timeframe" className="flex gap-1">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-3 py-1 rounded ${
                tf === timeframe
                  ? 'bg-emerald-600 text-white'
                  : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </header>

      {error && (
        <div role="alert" className="mb-4 p-3 bg-red-900/50 border border-red-700 rounded text-red-200">
          Load failed: {error}
        </div>
      )}

      <section className="grid grid-cols-1 md:grid-cols-[2fr_1fr] gap-6 mb-6">
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <CandleChart candles={candles} />
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-col justify-center">
          <span className="text-slate-400 text-sm">Last close ({timeframe})</span>
          <span data-testid="last-price" className="text-4xl font-bold tabular-nums text-emerald-400">
            {last ? fmtPrice(last.close) : '—'}
          </span>
          {last && (
            <span
              className={`mt-2 text-sm font-semibold ${
                last.close >= last.open ? 'text-emerald-400' : 'text-red-400'
              }`}
            >
              {last.close >= last.open ? '▲' : '▼'} {fmtPrice(Math.abs(last.close - last.open))}
            </span>
          )}
        </div>
      </section>

      <section className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-800 text-left text-slate-300">
              <th className="p-2">Open time</th>
              <th className="p-2">Open</th>
              <th className="p-2">High</th>
              <th className="p-2">Low</th>
              <th className="p-2">Close</th>
              <th className="p-2">Volume</th>
            </tr>
          </thead>
          <tbody>
            {[...candles].reverse().map((c) => (
              <tr key={c.open_time} data-testid="candle-row" className="border-t border-slate-800">
                <td className="p-2">{new Date(c.open_time).toISOString().replace('T', ' ').slice(0, 16)}</td>
                <td className="p-2 tabular-nums">{fmtPrice(c.open)}</td>
                <td className="p-2 tabular-nums">{fmtPrice(c.high)}</td>
                <td className="p-2 tabular-nums">{fmtPrice(c.low)}</td>
                <td className={`p-2 tabular-nums ${c.close >= c.open ? 'text-emerald-400' : 'text-red-400'}`}>
                  {fmtPrice(c.close)}
                </td>
                <td className="p-2 tabular-nums">{c.volume.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

export default App

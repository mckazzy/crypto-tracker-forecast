import { useCallback, useEffect, useState } from 'react'
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart2,
  Clock,
  LayoutDashboard,
  Moon,
  RefreshCw,
  Sun,
  Trophy,
  Zap,
} from 'lucide-react'
import CandleChart from './components/CandleChart'
import ForecastCompare from './components/ForecastCompare'
import Leaderboard from './components/Leaderboard'
import ModelPicker from './components/ModelPicker'
import AlertsPanel from './components/AlertsPanel'
import FuturesTerminal from './components/futures/FuturesTerminal'
import {
  fetchKlines,
  fetchSymbols,
  type Kline,
  type SymbolCoverage,
} from './lib/api'

const TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d', '1w']

function fmtPrice(n: number): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function App() {
  const [tab, setTab] = useState<'dashboard' | 'leaderboard' | 'trading' | 'forecast' | 'alerts'>('dashboard')
  const [symbols, setSymbols] = useState<SymbolCoverage[]>([])
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [timeframe, setTimeframe] = useState('1h')
  const [candles, setCandles] = useState<Kline[]>([])
  const [error, setError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

  // Clean Quartz / Pro Terminal Theme Engine
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('theme')
      if (saved === 'light' || saved === 'dark') return saved
      if (window.matchMedia?.('(prefers-color-scheme: light)').matches) return 'light'
    }
    return 'dark'
  })

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') {
      root.classList.add('dark')
      root.classList.remove('light')
    } else {
      root.classList.remove('dark')
      root.classList.add('light')
    }
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'))
  }

  useEffect(() => {
    fetchSymbols()
      .then(setSymbols)
      .catch(() => setSymbols([]))
  }, [])

  const load = useCallback(() => {
    setIsRefreshing(true)
    setError(null)
    // force=true: manual refresh (nút Refresh) bypass throttle 10s của fetchKlines
    fetchKlines(symbol, timeframe, 500, { force: true })
      .then((r) => setCandles(r.data))
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setIsRefreshing(false))
  }, [symbol, timeframe])

  useEffect(() => {
    let cancelled = false
    fetchKlines(symbol, timeframe)
      .then((r) => {
        if (!cancelled) setCandles(r.data)
      })
      .catch((e) => {
        if (!cancelled) setError(String(e.message ?? e))
      })
      .finally(() => {
        if (!cancelled) setIsRefreshing(false)
      })

    const t = setInterval(() => {
      fetchKlines(symbol, timeframe)
        .then((r) => {
          if (!cancelled) setCandles(r.data)
        })
        .catch((e) => {
          if (!cancelled) setError(String(e.message ?? e))
        })
    }, 30_000)

    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [symbol, timeframe])

  const last = candles.length > 0 ? candles[candles.length - 1] : null
  const prev = candles.length > 1 ? candles[candles.length - 2] : null
  const priceChange = last && prev ? last.close - prev.close : (last ? last.close - last.open : 0)
  const priceChangePct = last && prev && prev.close > 0
    ? (priceChange / prev.close) * 100
    : (last && last.open > 0 ? (priceChange / last.open) * 100 : 0)
  const isUp = priceChange >= 0

  const high24h = candles.length > 0 ? Math.max(...candles.map((c) => c.high)) : 0
  const low24h = candles.length > 0 ? Math.min(...candles.map((c) => c.low)) : 0
  const totalVolume = candles.reduce((acc, c) => acc + c.volume, 0)

  return (
    <div className="min-h-screen bg-[var(--color-bg)] text-[var(--color-text)] selection:bg-[var(--color-primary)]/20 selection:text-[var(--color-primary)] transition-colors duration-200">
      {/* Top Navbar - Glass Header */}
      <header className="sticky top-0 z-50 glass-header px-4 sm:px-8 py-3 transition-colors duration-200">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
          {/* Logo & Status Badge */}
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-[var(--color-primary)] to-[#60a5fa] flex items-center justify-center shadow-md shadow-[var(--color-primary)]/25">
              <Zap className="w-4 h-4 text-white fill-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base sm:text-lg font-bold tracking-tight text-[var(--color-text-main)]">
                  Crypto Tracker
                </h1>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 dark:bg-emerald-400 animate-pulse" />
                  LIVE
                </span>
              </div>
              <p className="text-[11px] text-[var(--color-text-muted)] hidden sm:block">
                AI Price Forecast & Real-Time Trading Terminal
              </p>
            </div>
          </div>

          {/* Center Navigation Tabs (Segmented Control) */}
          <nav role="tablist" aria-label="View" className="flex items-center p-1 rounded-xl bg-[var(--color-surface-2)] border border-[var(--color-border)] shadow-inner">
            <button
              role="tab"
              aria-selected={tab === 'dashboard'}
              onClick={() => setTab('dashboard')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                tab === 'dashboard'
                  ? 'brand-pill-active'
                  : 'brand-pill-inactive'
              }`}
            >
              <LayoutDashboard className="w-3.5 h-3.5" />
              <span>Dashboard</span>
            </button>
            <button
              role="tab"
              aria-selected={tab === 'leaderboard'}
              onClick={() => setTab('leaderboard')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                tab === 'leaderboard'
                  ? 'brand-pill-active'
                  : 'brand-pill-inactive'
              }`}
            >
              <Trophy className="w-3.5 h-3.5" />
              <span>Leaderboard</span>
            </button>
            <button
              role="tab"
              aria-selected={tab === 'forecast'}
              onClick={() => setTab('forecast')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                tab === 'forecast'
                  ? 'brand-pill-active'
                  : 'brand-pill-inactive'
              }`}
            >
              <Zap className="w-3.5 h-3.5" />
              <span>Forecast</span>
            </button>
            <button
              role="tab"
              aria-selected={tab === 'trading'}
              onClick={() => setTab('trading')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                tab === 'trading'
                  ? 'brand-pill-active'
                  : 'brand-pill-inactive'
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              <span>Trading</span>
            </button>
            <button
              role="tab"
              aria-selected={tab === 'alerts'}
              onClick={() => setTab('alerts')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                tab === 'alerts'
                  ? 'brand-pill-active'
                  : 'brand-pill-inactive'
              }`}
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Alerts</span>
            </button>
          </nav>

          {/* Right Action / Filter & Theme Switcher */}
          <div className="flex items-center gap-3">
            {tab === 'leaderboard' && <ModelPicker />}

            {tab === 'dashboard' && (
              <div className="flex flex-wrap items-center gap-2">
                {/* Symbol Selector */}
                <label className="flex items-center gap-1.5 text-xs">
                  <span className="text-[var(--color-text-muted)] hidden md:inline">Symbol</span>
                  <div className="relative">
                    <select
                      aria-label="Symbol"
                      value={symbol}
                      onChange={(e) => setSymbol(e.target.value)}
                      className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-2.5 py-1.5 text-xs font-bold text-[var(--color-primary)] focus:outline-none focus:border-[var(--color-primary)] cursor-pointer shadow-sm"
                    >
                      {(symbols.length > 0 ? symbols.map((s) => s.symbol) : [symbol]).map((s) => (
                        <option key={s} value={s} className="bg-[var(--color-surface)] text-[var(--color-text)]">
                          {s}
                        </option>
                      ))}
                    </select>
                  </div>
                </label>

                {/* Timeframe Pills */}
                <div role="group" aria-label="Timeframe" className="flex items-center p-0.5 rounded-lg bg-[var(--color-surface-2)] border border-[var(--color-border)]">
                  {TIMEFRAMES.map((tf) => (
                    <button
                      key={tf}
                      onClick={() => setTimeframe(tf)}
                      className={`px-2 py-1 rounded text-xs font-mono font-medium transition ${
                        tf === timeframe
                          ? 'bg-[var(--color-primary)] text-white font-bold shadow-sm'
                          : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface)]'
                      }`}
                    >
                      {tf}
                    </button>
                  ))}
                </div>

                {/* Refresh Button */}
                <button
                  onClick={load}
                  title="Refresh data"
                  className="p-1.5 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-primary)] hover:border-[var(--color-primary)] transition shadow-sm"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-[var(--color-primary)]' : ''}`} />
                </button>
              </div>
            )}

            {tab === 'trading' && (
              <div className="flex flex-wrap items-center gap-2">
                {/* Symbol Selector for futures terminal */}
                <label className="flex items-center gap-1.5 text-xs">
                  <span className="text-[var(--color-text-muted)] hidden md:inline">Symbol</span>
                  <div className="relative">
                    <select
                      aria-label="Trading Symbol"
                      value={symbol}
                      onChange={(e) => setSymbol(e.target.value)}
                      className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-2.5 py-1.5 text-xs font-bold text-[var(--color-primary)] focus:outline-none focus:border-[var(--color-primary)] cursor-pointer shadow-sm"
                    >
                      {(symbols.length > 0 ? symbols.map((s) => s.symbol) : [symbol]).map((s) => (
                        <option key={s} value={s} className="bg-[var(--color-surface)] text-[var(--color-text)]">
                          {s}
                        </option>
                      ))}
                    </select>
                  </div>
                </label>
              </div>
            )}

            {/* Theme Toggle Button (Light / Dark) */}
            <button
              onClick={toggleTheme}
              title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} mode`}
              aria-label="Toggle Theme"
              className="p-2 rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-primary)] hover:border-[var(--color-primary)] shadow-sm transition-all duration-200 cursor-pointer"
            >
              {theme === 'dark' ? (
                <Sun className="w-4 h-4 text-amber-400 hover:rotate-45 transition-transform duration-300" />
              ) : (
                <Moon className="w-4 h-4 text-[var(--color-primary)] hover:-rotate-12 transition-transform duration-300" />
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Body */}
      <main className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
        {tab === 'leaderboard' ? (
          <Leaderboard />
        ) : tab === 'trading' ? (
          <FuturesTerminal symbol={symbol} />
        ) : tab === 'forecast' ? (
          <ForecastCompare />
        ) : tab === 'alerts' ? (
          <AlertsPanel />
        ) : (
          <>
            {error && (
              <div role="alert" className="flex items-center gap-2.5 p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-600 dark:text-rose-400 text-xs shadow-sm">
                <AlertCircle className="w-4 h-4 text-rose-500 shrink-0" />
                <span>Load failed: {error}</span>
              </div>
            )}

            {/* Hero Bento Grid: Chart + Live Ticker Summary */}
            <section className="grid grid-cols-1 lg:grid-cols-[2.5fr_1fr] gap-6">
              {/* Left Panel: Candlestick & Volume Chart */}
              <div className="p-4 sm:p-5 surface-card relative flex flex-col justify-between">
                <CandleChart candles={candles} symbol={symbol} timeframe={timeframe} />
              </div>

              {/* Right Panel: Real-time Stats & AI Forecast */}
              <div className="flex flex-col gap-4">
                {/* Real-time Price Card */}
                <div className="p-5 surface-card flex flex-col justify-between relative overflow-hidden">
                  <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)] mb-1">
                    <span className="font-semibold flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5 text-[var(--color-primary)]" />
                      Last Close ({timeframe})
                    </span>
                    <span className="text-[11px] font-mono text-[var(--color-text-subtle)] uppercase font-semibold">{symbol}</span>
                  </div>

                  <div className="my-2">
                    <div
                      data-testid="last-price"
                      className="text-3xl sm:text-4xl font-extrabold font-mono tracking-tight tabular-nums text-[var(--color-text-main)]"
                    >
                      {last ? fmtPrice(last.close) : '—'}
                    </div>

                    {last && (
                      <div className="flex items-center gap-2 mt-2">
                        <span
                          className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-xs font-bold font-mono tabular-nums ${
                            isUp
                              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
                              : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/30'
                          }`}
                        >
                          {isUp ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                          {isUp ? '+' : ''}
                          {fmtPrice(priceChange)} ({isUp ? '+' : ''}{priceChangePct.toFixed(2)}%)
                        </span>
                        <span className="text-[11px] text-[var(--color-text-muted)]">vs prev</span>
                      </div>
                    )}
                  </div>

                  {/* 24h High/Low Mini Bento */}
                  <div className="grid grid-cols-2 gap-2 pt-3 mt-2 border-t border-[var(--color-border)] text-xs">
                    <div className="p-2.5 rounded-xl bg-[var(--color-surface-2)] border border-[var(--color-border-subtle)]">
                      <span className="text-[10px] text-[var(--color-text-muted)] block font-semibold">24h High</span>
                      <span className="font-mono font-bold tabular-nums text-emerald-600 dark:text-emerald-400 text-sm">
                        {high24h > 0 ? fmtPrice(high24h) : '—'}
                      </span>
                    </div>
                    <div className="p-2.5 rounded-xl bg-[var(--color-surface-2)] border border-[var(--color-border-subtle)]">
                      <span className="text-[10px] text-[var(--color-text-muted)] block font-semibold">24h Low</span>
                      <span className="font-mono font-bold tabular-nums text-rose-600 dark:text-rose-400 text-sm">
                        {low24h > 0 ? fmtPrice(low24h) : '—'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* AI Forecast & Signal Widget */}
                <div className="p-5 surface-card relative overflow-hidden border-[var(--color-primary)]/30 bg-gradient-to-b from-[var(--color-brand-50)]/60 to-[var(--color-surface)] dark:from-[var(--color-brand-900)]/20 dark:to-[var(--color-surface)]">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-1.5">
                      <div className="p-1.5 rounded-lg bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
                        <Zap className="w-4 h-4 text-[var(--color-primary)] fill-[var(--color-primary)]/20" />
                      </div>
                      <span className="text-xs font-bold text-[var(--color-primary)] uppercase tracking-wider">AI Forecast Status</span>
                    </div>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--color-primary)]/10 text-[var(--color-primary)] font-mono font-bold border border-[var(--color-primary)]/20">
                      Auto-eval
                    </span>
                  </div>

                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between items-center text-[var(--color-text-muted)]">
                      <span className="font-medium">Total Volume:</span>
                      <span className="font-mono font-bold tabular-nums text-[var(--color-text-main)]">
                        {totalVolume.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between items-center text-[var(--color-text-muted)]">
                      <span className="font-medium">Candles Loaded:</span>
                      <span className="font-mono font-bold tabular-nums text-[var(--color-primary)]">
                        {candles.length} periods
                      </span>
                    </div>
                    <div className="flex justify-between items-center text-[var(--color-text-muted)]">
                      <span className="font-medium">Trend Momentum:</span>
                      <span className={`font-bold ${isUp ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                        {isUp ? '🟢 Bullish Momentum' : '🔴 Bearish Retracement'}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {/* Historical OHLCV Table */}
            <section className="surface-card overflow-hidden">
              <div className="flex items-center justify-between p-4 sm:p-5 border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
                <div className="flex items-center gap-2">
                  <BarChart2 className="w-4 h-4 text-[var(--color-primary)]" />
                  <h3 className="text-sm font-bold text-[var(--color-text-main)] uppercase tracking-wide">
                    Historical OHLCV Data
                  </h3>
                </div>
                <span className="text-xs text-[var(--color-text-muted)] font-mono font-semibold">
                  {candles.length} records
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-[var(--color-surface-2)] text-left text-[var(--color-text-muted)] uppercase tracking-wider border-b border-[var(--color-border)] font-bold">
                      <th className="py-3 px-4">Open time</th>
                      <th className="py-3 px-4 text-right">Open</th>
                      <th className="py-3 px-4 text-right">High</th>
                      <th className="py-3 px-4 text-right">Low</th>
                      <th className="py-3 px-4 text-right">Close</th>
                      <th className="py-3 px-4 text-right">Volume</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border-subtle)] font-mono tabular-nums">
                    {[...candles].reverse().map((c) => {
                      const isRowUp = c.close >= c.open
                      return (
                        <tr
                          key={c.open_time}
                          data-testid="candle-row"
                          className="hover:bg-[var(--color-surface-2)]/80 transition-colors"
                        >
                          <td className="py-3 px-4 text-[var(--color-text-muted)] font-sans font-medium">
                            {new Date(c.open_time).toISOString().replace('T', ' ').slice(0, 16)}
                          </td>
                          <td className="py-3 px-4 text-right text-[var(--color-text-main)]">{fmtPrice(c.open)}</td>
                          <td className="py-3 px-4 text-right text-[var(--color-text-main)]">{fmtPrice(c.high)}</td>
                          <td className="py-3 px-4 text-right text-[var(--color-text-main)]">{fmtPrice(c.low)}</td>
                          <td
                            className={`py-3 px-4 text-right font-bold ${
                              isRowUp ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
                            }`}
                          >
                            {fmtPrice(c.close)}
                          </td>
                          <td className="py-3 px-4 text-right text-[var(--color-text-muted)]">{c.volume.toFixed(2)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  )
}

export default App

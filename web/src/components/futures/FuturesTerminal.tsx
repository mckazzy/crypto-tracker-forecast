import { useCallback, useEffect, useRef, useState } from 'react'
import { RefreshCw, UserCircle2 } from 'lucide-react'
import {
  connectTradeWs,
  fetchAccount,
  fetchFuturesKlines,
  fetchPositions,
  getToken,
  placeOrder,
  resetAccount,
  type FuturesAccount,
  type FuturesPosition,
  type KlineFrame,
  type OrderPayload,
} from '../../lib/futures'
import AuthModal from './AuthModal'
import FuturesChart from './FuturesChart'
import OrderForm from './OrderForm'
import PositionsPanel from './PositionsPanel'
import TradeHeader from './TradeHeader'

const MAX_CHART_CANDLES = 500

export function FuturesTerminal({ symbol }: { symbol: string }) {
  const [token, setToken] = useState<string | null>(() => getToken())
  const [authOpen, setAuthOpen] = useState(false)
  const [account, setAccount] = useState<FuturesAccount | null>(null)
  const [mark, setMark] = useState<number | null>(null)
  const [prevMark, setPrevMark] = useState<number | null>(null)
  const [candles, setCandles] = useState<KlineFrame[]>([])
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [positions, setPositions] = useState<FuturesPosition[]>([])
  const candleRef = useRef<KlineFrame[]>([])

  const authed = token != null

  const loadAccount = useCallback(async () => {
    if (!token) return
    try {
      const acc = await fetchAccount()
      setAccount(acc)
      setError(null)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      if (msg.includes('401') || msg.toLowerCase().includes('token')) {
        setToken(null)
        setAuthOpen(true)
      } else {
        setError(msg)
      }
    }
  }, [token])

  useEffect(() => {
    loadAccount()
  }, [loadAccount, refreshKey])

  // WS mark + kline
  useEffect(() => {
    const cleanup = connectTradeWs({
      symbol,
      onMark: (m) => {
        setPrevMark((p) => (p == null ? null : p))
        setMark((prev) => {
          setPrevMark(prev)
          return m
        })
      },
      onKline: (k) => {
        if (candleRef.current.length === 0 || k.open_time > candleRef.current[candleRef.current.length - 1].open_time) {
          candleRef.current = [...candleRef.current, k].slice(-MAX_CHART_CANDLES)
          setCandles(candleRef.current)
        } else {
          // update candle cuối
          const next = [...candleRef.current]
          next[next.length - 1] = k
          candleRef.current = next
          setCandles(next)
        }
      },
    })
    return cleanup
  }, [symbol])

  // Seed chart từ REST khi WS kline chưa có frame (fstream push có thể bị drop).
  // Chỉ seed 1 lần mỗi symbol; KHÔNG đè data WS đã có (guard candleRef.length).
  useEffect(() => {
    let cancelled = false
    const seed = async () => {
      if (candleRef.current.length > 0) return
      try {
        const frames = await fetchFuturesKlines(symbol)
        if (cancelled || candleRef.current.length > 0) return
        if (frames.length > 0) {
          candleRef.current = frames.slice(-MAX_CHART_CANDLES)
          setCandles(candleRef.current)
        }
      } catch {
        /* REST cũng không có — chart giữ trạng thái rỗng, chờ WS */
      }
    }
    seed()
    return () => {
      cancelled = true
    }
  }, [symbol])

  const handleOrder = async (payload: OrderPayload) => {
    if (!token) {
      setAuthOpen(true)
      return
    }
    await placeOrder(payload)
    setRefreshKey((k) => k + 1)
  }

  const handleReset = async () => {
    if (!confirm('Reset virtual account to 10,000 USDT? All positions & orders will be closed.')) return
    try {
      await resetAccount()
      setRefreshKey((k) => k + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  useEffect(() => {
    if (!token) return
    fetchPositions()
      .then((p) => setPositions(p))
      .catch(() => {})
  }, [token, refreshKey])

  const activePos = positions.find((p) => p.symbol === symbol && p.status === 'OPEN') ?? null

  return (
    <div className="space-y-4">
      <TradeHeader symbol={symbol} mark={mark} prevMark={prevMark} />

      {/* Account bar */}
      <div className="surface-card px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4 text-xs">
          <div>
            <span className="text-[var(--color-text-muted)] block text-[10px] font-semibold">Balance</span>
            <span className="font-mono font-bold tabular-nums text-[var(--color-text-main)]" data-testid="account-balance">
              {account ? account.balance.toFixed(2) : '—'} USDT
            </span>
          </div>
          <div>
            <span className="text-[var(--color-text-muted)] block text-[10px] font-semibold">Margin Used</span>
            <span className="font-mono font-bold tabular-nums text-[var(--color-primary)]">
              {account ? account.margin_used.toFixed(2) : '—'} USDT
            </span>
          </div>
          <div>
            <span className="text-[var(--color-text-muted)] block text-[10px] font-semibold">Available</span>
            <span className="font-mono font-bold tabular-nums text-emerald-600 dark:text-emerald-400">
              {account ? Math.max(0, account.balance - account.margin_used).toFixed(2) : '—'} USDT
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {authed ? (
            <>
              <button
                onClick={() => setRefreshKey((k) => k + 1)}
                className="p-1.5 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-primary)] transition"
                title="Refresh"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={handleReset}
                className="px-3 py-1.5 rounded-lg bg-[var(--color-surface-2)] border border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-amber-500 text-xs font-semibold transition"
                data-testid="reset-account"
              >
                Reset Wallet
              </button>
            </>
          ) : (
            <button
              onClick={() => setAuthOpen(true)}
              className="px-3 py-1.5 rounded-lg bg-[var(--color-primary)] text-white text-xs font-bold hover:opacity-90 transition"
              data-testid="login-button"
            >
              <span className="inline-flex items-center gap-1.5">
                <UserCircle2 className="w-3.5 h-3.5" />
                Sign in to trade
              </span>
            </button>
          )}
        </div>
      </div>

      {error && (
        <div role="alert" className="text-xs text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {/* Chart + Order form */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-4">
        <div className="surface-card p-3">
          <FuturesChart
            candles={candles}
            entry={activePos?.entry ?? null}
            tp={activePos?.tp ?? null}
            sl={activePos?.sl ?? null}
            liq={activePos?.liq_price ?? null}
          />
        </div>
        <OrderForm symbol={symbol} mark={mark} onSubmit={handleOrder} />
      </div>

      <PositionsPanel
        mark={mark}
        refreshKey={refreshKey}
        onChanged={() => setRefreshKey((k) => k + 1)}
        onError={(m) => setError(m)}
        onUnauthorized={() => {
          setToken(null)
          setAuthOpen(true)
        }}
      />

      <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} onAuthed={(t) => setToken(t)} />
    </div>
  )
}

export default FuturesTerminal

import { useMemo, useState } from 'react'
import { calcLiqPrice, calcMargin, type OrderPayload } from '../../lib/futures'

interface OrderFormProps {
  symbol: string
  mark: number | null
  onSubmit: (payload: OrderPayload) => Promise<void>
}

const LEVERAGE_STEPS = [1, 2, 5, 10, 20, 50, 100, 125]

export function OrderForm({ symbol, mark, onSubmit }: OrderFormProps) {
  const [side, setSide] = useState<'LONG' | 'SHORT'>('LONG')
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET')
  const [leverage, setLeverage] = useState(10)
  const [notional, setNotional] = useState('100')
  const [limitPrice, setLimitPrice] = useState('')
  const [tp, setTp] = useState('')
  const [sl, setSl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const notionalNum = parseFloat(notional) || 0
  const priceNum = orderType === 'LIMIT' ? parseFloat(limitPrice) || 0 : mark ?? 0

  const precheck = useMemo(() => {
    if (notionalNum <= 0 || priceNum <= 0) return null
    const margin = calcMargin(notionalNum, leverage)
    const entry = priceNum
    const liq = calcLiqPrice(entry, leverage, side)
    return { margin, liq }
  }, [notionalNum, priceNum, leverage, side])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (orderType === 'LIMIT' && !(parseFloat(limitPrice) > 0)) {
      setError('Limit price required')
      return
    }
    setBusy(true)
    try {
      const payload: OrderPayload = {
        symbol,
        side,
        type: orderType,
        notional_usdt: notionalNum,
        leverage,
      }
      if (orderType === 'LIMIT') payload.price = parseFloat(limitPrice)
      if (parseFloat(tp) > 0) payload.tp = parseFloat(tp)
      if (parseFloat(sl) > 0) payload.sl = parseFloat(sl)
      await onSubmit(payload)
      if (orderType === 'MARKET') setNotional('100')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="surface-card p-4 space-y-3" data-testid="order-form">
      {/* Side toggle */}
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => setSide('LONG')}
          data-testid="side-long"
          className={`py-2 rounded-lg text-xs font-bold transition ${
            side === 'LONG'
              ? 'bg-emerald-500 text-white'
              : 'bg-[var(--color-surface-2)] text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
          }`}
        >
          Long / Buy
        </button>
        <button
          type="button"
          onClick={() => setSide('SHORT')}
          data-testid="side-short"
          className={`py-2 rounded-lg text-xs font-bold transition ${
            side === 'SHORT'
              ? 'bg-rose-500 text-white'
              : 'bg-[var(--color-surface-2)] text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
          }`}
        >
          Short / Sell
        </button>
      </div>

      {/* Order type */}
      <div className="grid grid-cols-2 gap-2">
        {(['MARKET', 'LIMIT'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setOrderType(t)}
            data-testid={`type-${t.toLowerCase()}`}
            className={`py-1.5 rounded-lg text-xs font-semibold transition ${
              orderType === t
                ? 'bg-[var(--color-primary)]/15 text-[var(--color-primary)] border border-[var(--color-primary)]/40'
                : 'bg-[var(--color-surface-2)] text-[var(--color-text-muted)] border border-transparent'
            }`}
          >
            {t === 'MARKET' ? 'Market' : 'Limit'}
          </button>
        ))}
      </div>

      {/* Leverage slider */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-[11px] font-semibold text-[var(--color-text-muted)]">Leverage</label>
          <span className="text-xs font-mono font-bold text-[var(--color-primary)]" data-testid="leverage-value">
            {leverage}x
          </span>
        </div>
        <input
          type="range"
          min={1}
          max={125}
          step={1}
          value={leverage}
          onChange={(e) => setLeverage(parseInt(e.target.value))}
          className="w-full"
          aria-label="Leverage"
        />
        <div className="flex justify-between mt-1">
          {LEVERAGE_STEPS.map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => setLeverage(l)}
              className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                leverage === l ? 'text-[var(--color-primary)] font-bold' : 'text-[var(--color-text-muted)]'
              }`}
            >
              {l}x
            </button>
          ))}
        </div>
      </div>

      {/* Notional USDT */}
      <div>
        <label className="block text-[11px] font-semibold text-[var(--color-text-muted)] mb-1">
          Amount (USDT)
        </label>
        <input
          type="number"
          min={1}
          step={1}
          value={notional}
          onChange={(e) => setNotional(e.target.value)}
          data-testid="notional-input"
          className="w-full px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-xs font-mono text-[var(--color-text-main)] focus:outline-none focus:border-[var(--color-primary)]"
        />
        {mark != null && notionalNum > 0 && (
          <p className="text-[10px] text-[var(--color-text-muted)] mt-1 font-mono">
            ≈ {(notionalNum / mark).toFixed(6)} {symbol.replace('USDT', '')}
          </p>
        )}
      </div>

      {/* Limit price */}
      {orderType === 'LIMIT' && (
        <div>
          <label className="block text-[11px] font-semibold text-[var(--color-text-muted)] mb-1">
            Limit Price (USDT)
          </label>
          <input
            type="number"
            min={0}
            step="any"
            value={limitPrice}
            onChange={(e) => setLimitPrice(e.target.value)}
            data-testid="limit-price-input"
            className="w-full px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-xs font-mono text-[var(--color-text-main)] focus:outline-none focus:border-[var(--color-primary)]"
          />
        </div>
      )}

      {/* TP / SL */}
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-[11px] font-semibold text-[var(--color-text-muted)] mb-1">
            Take Profit
          </label>
          <input
            type="number"
            min={0}
            step="any"
            value={tp}
            onChange={(e) => setTp(e.target.value)}
            data-testid="tp-input"
            placeholder="optional"
            className="w-full px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-xs font-mono text-[var(--color-text-main)] focus:outline-none focus:border-[var(--color-primary)]"
          />
        </div>
        <div>
          <label className="block text-[11px] font-semibold text-[var(--color-text-muted)] mb-1">
            Stop Loss
          </label>
          <input
            type="number"
            min={0}
            step="any"
            value={sl}
            onChange={(e) => setSl(e.target.value)}
            data-testid="sl-input"
            placeholder="optional"
            className="w-full px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-xs font-mono text-[var(--color-text-main)] focus:outline-none focus:border-[var(--color-primary)]"
          />
        </div>
      </div>

      {/* Pre-check */}
      {precheck && (
        <div className="grid grid-cols-2 gap-2 text-[11px] bg-[var(--color-surface-2)] rounded-lg p-2.5">
          <div>
            <span className="text-[var(--color-text-muted)] block">Margin</span>
            <span className="font-mono font-bold text-[var(--color-text-main)] tabular-nums">
              {precheck.margin.toFixed(2)} USDT
            </span>
          </div>
          <div>
            <span className="text-[var(--color-text-muted)] block">Liq. Price</span>
            <span className="font-mono font-bold text-[var(--color-text-main)] tabular-nums" data-testid="liq-price">
              {precheck.liq.toLocaleString('en-US', { maximumFractionDigits: 2 })}
            </span>
          </div>
        </div>
      )}

      {error && (
        <div role="alert" className="text-xs text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={busy || !mark}
        data-testid="order-submit"
        className={`w-full py-2.5 rounded-lg text-xs font-bold text-white transition disabled:opacity-50 ${
          side === 'LONG' ? 'bg-emerald-500 hover:bg-emerald-600' : 'bg-rose-500 hover:bg-rose-600'
        }`}
      >
        {busy ? 'Placing…' : `${side === 'LONG' ? 'Buy / Long' : 'Sell / Short'} ${symbol.replace('USDT', '')} (${orderType.toLowerCase()})`}
      </button>
    </form>
  )
}

export default OrderForm

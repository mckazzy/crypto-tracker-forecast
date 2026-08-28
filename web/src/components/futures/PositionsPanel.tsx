import { useEffect, useState } from 'react'
import { Layers } from 'lucide-react'
import {
  cancelOrder,
  closePosition,
  fetchOrders,
  fetchPositions,
  fetchTrades,
  type FuturesOrder,
  type FuturesPosition,
} from '../../lib/futures'

interface PositionsPanelProps {
  mark: number | null
  refreshKey: number
  onChanged: () => void
  onError: (msg: string) => void
  onUnauthorized: () => void
}

type Tab = 'positions' | 'orders' | 'history'

export function PositionsPanel({ mark, refreshKey, onChanged, onError, onUnauthorized }: PositionsPanelProps) {
  const [tab, setTab] = useState<Tab>('positions')
  const [positions, setPositions] = useState<FuturesPosition[]>([])
  const [orders, setOrders] = useState<FuturesOrder[]>([])
  const [history, setHistory] = useState<FuturesPosition[]>([])

  const load = async () => {
    try {
      const [pos, ord, hist] = await Promise.all([fetchPositions(), fetchOrders(), fetchTrades()])
      setPositions(pos)
      setOrders(ord)
      setHistory(hist)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      if (msg.includes('401') || msg.toLowerCase().includes('token')) onUnauthorized()
      else onError(msg)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey])

  const livePnl = (p: FuturesPosition): number => {
    if (mark == null) return 0
    return p.side === 'LONG' ? (mark - p.entry) * p.qty : (p.entry - mark) * p.qty
  }

  const onClose = async (p: FuturesPosition) => {
    try {
      await closePosition(p.id)
      onChanged()
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err))
    }
  }

  const onCancel = async (o: FuturesOrder) => {
    try {
      await cancelOrder(o.id)
      onChanged()
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="surface-card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-[var(--color-primary)]" />
          <h3 className="text-sm font-bold text-[var(--color-text-main)] uppercase tracking-wide">Futures</h3>
        </div>
        <div className="flex items-center gap-1" role="tablist">
          {(
            [
              ['positions', 'Positions'],
              ['orders', 'Open Orders'],
              ['history', 'History'],
            ] as [Tab, string][]
          ).map(([t, label]) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                tab === t
                  ? 'bg-[var(--color-primary)]/15 text-[var(--color-primary)]'
                  : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Positions */}
      {tab === 'positions' && (
        <div className="overflow-x-auto">
          {positions.length === 0 ? (
            <div className="py-10 text-center text-[var(--color-text-muted)] text-xs">
              No open positions — place an order to start
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-[var(--color-surface-2)] text-left text-[var(--color-text-muted)] uppercase tracking-wider border-b border-[var(--color-border)] font-semibold">
                  <th className="py-2.5 px-4">Symbol</th>
                  <th className="py-2.5 px-4">Side</th>
                  <th className="py-2.5 px-4 text-right">Entry</th>
                  <th className="py-2.5 px-4 text-right">Mark</th>
                  <th className="py-2.5 px-4 text-right">Qty</th>
                  <th className="py-2.5 px-4 text-right">Lev</th>
                  <th className="py-2.5 px-4 text-right">Margin</th>
                  <th className="py-2.5 px-4 text-right">Liq</th>
                  <th className="py-2.5 px-4 text-right">PnL</th>
                  <th className="py-2.5 px-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border-subtle)] font-mono tabular-nums">
                {positions.map((p) => {
                  const pnl = livePnl(p)
                  const up = pnl >= 0
                  return (
                    <tr key={p.id} data-testid="position-row" className="hover:bg-[var(--color-surface-2)]/60">
                      <td className="py-2.5 px-4 font-sans font-bold">{p.symbol}</td>
                      <td className="py-2.5 px-4">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            p.side === 'LONG'
                              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                              : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                          }`}
                        >
                          {p.side}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 text-right">{p.entry.toFixed(2)}</td>
                      <td className="py-2.5 px-4 text-right">{mark != null ? mark.toFixed(2) : '—'}</td>
                      <td className="py-2.5 px-4 text-right">{p.qty}</td>
                      <td className="py-2.5 px-4 text-right">{p.leverage}x</td>
                      <td className="py-2.5 px-4 text-right">{p.margin.toFixed(2)}</td>
                      <td className="py-2.5 px-4 text-right text-amber-600 dark:text-amber-400">
                        {p.liq_price.toFixed(2)}
                      </td>
                      <td className={`py-2.5 px-4 text-right font-bold ${up ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                        {up ? '+' : ''}{pnl.toFixed(2)}
                      </td>
                      <td className="py-2.5 px-4 text-right font-sans">
                        <button
                          onClick={() => onClose(p)}
                          className="px-2.5 py-1 rounded-lg bg-[var(--color-surface-2)] hover:bg-[var(--color-surface-3)] text-[var(--color-text-main)] text-xs font-semibold border border-[var(--color-border)] transition"
                        >
                          Close
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Open Orders */}
      {tab === 'orders' && (
        <div className="overflow-x-auto">
          {orders.filter((o) => o.status === 'OPEN').length === 0 ? (
            <div className="py-10 text-center text-[var(--color-text-muted)] text-xs">No open orders</div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-[var(--color-surface-2)] text-left text-[var(--color-text-muted)] uppercase tracking-wider border-b border-[var(--color-border)] font-semibold">
                  <th className="py-2.5 px-4">Symbol</th>
                  <th className="py-2.5 px-4">Side</th>
                  <th className="py-2.5 px-4">Type</th>
                  <th className="py-2.5 px-4 text-right">Price</th>
                  <th className="py-2.5 px-4 text-right">Qty</th>
                  <th className="py-2.5 px-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border-subtle)] font-mono tabular-nums">
                {orders.filter((o) => o.status === 'OPEN').map((o) => (
                  <tr key={o.id} data-testid="order-row" className="hover:bg-[var(--color-surface-2)]/60">
                    <td className="py-2.5 px-4 font-sans font-bold">{o.symbol}</td>
                    <td className="py-2.5 px-4">{o.side}</td>
                    <td className="py-2.5 px-4">{o.type}</td>
                    <td className="py-2.5 px-4 text-right">{o.price?.toFixed(2) ?? '—'}</td>
                    <td className="py-2.5 px-4 text-right">{o.qty}</td>
                    <td className="py-2.5 px-4 font-sans">
                      <button
                        onClick={() => onCancel(o)}
                        className="px-2.5 py-1 rounded-lg bg-[var(--color-surface-2)] hover:bg-[var(--color-surface-3)] text-[var(--color-text-main)] text-xs font-semibold border border-[var(--color-border)] transition"
                      >
                        Cancel
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* History */}
      {tab === 'history' && (
        <div className="overflow-x-auto">
          {history.length === 0 ? (
            <div className="py-10 text-center text-[var(--color-text-muted)] text-xs">No closed trades yet</div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-[var(--color-surface-2)] text-left text-[var(--color-text-muted)] uppercase tracking-wider border-b border-[var(--color-border)] font-semibold">
                  <th className="py-2.5 px-4">Symbol</th>
                  <th className="py-2.5 px-4">Side</th>
                  <th className="py-2.5 px-4 text-right">Entry</th>
                  <th className="py-2.5 px-4 text-right">Exit</th>
                  <th className="py-2.5 px-4 text-right">PnL</th>
                  <th className="py-2.5 px-4">Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border-subtle)] font-mono tabular-nums">
                {history.map((p) => (
                  <tr key={p.id} data-testid="trade-row" className="hover:bg-[var(--color-surface-2)]/60">
                    <td className="py-2.5 px-4 font-sans font-bold">{p.symbol}</td>
                    <td className="py-2.5 px-4">{p.side}</td>
                    <td className="py-2.5 px-4 text-right">{p.entry.toFixed(2)}</td>
                    <td className="py-2.5 px-4 text-right">{p.exit_price?.toFixed(2) ?? '—'}</td>
                    <td className={`py-2.5 px-4 text-right font-bold ${(p.pnl ?? 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                      {p.pnl != null ? `${p.pnl >= 0 ? '+' : ''}${p.pnl.toFixed(2)}` : '—'}
                    </td>
                    <td className="py-2.5 px-4 font-sans">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[var(--color-surface-2)] text-[var(--color-text-muted)]">
                        {p.close_reason ?? '—'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

export default PositionsPanel

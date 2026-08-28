import { ArrowDownRight, ArrowUpRight } from 'lucide-react'

interface TradeHeaderProps {
  symbol: string
  mark: number | null
  prevMark: number | null
}

export function TradeHeader({ symbol, mark, prevMark }: TradeHeaderProps) {
  const dir = prevMark != null && mark != null ? (mark >= prevMark ? 'up' : mark < prevMark ? 'down' : 'flat') : 'flat'
  const color =
    dir === 'up'
      ? 'text-emerald-600 dark:text-emerald-400'
      : dir === 'down'
        ? 'text-rose-600 dark:text-rose-400'
        : 'text-[var(--color-text-main)]'

  return (
    <div className="surface-card px-4 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <span className="text-sm font-bold text-[var(--color-text-main)] font-mono">{symbol}</span>
        <span className="px-2 py-0.5 rounded-md bg-[var(--color-surface-2)] text-[var(--color-text-muted)] text-[10px] font-bold border border-[var(--color-border)]">
          USDT-M Futures
        </span>
      </div>
      <div className="flex items-center gap-1.5" data-testid="mark-price">
        {dir === 'up' ? (
          <ArrowUpRight className="w-4 h-4 text-emerald-500" />
        ) : dir === 'down' ? (
          <ArrowDownRight className="w-4 h-4 text-rose-500" />
        ) : null}
        <span className={`text-lg font-extrabold font-mono tabular-nums ${color}`}>
          {mark != null ? mark.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'}
        </span>
        {mark != null && prevMark != null && mark !== prevMark && (
          <span className={`text-[11px] font-mono font-bold ${color}`}>
            {mark >= prevMark ? '+' : ''}
            {((mark - prevMark) / prevMark * 100).toFixed(2)}%
          </span>
        )}
      </div>
    </div>
  )
}

export default TradeHeader

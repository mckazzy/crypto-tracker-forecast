import { useCallback, useEffect, useState } from 'react'
import {
  closePosition,
  fetchAlerts,
  fetchPnl,
  fetchPositions,
  submitOutcome,
  type Alert,
  type PnlSummary,
  type Position,
} from '../lib/trading'

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(2)}%`
}

function Trading() {
  const [positions, setPositions] = useState<Position[]>([])
  const [pnl, setPnl] = useState<PnlSummary | null>(null)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    Promise.all([fetchPositions(), fetchPnl(), fetchAlerts()])
      .then(([pos, p, al]) => {
        setPositions(pos)
        setPnl(p)
        setAlerts(al)
        setError(null)
      })
      .catch((e) => setError(String(e.message ?? e)))
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [load])

  const onClose = async (p: Position) => {
    try {
      await closePosition(p.id, p.entry) // paper: close tại entry (hoặc giá hiện tại)
      load()
    } catch (e) {
      setError(String(e))
    }
  }

  const onOutcome = async (p: Position, outcome: 'win' | 'lose') => {
    try {
      await submitOutcome({
        symbol: p.symbol,
        timeframe: p.timeframe,
        direction: p.direction,
        outcome,
        entry: p.entry,
        tp: p.tp,
        sl: p.sl,
        model: p.model ?? undefined,
      })
      load()
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <div className="p-6">
      <header className="mb-6">
        <h2 className="text-xl font-bold mr-4">Paper Trading</h2>
        {pnl && (
          <div className="flex gap-6 mt-2 text-sm">
            <span>
              Total P&L:{' '}
              <span className={`font-bold tabular-nums ${pnl.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {fmtPct(pnl.total_pnl)}
              </span>
            </span>
            <span>
              Win rate: <span className="font-bold tabular-nums">{fmtPct(pnl.win_rate)}</span>
            </span>
            <span>
              Closed/Open: <span className="tabular-nums">{pnl.total_closed}/{pnl.total_open}</span>
            </span>
          </div>
        )}
      </header>

      {error && (
        <div role="alert" className="mb-4 p-3 bg-red-900/50 border border-red-700 rounded text-red-200">
          Load failed: {error}
        </div>
      )}

      <section className="mb-8">
        <h3 className="text-lg font-semibold mb-2">Positions</h3>
        {positions.length === 0 ? (
          <div data-testid="positions-empty" className="p-6 text-center text-slate-400">
            No positions yet
          </div>
        ) : (
          <table className="w-full text-sm bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
            <thead>
              <tr className="bg-slate-800 text-left text-slate-300">
                <th className="p-2">Symbol</th>
                <th className="p-2">TF</th>
                <th className="p-2">Dir</th>
                <th className="p-2">Entry</th>
                <th className="p-2">TP</th>
                <th className="p-2">SL</th>
                <th className="p-2">P&L</th>
                <th className="p-2">Status</th>
                <th className="p-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.id} data-testid="position-row" className="border-t border-slate-800">
                  <td className="p-2">{p.symbol}</td>
                  <td className="p-2">{p.timeframe}</td>
                  <td className={`p-2 font-semibold ${p.direction === 'LONG' ? 'text-emerald-400' : 'text-red-400'}`}>
                    {p.direction}
                  </td>
                  <td className="p-2 tabular-nums">{p.entry.toFixed(2)}</td>
                  <td className="p-2 tabular-nums">{p.tp.toFixed(2)}</td>
                  <td className="p-2 tabular-nums">{p.sl.toFixed(2)}</td>
                  <td className={`p-2 tabular-nums ${(p.pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {p.pnl != null ? fmtPct(p.pnl) : '—'}
                  </td>
                  <td className="p-2">{p.status}</td>
                  <td className="p-2">
                    {p.status === 'open' ? (
                      <>
                        <button
                          onClick={() => onClose(p)}
                          className="mr-2 px-2 py-0.5 rounded bg-slate-700 hover:bg-slate-600 text-xs"
                        >
                          Close
                        </button>
                        <button
                          onClick={() => onOutcome(p, 'win')}
                          className="mr-1 px-2 py-0.5 rounded bg-emerald-700 hover:bg-emerald-600 text-xs"
                        >
                          Win
                        </button>
                        <button
                          onClick={() => onOutcome(p, 'lose')}
                          className="px-2 py-0.5 rounded bg-red-700 hover:bg-red-600 text-xs"
                        >
                          Lose
                        </button>
                      </>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h3 className="text-lg font-semibold mb-2">Alerts</h3>
        {alerts.length === 0 ? (
          <div className="p-6 text-center text-slate-400">No alerts yet</div>
        ) : (
          <table className="w-full text-sm bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
            <thead>
              <tr className="bg-slate-800 text-left text-slate-300">
                <th className="p-2">Symbol</th>
                <th className="p-2">Dir</th>
                <th className="p-2">Entry</th>
                <th className="p-2">Channel</th>
                <th className="p-2">Status</th>
                <th className="p-2">Sent</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id} data-testid="alert-row" className="border-t border-slate-800">
                  <td className="p-2">{a.symbol}</td>
                  <td className="p-2">{a.direction}</td>
                  <td className="p-2 tabular-nums">{a.entry?.toFixed(2) ?? '—'}</td>
                  <td className="p-2">{a.channel}</td>
                  <td className={`p-2 ${a.status === 'sent' ? 'text-emerald-400' : 'text-red-400'}`}>{a.status}</td>
                  <td className="p-2 tabular-nums">
                    {a.sent_at ? new Date(a.sent_at).toISOString().slice(0, 16).replace('T', ' ') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}

export default Trading

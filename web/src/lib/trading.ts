export interface Position {
  id: number
  symbol: string
  timeframe: string
  direction: 'LONG' | 'SHORT'
  entry: number
  tp: number
  sl: number
  opened_at: string | null
  closed_at: string | null
  exit_price: number | null
  pnl: number | null
  status: 'open' | 'closed'
  model: string | null
}

export interface PnlSummary {
  total_closed: number
  total_open: number
  total_pnl: number
  win_rate: number
  avg_pnl: number
}

export interface Alert {
  id: number
  symbol: string
  timeframe: string
  direction: string
  entry: number | null
  tp: string | null
  sl: number | null
  model: string | null
  sent_at: string | null
  channel: string
  status: string
}

export async function fetchPositions(status?: string): Promise<Position[]> {
  const params = status ? `?status=${status}` : ''
  const resp = await fetch(`/api/positions${params}`)
  if (!resp.ok) throw new Error(`positions ${resp.status}`)
  const body = await resp.json()
  return body.positions
}

export async function fetchPnl(): Promise<PnlSummary> {
  const resp = await fetch('/api/positions/pnl')
  if (!resp.ok) throw new Error(`pnl ${resp.status}`)
  return resp.json()
}

export async function closePosition(id: number, exitPrice: number): Promise<void> {
  const resp = await fetch(`/api/positions/${id}/close`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ exit_price: exitPrice }),
  })
  if (!resp.ok) throw new Error(`close ${resp.status}`)
}

export async function submitOutcome(payload: {
  symbol: string
  timeframe: string
  direction: string
  outcome: 'win' | 'lose' | 'neutral'
  entry?: number
  tp?: number
  sl?: number
  model?: string
}): Promise<{ id: number; trusted: boolean }> {
  const resp = await fetch('/api/outcomes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error(`outcome ${resp.status}`)
  return resp.json()
}

export async function fetchAlerts(): Promise<Alert[]> {
  const resp = await fetch('/api/alerts')
  if (!resp.ok) throw new Error(`alerts ${resp.status}`)
  const body = await resp.json()
  return body.alerts
}

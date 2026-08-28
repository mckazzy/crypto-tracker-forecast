export interface SignalPayload {
  version?: string
  symbol: string
  timeframe: string
  direction: 'LONG' | 'SHORT' | 'FLAT'
  probability: number
  entry: number | null
  take_profit: number[]
  stop_loss: number | null
  rr_ratio: number | null
  model: string
  valid_until: string | null
  status: string
  created_at: string | null
  token_cost: number
}

export interface CompareResponse {
  symbol: string
  timeframe: string
  results: Record<string, SignalPayload | { error: string }>
}

export interface OutcomeInfo {
  outcome: string
  user_override: boolean
  resolved_at: string | null
  score: number | null
  exit_price?: number | null
}

export interface UserForecastInput {
  symbol: string
  timeframe: string
  direction: 'LONG' | 'SHORT'
  entry?: number | null
  take_profit?: number[] | number
  stop_loss?: number | null
  probability?: number
}

export interface ForecastRecord {
  id: number
  symbol: string
  timeframe: string
  provider: string
  source: 'AI' | 'Local' | 'User'
  direction: 'LONG' | 'SHORT' | 'FLAT'
  probability: number | null
  entry: number | null
  take_profit: number[]
  stop_loss: number | null
  exit_price?: number | null
  created_at: string | null
  valid_until: string | null
  expired: boolean
  scored: boolean
  outcome: OutcomeInfo | null
}

export interface ForecastListResponse {
  forecasts: ForecastRecord[]
}

export interface RunForecastResponse {
  id: number
  symbol: string
  timeframe: string
  provider: string
  signal: SignalPayload
  valid_until: string | null
  created_at: string | null
}

export interface ScoreResponse {
  scored: boolean
  forecast_id?: number
  exit_price?: number
  score?: number
  outcome?: string
  message?: string
}

export interface ScoreAllResponse {
  scored: number
  skipped: number
  details: { id: number; score: number; exit_price?: number; outcome: string }[]
}

export interface AnalyticsResponse {
  total: number
  scored_total: number
  avg_accuracy: number
  direction_split: { LONG: number; SHORT: number; FLAT: number }
  by_source: Record<string, { total: number; scored: number; score_sum: number; wins: number; losses: number; accuracy: number }>
  by_direction: Record<string, { total: number; scored: number; score_sum: number; accuracy: number }>
}

export interface RetrainResponse {
  retrained: boolean
  model?: string
  message: string
}

export async function fetchCompare(symbol: string, timeframe: string): Promise<CompareResponse> {
  const resp = await fetch(`/api/forecast/compare/${symbol}/${timeframe}`)
  if (!resp.ok) throw new Error(`compare ${resp.status}`)
  return resp.json()
}

export async function runForecast(
  provider: 'ai' | 'local',
  symbol: string,
  timeframe: string,
): Promise<RunForecastResponse> {
  const params = new URLSearchParams({ provider, symbol, timeframe })
  const resp = await fetch(`/api/forecast/run?${params}`, { method: 'POST' })
  if (!resp.ok) {
    const body = await resp.json().catch(() => null)
    throw new Error(body?.detail ?? `run ${resp.status}`)
  }
  return resp.json()
}

export async function fetchForecasts(
  opts: { symbol?: string; timeframe?: string; provider?: string } = {},
): Promise<ForecastListResponse> {
  const params = new URLSearchParams()
  if (opts.symbol) params.set('symbol', opts.symbol)
  if (opts.timeframe) params.set('timeframe', opts.timeframe)
  if (opts.provider) params.set('provider', opts.provider)
  const qs = params.toString()
  const resp = await fetch(`/api/forecast/forecasts${qs ? `?${qs}` : ''}`)
  if (!resp.ok) throw new Error(`forecasts ${resp.status}`)
  return resp.json()
}

export async function scoreForecast(id: number): Promise<ScoreResponse> {
  const resp = await fetch(`/api/forecast/forecasts/${id}/score`, { method: 'POST' })
  if (!resp.ok) throw new Error(`score ${resp.status}`)
  return resp.json()
}

export async function scoreAllExpired(): Promise<ScoreAllResponse> {
  const resp = await fetch('/api/forecast/forecasts/score-all', { method: 'POST' })
  if (!resp.ok) throw new Error(`score-all ${resp.status}`)
  return resp.json()
}

export async function deleteForecast(id: number): Promise<{ deleted: boolean; id: number }> {
  const resp = await fetch(`/api/forecast/forecasts/${id}`, { method: 'DELETE' })
  if (!resp.ok) throw new Error(`delete ${resp.status}`)
  return resp.json()
}

export async function fetchAnalytics(): Promise<AnalyticsResponse> {
  const resp = await fetch('/api/forecast/forecasts/analytics')
  if (!resp.ok) throw new Error(`analytics ${resp.status}`)
  return resp.json()
}

export function exportForecastsCsv(symbol?: string, timeframe?: string): void {
  const params = new URLSearchParams()
  if (symbol) params.set('symbol', symbol)
  if (timeframe) params.set('timeframe', timeframe)
  const qs = params.toString()
  window.location.href = `/api/forecast/forecasts/export.csv${qs ? `?${qs}` : ''}`
}

export async function fetchForecastHistory(
  symbol?: string,
  timeframe?: string,
): Promise<{ forecasts: { id: number; symbol: string; timeframe: string; provider: string; status: string; created_at: string | null; valid_until: string | null; signal: SignalPayload; outcome: OutcomeInfo | null }[] }> {
  const params = new URLSearchParams()
  if (symbol) params.set('symbol', symbol)
  if (timeframe) params.set('timeframe', timeframe)
  const qs = params.toString()
  const resp = await fetch(`/api/forecast/history${qs ? `?${qs}` : ''}`)
  if (!resp.ok) throw new Error(`history ${resp.status}`)
  return resp.json()
}

export async function submitForecastOutcome(payload: {
  symbol: string
  timeframe: string
  direction: string
  outcome: 'win' | 'lose' | 'neutral'
  entry?: number | null
  tp?: number | null
  sl?: number | null
  model: string
}): Promise<{ id: number; trusted: boolean }> {
  const resp = await fetch('/api/outcomes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error(`outcome ${resp.status}`)
  return resp.json()
}

export async function retrainModel(symbol: string, timeframe: string): Promise<RetrainResponse> {
  const resp = await fetch(
    `/api/forecast/retrain?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`,
    { method: 'POST' },
  )
  if (!resp.ok) throw new Error(`retrain ${resp.status}`)
  return resp.json()
}

export async function submitUserForecast(payload: UserForecastInput): Promise<RunForecastResponse> {
  const tpList = Array.isArray(payload.take_profit)
    ? payload.take_profit
    : payload.take_profit != null
      ? [payload.take_profit]
      : []

  const resp = await fetch('/api/forecast/user', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...payload,
      take_profit: tpList,
    }),
  })
  if (!resp.ok) {
    const body = await resp.json().catch(() => null)
    throw new Error(body?.detail ?? `user forecast ${resp.status}`)
  }
  return resp.json()
}

export interface PendingForecastConfirmation {
  id: number
  symbol: string
  timeframe: string
  provider: string
  source: 'AI' | 'Local'
  signal: SignalPayload
  reasons: string[]
  probPct: number
  priceDeltaPct: number
  valid_until: string | null
}

export function evaluateForecastQuality(signal: SignalPayload): {
  isMarginal: boolean
  reasons: string[]
  probPct: number
  priceDeltaPct: number
} {
  const prob = signal.probability ?? 0
  const probPct = prob * 100
  const entry = signal.entry ?? 0
  const tp = signal.take_profit?.[0] ?? 0
  const priceDeltaPct = entry > 0 && tp > 0 ? (Math.abs(tp - entry) / entry) * 100 : 0

  const reasons: string[] = []
  if (prob < 0.60) {
    reasons.push(`Độ tin cậy thấp (${probPct.toFixed(1)}% < 60%)`)
  }
  if (priceDeltaPct < 1.0) {
    reasons.push(`Biên độ giá mục tiêu hẹp (${priceDeltaPct.toFixed(2)}% < 1.00% từ Entry)`)
  }

  return {
    isMarginal: reasons.length > 0,
    reasons,
    probPct,
    priceDeltaPct,
  }
}



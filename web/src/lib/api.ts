export interface Kline {
  open_time: number
  close_time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface KlinesResponse {
  symbol: string
  timeframe: string
  count: number
  data: Kline[]
}

export interface SymbolCoverage {
  symbol: string
  timeframes: { timeframe: string; count: number }[]
}

export async function fetchKlines(
  symbol: string,
  timeframe: string,
  limit = 500,
): Promise<KlinesResponse> {
  const params = new URLSearchParams({ symbol, timeframe, limit: String(limit) })
  const resp = await fetch(`/api/klines?${params}`)
  if (!resp.ok) throw new Error(`klines ${resp.status}`)
  return resp.json()
}

export async function fetchSymbols(): Promise<SymbolCoverage[]> {
  const resp = await fetch('/api/symbols')
  if (!resp.ok) throw new Error(`symbols ${resp.status}`)
  const body = await resp.json()
  return body.symbols
}

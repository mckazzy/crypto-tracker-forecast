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

export interface FetchKlinesOpts {
  /** Bypass throttle/dedupe — dùng cho manual refresh. */
  force?: boolean
}

// Throttle/dedupe /api/klines (~40 req/30s trên Dashboard do StrictMode
// double-invoke effects + nhiều component poll). Mỗi key symbol|timeframe|limit:
// - dedupe in-flight promise (gọi trùng khi đang chạy → dùng chung 1 request)
// - cache response 10s (gọi lại trong khoảng đó → trả cached)
const klinesCache = new Map<
  string,
  { promise: Promise<KlinesResponse> | null; data: KlinesResponse | null; ts: number }
>()

const KLINES_CACHE_MS = 10_000

export async function fetchKlines(
  symbol: string,
  timeframe: string,
  limit = 500,
  opts?: FetchKlinesOpts,
): Promise<KlinesResponse> {
  const key = `${symbol}|${timeframe}|${limit}`
  const now = Date.now()
  const entry = klinesCache.get(key)
  const force = opts?.force === true

  if (!force && entry) {
    if (entry.data && now - entry.ts < KLINES_CACHE_MS) return entry.data
    if (entry.promise) return entry.promise
  }

  const promise = (async () => {
    const params = new URLSearchParams({ symbol, timeframe, limit: String(limit) })
    const resp = await fetch(`/api/klines?${params}`)
    if (!resp.ok) throw new Error(`klines ${resp.status}`)
    return resp.json() as Promise<KlinesResponse>
  })()

  if (force) {
    const data = await promise
    klinesCache.set(key, { promise: null, data, ts: Date.now() })
    return data
  }

  klinesCache.set(key, { promise, data: entry?.data ?? null, ts: entry?.ts ?? 0 })
  try {
    const data = await promise
    klinesCache.set(key, { promise: null, data, ts: Date.now() })
    return data
  } catch (err) {
    // fail → bỏ in-flight để lần gọi sau retry được (không cache lỗi)
    klinesCache.set(key, { promise: null, data: entry?.data ?? null, ts: entry?.ts ?? 0 })
    throw err
  }
}

export async function fetchSymbols(): Promise<SymbolCoverage[]> {
  const resp = await fetch('/api/symbols')
  if (!resp.ok) throw new Error(`symbols ${resp.status}`)
  const body = await resp.json()
  return body.symbols
}

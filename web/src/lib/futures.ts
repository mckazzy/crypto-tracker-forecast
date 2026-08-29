// Futures demo exchange API client + WS hooks (SP5).
// Owner duy nhất của frame parsing (server-normalized) + pre-check math
// (liq price mirror backend với MMR buffer 0.5%).

export interface FuturesAccount {
  balance: number
  margin_used: number
  unrealized_pnl: number
}

export interface FuturesPosition {
  id: number
  user_id: number
  symbol: string
  side: 'LONG' | 'SHORT'
  entry: number
  qty: number
  leverage: number
  margin: number
  liq_price: number
  tp: number | null
  sl: number | null
  status: 'OPEN' | 'CLOSED'
  pnl: number | null
  exit_price: number | null
  close_reason: string | null
  created_at: string | null
}

export interface FuturesOrder {
  id: number
  symbol: string
  side: 'LONG' | 'SHORT'
  type: 'MARKET' | 'LIMIT'
  price: number | null
  qty: number
  leverage: number
  tp: number | null
  sl: number | null
  status: 'OPEN' | 'FILLED' | 'CANCELLED'
  created_at: string | null
}

export interface MarkFrame {
  type: 'markPrice'
  symbol: string
  mark: number
  ts: number
}

export interface KlineFrame {
  type: 'kline'
  symbol: string
  timeframe: string
  open_time: number
  close_time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  is_closed: boolean
}

export type RelayFrame = MarkFrame | KlineFrame

export interface OrderPayload {
  symbol: string
  side: 'LONG' | 'SHORT'
  type: 'MARKET' | 'LIMIT'
  notional_usdt: number
  leverage: number
  price?: number
  tp?: number
  sl?: number
}

const TOKEN_KEY = 'futures_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json', ...(extra ?? {}) }
  const token = getToken()
  if (token) h['Authorization'] = `Bearer ${token}`
  return h
}

async function handle<T>(resp: Response): Promise<T> {
  if (resp.status === 401) {
    clearToken()
  }
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const body = await resp.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return resp.json() as Promise<T>
}

// ---- Auth ----

export async function register(username: string, password: string): Promise<string> {
  const r = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const body = await handle<{ token: string }>(r)
  return body.token
}

export async function login(username: string, password: string): Promise<string> {
  const r = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const body = await handle<{ token: string }>(r)
  return body.token
}

// ---- Account / Orders / Positions ----

export async function fetchAccount(): Promise<FuturesAccount> {
  const r = await fetch('/api/futures/account', { headers: authHeaders() })
  return handle<FuturesAccount>(r)
}

export async function resetAccount(): Promise<void> {
  const r = await fetch('/api/futures/account/reset', {
    method: 'POST',
    headers: authHeaders(),
  })
  await handle<{ ok: boolean }>(r)
}

export async function placeOrder(payload: OrderPayload): Promise<{ id: number; status: string }> {
  const body: Record<string, unknown> = {
    symbol: payload.symbol,
    side: payload.side,
    type: payload.type,
    notional_usdt: payload.notional_usdt,
    leverage: payload.leverage,
  }
  if (payload.type === 'LIMIT') body.price = payload.price
  if (payload.tp != null) body.tp = payload.tp
  if (payload.sl != null) body.sl = payload.sl
  const r = await fetch('/api/futures/orders', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body),
  })
  return handle<{ id: number; status: string }>(r)
}

export async function cancelOrder(orderId: number): Promise<void> {
  const r = await fetch(`/api/futures/orders/${orderId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  await handle<{ ok: boolean }>(r)
}

export async function fetchPositions(status?: string): Promise<FuturesPosition[]> {
  const qs = status ? `?status=${status}` : ''
  const r = await fetch(`/api/futures/positions${qs}`, { headers: authHeaders() })
  const body = await handle<{ positions: FuturesPosition[] }>(r)
  return body.positions
}

export async function fetchOrders(): Promise<FuturesOrder[]> {
  const r = await fetch('/api/futures/orders', { headers: authHeaders() })
  const body = await handle<{ orders: FuturesOrder[] }>(r)
  return body.orders
}

export async function fetchTrades(): Promise<FuturesPosition[]> {
  const r = await fetch('/api/futures/trades', { headers: authHeaders() })
  const body = await handle<{ trades: FuturesPosition[] }>(r)
  return body.trades
}

export async function closePosition(posId: number): Promise<{ pnl: number }> {
  const r = await fetch(`/api/futures/positions/${posId}/close`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({}),
  })
  return handle<{ pnl: number }>(r)
}

export async function fetchMark(symbol: string): Promise<number> {
  const r = await fetch(`/api/futures/mark/${symbol}`, { headers: authHeaders() })
  const body = await handle<{ mark: number }>(r)
  return body.mark
}

export interface KlinesResponse {
  symbol: string
  timeframe: string
  klines: KlineFrame[]
}

// Seed chart futures từ REST (public market data, không cần auth). Dùng khi WS
// kline chưa có frame — /api/klines hiện có không có timeframe 1m nên không dùng được.
export async function fetchFuturesKlines(
  symbol: string,
  timeframe = '1m',
  limit = 200,
): Promise<KlineFrame[]> {
  const r = await fetch(
    `/api/futures/klines/${symbol}?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`,
  )
  const body = await handle<KlinesResponse>(r)
  return body.klines
}

// ---- Pre-check math (mirror backend formulas + MMR buffer 0.5%) ----

export const MMR_BUFFER = 0.005

export function calcMargin(notionalUsdt: number, leverage: number): number {
  return notionalUsdt / leverage
}

export function calcLiqPrice(entry: number, leverage: number, side: 'LONG' | 'SHORT'): number {
  if (side === 'LONG') return entry * (1 - 1 / leverage + MMR_BUFFER)
  return entry * (1 + 1 / leverage - MMR_BUFFER)
}

export function calcPnl(entry: number, mark: number, qty: number, side: 'LONG' | 'SHORT'): number {
  return side === 'LONG' ? (mark - entry) * qty : (entry - mark) * qty
}

// ---- WS hook ----

export interface UseMarkPriceOptions {
  symbol: string
  onMark?: (mark: number) => void
  onKline?: (frame: KlineFrame) => void
}

export function wsUrl(symbol: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws/trade/${symbol}`
}

export function connectTradeWs(opts: UseMarkPriceOptions): () => void {
  let ws: WebSocket | null = null
  let closed = false
  let timer: ReturnType<typeof setTimeout> | null = null
  let reconnectDelay = 1000
  let lastFrameTs = 0
  let silenceTimer: ReturnType<typeof setInterval> | null = null

  const poll = () => {
    fetchMark(opts.symbol)
      .then((mark) => opts.onMark?.(mark))
      .catch(() => {})
  }

  const open = () => {
    if (closed) return
    ws = new WebSocket(wsUrl(opts.symbol))
    ws.onopen = () => {
      reconnectDelay = 1000
      // baseline silence mới cho connection mới (chưa có frame nào)
      lastFrameTs = Date.now()
    }
    ws.onmessage = (ev) => {
      lastFrameTs = Date.now()
      try {
        const frame = JSON.parse(ev.data as string) as RelayFrame
        if (frame.type === 'markPrice') {
          opts.onMark?.(frame.mark)
        } else if (frame.type === 'kline') {
          opts.onKline?.(frame)
        }
      } catch {
        /* drop malformed frame */
      }
    }
    ws.onclose = () => {
      if (closed) return
      // fallback polling khi WS đứt + reconnect với backoff + jitter
      poll()
      timer = setTimeout(open, reconnectDelay + Math.random() * 500)
      reconnectDelay = Math.min(reconnectDelay * 2, 15000)
    }
    ws.onerror = () => {
      ws?.close()
    }
  }

  // Watchdog: WS OPEN nhưng im lặng >10s → poll REST (fstream push frames có thể
  // bị network drop — onclose không fire nên poll() trong onclose không cover).
  silenceTimer = setInterval(() => {
    if (closed) return
    const s = ws
    if (s && s.readyState === WebSocket.OPEN && Date.now() - lastFrameTs > 10_000) {
      poll()
    }
  }, 5000)

  open()

  return () => {
    closed = true
    if (timer) clearTimeout(timer)
    if (silenceTimer) clearInterval(silenceTimer)
    ws?.close()
  }
}

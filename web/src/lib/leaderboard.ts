export interface LeaderboardEntry {
  name: string
  signals: number
  ok_signals: number
  total_token_cost: number
}

export interface LeaderboardResponse {
  symbol: string | null
  timeframe: string | null
  providers: LeaderboardEntry[]
}

export async function fetchLeaderboard(
  symbol?: string,
  timeframe?: string,
): Promise<LeaderboardResponse> {
  const params = new URLSearchParams()
  if (symbol) params.set('symbol', symbol)
  if (timeframe) params.set('timeframe', timeframe)
  const qs = params.toString()
  const resp = await fetch(`/api/leaderboard${qs ? `?${qs}` : ''}`)
  if (!resp.ok) throw new Error(`leaderboard ${resp.status}`)
  return resp.json()
}

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Leaderboard from '../components/Leaderboard'
import { fetchLeaderboard, type LeaderboardEntry } from '../lib/leaderboard'

vi.mock('../lib/leaderboard', () => ({
  fetchLeaderboard: vi.fn(),
}))

const mockedFetch = vi.mocked(fetchLeaderboard)

const sampleProviders: LeaderboardEntry[] = [
  { name: 'deepseek-v4', model_type: 'llm', signals: 10, ok_signals: 9, total_token_cost: 1500 },
  { name: 'intraday_lgbm', model_type: 'gradient_boosting', signals: 20, ok_signals: 14, total_token_cost: 0 },
  { name: 'random_walk', model_type: 'baseline', signals: 10, ok_signals: 4, total_token_cost: 0 },
]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Leaderboard Component & Benchmark Ranking', () => {
  it('shows empty state when no providers', async () => {
    mockedFetch.mockResolvedValue({ symbol: null, timeframe: null, providers: [] })
    render(<Leaderboard />)
    expect(await screen.findByTestId('leaderboard-empty')).toHaveTextContent(/no models evaluated yet/i)
  })

  it('renders provider rows sorted by accuracy with ranks and medals', async () => {
    mockedFetch.mockResolvedValue({
      symbol: null,
      timeframe: null,
      providers: sampleProviders,
    })
    render(<Leaderboard />)

    const rows = await screen.findAllByTestId('leaderboard-row')
    expect(rows).toHaveLength(3)

    // Check rank 1 (deepseek-v4: 90% win rate)
    expect(screen.getByText('🥇 1')).toBeInTheDocument()
    expect(screen.getByText('deepseek-v4')).toBeInTheDocument()
    expect(screen.getByText('90.0%')).toBeInTheDocument()
    expect(screen.getByText('1,500')).toBeInTheDocument() // Token cost

    // Check rank 2 (intraday_lgbm: 70% win rate)
    expect(screen.getByText('🥈 2')).toBeInTheDocument()
    expect(screen.getByText('intraday_lgbm')).toBeInTheDocument()
    expect(screen.getByText('70.0%')).toBeInTheDocument()
    expect(screen.getAllByText('0 (local)').length).toBeGreaterThan(0)

    // Check rank 3 (random_walk: 40% win rate)
    expect(screen.getByText('🥉 3')).toBeInTheDocument()
    expect(screen.getByText('random_walk')).toBeInTheDocument()
    expect(screen.getByText('40.0%')).toBeInTheDocument()
  })

  it('filters leaderboard by symbol and timeframe dropdowns', async () => {
    mockedFetch.mockResolvedValue({
      symbol: null,
      timeframe: null,
      providers: sampleProviders,
    })
    render(<Leaderboard />)

    const symbolFilter = (await screen.findByLabelText(/Leaderboard symbol/i)) as HTMLSelectElement
    await userEvent.selectOptions(symbolFilter, 'BTCUSDT')
    expect(mockedFetch).toHaveBeenCalledWith('BTCUSDT', undefined)

    const tfFilter = screen.getByLabelText(/Leaderboard timeframe/i) as HTMLSelectElement
    await userEvent.selectOptions(tfFilter, '1h')
    expect(mockedFetch).toHaveBeenCalledWith('BTCUSDT', '1h')
  })

  it('shows error banner when API fails', async () => {
    mockedFetch.mockRejectedValue(new Error('leaderboard 500'))
    render(<Leaderboard />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/failed: leaderboard 500/i)
  })
})

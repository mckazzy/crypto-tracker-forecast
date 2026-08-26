import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Leaderboard from '../components/Leaderboard'
import { fetchLeaderboard } from '../lib/leaderboard'

vi.mock('../lib/leaderboard', () => ({
  fetchLeaderboard: vi.fn(),
}))

const mockedFetch = vi.mocked(fetchLeaderboard)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Leaderboard', () => {
  it('shows empty state when no providers', async () => {
    mockedFetch.mockResolvedValue({ symbol: null, timeframe: null, providers: [] })
    render(<Leaderboard />)
    expect(await screen.findByTestId('leaderboard-empty')).toHaveTextContent(/no models/i)
  })

  it('renders provider rows with token cost', async () => {
    mockedFetch.mockResolvedValue({
      symbol: null,
      timeframe: null,
      providers: [
        { name: 'random_walk', signals: 10, ok_signals: 5, total_token_cost: 0 },
        { name: 'ai', signals: 4, ok_signals: 3, total_token_cost: 800 },
      ],
    })
    render(<Leaderboard />)
    const rows = await screen.findAllByTestId('leaderboard-row')
    expect(rows).toHaveLength(2)
    expect(screen.getByText('ai')).toBeTruthy()
    expect(screen.getByText('800')).toBeTruthy()
    expect(screen.getByText('0 (local)')).toBeTruthy()
  })

  it('shows error banner when API fails', async () => {
    mockedFetch.mockRejectedValue(new Error('leaderboard 500'))
    render(<Leaderboard />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/failed/i)
  })
})

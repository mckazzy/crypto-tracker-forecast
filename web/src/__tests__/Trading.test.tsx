import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Trading from '../components/Trading'
import {
  closePosition,
  fetchAlerts,
  fetchPnl,
  fetchPositions,
  submitOutcome,
  type Position,
} from '../lib/trading'

vi.mock('../lib/trading', () => ({
  fetchPositions: vi.fn(),
  fetchPnl: vi.fn(),
  fetchAlerts: vi.fn(),
  closePosition: vi.fn(),
  submitOutcome: vi.fn(),
}))

const mocked = {
  fetchPositions: vi.mocked(fetchPositions),
  fetchPnl: vi.mocked(fetchPnl),
  fetchAlerts: vi.mocked(fetchAlerts),
  closePosition: vi.mocked(closePosition),
  submitOutcome: vi.mocked(submitOutcome),
}

function makePosition(overrides: Partial<Position> = {}): Position {
  return {
    id: 1,
    symbol: 'BTCUSDT',
    timeframe: '1h',
    direction: 'LONG',
    entry: 67200,
    tp: 68500,
    sl: 66100,
    opened_at: '2026-01-01T00:00:00Z',
    closed_at: null,
    exit_price: null,
    pnl: null,
    status: 'open',
    model: 'test',
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocked.fetchPositions.mockResolvedValue([])
  mocked.fetchPnl.mockResolvedValue({ total_closed: 0, total_open: 0, total_pnl: 0, win_rate: 0, avg_pnl: 0 })
  mocked.fetchAlerts.mockResolvedValue([])
  mocked.closePosition.mockResolvedValue(undefined)
  mocked.submitOutcome.mockResolvedValue({ id: 1, trusted: true })
})

describe('Trading', () => {
  it('shows empty state', async () => {
    render(<Trading />)
    expect(await screen.findByTestId('positions-empty')).toHaveTextContent(/no positions/i)
  })

  it('renders positions with P&L summary', async () => {
    mocked.fetchPositions.mockResolvedValue([
      makePosition(),
      makePosition({ id: 2, direction: 'SHORT', status: 'closed', pnl: 0.05 }),
    ])
    mocked.fetchPnl.mockResolvedValue({ total_closed: 1, total_open: 1, total_pnl: 0.05, win_rate: 1, avg_pnl: 0.05 })
    render(<Trading />)
    const rows = await screen.findAllByTestId('position-row')
    expect(rows).toHaveLength(2)
    expect(screen.getByText(/win rate/i)).toBeTruthy()
  })

  it('submits win outcome on button click', async () => {
    mocked.fetchPositions.mockResolvedValue([makePosition()])
    render(<Trading />)
    const winBtn = await screen.findByRole('button', { name: /win/i })
    await userEvent.click(winBtn)
    expect(mocked.submitOutcome).toHaveBeenCalledWith(
      expect.objectContaining({ symbol: 'BTCUSDT', outcome: 'win' }),
    )
  })

  it('closes position on button click', async () => {
    mocked.fetchPositions.mockResolvedValue([makePosition()])
    render(<Trading />)
    const closeBtn = await screen.findByRole('button', { name: /close/i })
    await userEvent.click(closeBtn)
    expect(mocked.closePosition).toHaveBeenCalledWith(1, 67200)
  })

  it('shows error banner when API fails', async () => {
    mocked.fetchPositions.mockRejectedValue(new Error('positions 500'))
    render(<Trading />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/failed/i)
  })
})

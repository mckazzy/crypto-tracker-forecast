import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { fetchKlines, fetchSymbols, type KlinesResponse } from '../lib/api'

vi.mock('../lib/api', () => ({
  fetchKlines: vi.fn(),
  fetchSymbols: vi.fn(),
}))

const mockedKlines = vi.mocked(fetchKlines)
const mockedSymbols = vi.mocked(fetchSymbols)

function makeResponse(overrides: Partial<KlinesResponse> = {}): KlinesResponse {
  return {
    symbol: 'BTCUSDT',
    timeframe: '1h',
    count: 2,
    data: [
      {
        open_time: 1_760_000_000_000,
        close_time: 1_760_000_359_999,
        open: 40000,
        high: 40200,
        low: 39900,
        close: 40100,
        volume: 123.4,
      },
      {
        open_time: 1_760_003_600_000,
        close_time: 1_760_003_959_999,
        open: 40100,
        high: 40300,
        low: 40050,
        close: 40250,
        volume: 150.0,
      },
    ],
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedSymbols.mockResolvedValue([
    { symbol: 'BTCUSDT', timeframes: [{ timeframe: '1h', count: 500 }] },
  ])
})

describe('App', () => {
  it('renders symbol selector with configured symbols', async () => {
    mockedKlines.mockResolvedValue(makeResponse())
    render(<App />)
    const select = await screen.findByLabelText(/symbol/i) as HTMLSelectElement
    expect(select.value).toBe('BTCUSDT')
  })

  it('shows last close price after loading klines', async () => {
    mockedKlines.mockResolvedValue(makeResponse())
    render(<App />)
    const last = await screen.findByTestId('last-price')
    expect(last).toHaveTextContent('40,250')
  })

  it('shows error banner when API fails', async () => {
    mockedKlines.mockRejectedValue(new Error('klines 500'))
    render(<App />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/failed/i)
  })

  it('renders candle rows in table', async () => {
    mockedKlines.mockResolvedValue(makeResponse())
    render(<App />)
    const rows = await screen.findAllByTestId('candle-row')
    expect(rows).toHaveLength(2)
  })
})

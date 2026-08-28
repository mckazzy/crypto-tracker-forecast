import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { fetchKlines, fetchSymbols, type KlinesResponse } from '../lib/api'
import { fetchAiModels } from '../lib/ai'
import { fetchForecasts, fetchAnalytics } from '../lib/forecast'
import { fetchLeaderboard } from '../lib/leaderboard'
import { fetchPositions, fetchPnl, fetchAlerts } from '../lib/trading'

vi.mock('../lib/api', () => ({
  fetchKlines: vi.fn(),
  fetchSymbols: vi.fn(),
}))

vi.mock('../lib/ai', () => ({
  fetchAiModels: vi.fn(),
}))

vi.mock('../lib/forecast', () => ({
  fetchForecasts: vi.fn(),
  fetchAnalytics: vi.fn(),
  fetchCompare: vi.fn(),
  runForecast: vi.fn(),
  scoreForecast: vi.fn(),
  scoreAllExpired: vi.fn(),
  retrainModel: vi.fn(),
  exportForecastsCsv: vi.fn(),
}))

vi.mock('../lib/leaderboard', () => ({
  fetchLeaderboard: vi.fn(),
}))

vi.mock('../lib/trading', () => ({
  fetchPositions: vi.fn(),
  fetchPnl: vi.fn(),
  fetchAlerts: vi.fn(),
  closePosition: vi.fn(),
  submitOutcome: vi.fn(),
}))

vi.mock('../lib/futures', () => ({
  getToken: vi.fn(() => 'test-token'),
  fetchAccount: vi.fn(async () => ({ balance: 10000, margin_used: 0, unrealized_pnl: 0 })),
  placeOrder: vi.fn(),
  resetAccount: vi.fn(),
  closePosition: vi.fn(),
  cancelOrder: vi.fn(),
  fetchPositions: vi.fn(async () => []),
  fetchOrders: vi.fn(async () => []),
  fetchTrades: vi.fn(async () => []),
  fetchMark: vi.fn(async () => 50000),
  connectTradeWs: vi.fn(() => () => {}),
}))

const mockedKlines = vi.mocked(fetchKlines)
const mockedSymbols = vi.mocked(fetchSymbols)
const mockedAiModels = vi.mocked(fetchAiModels)
const mockedForecasts = vi.mocked(fetchForecasts)
const mockedAnalytics = vi.mocked(fetchAnalytics)
const mockedLeaderboard = vi.mocked(fetchLeaderboard)
const mockedPositions = vi.mocked(fetchPositions)
const mockedPnl = vi.mocked(fetchPnl)
const mockedAlerts = vi.mocked(fetchAlerts)

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
    { symbol: 'ETHUSDT', timeframes: [{ timeframe: '1h', count: 500 }] },
  ])
  mockedKlines.mockResolvedValue(makeResponse())
  mockedAiModels.mockResolvedValue({
    enabled: true,
    provider: 'openrouter',
    base_url: 'https://openrouter.ai/api/v1',
    default_model: 'deepseek/deepseek-v4-flash-0731',
    models: ['deepseek/deepseek-v4-flash-0731'],
  })
  mockedForecasts.mockResolvedValue({ forecasts: [] })
  mockedAnalytics.mockResolvedValue({
    total: 0,
    scored_total: 0,
    avg_accuracy: 0,
    direction_split: { LONG: 0, SHORT: 0, FLAT: 0 },
    by_source: {},
    by_direction: {},
  })
  mockedLeaderboard.mockResolvedValue({ symbol: null, timeframe: null, providers: [] })
  mockedPositions.mockResolvedValue([])
  mockedPnl.mockResolvedValue({ total_closed: 0, total_open: 0, total_pnl: 0, win_rate: 0, avg_pnl: 0 })
  mockedAlerts.mockResolvedValue([])
})

describe('App Component and UI Navigation', () => {
  it('renders app branding and live status badge', async () => {
    render(<App />)
    expect(screen.getByText('Crypto Tracker')).toBeInTheDocument()
    expect(screen.getByText('LIVE')).toBeInTheDocument()
    expect(screen.getByText(/AI Price Forecast & Real-Time Trading Terminal/i)).toBeInTheDocument()
  })

  it('renders symbol selector and timeframe pills on Dashboard', async () => {
    render(<App />)
    const select = (await screen.findByLabelText(/symbol/i)) as HTMLSelectElement
    expect(select.value).toBe('BTCUSDT')

    // Check timeframe buttons
    expect(screen.getByRole('button', { name: '5m' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '15m' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '1h' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '4h' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '1d' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '1w' })).toBeInTheDocument()
  })

  it('shows last close price, 24h stats, and AI forecast widget', async () => {
    render(<App />)
    const last = await screen.findByTestId('last-price')
    expect(last).toHaveTextContent('40,250')

    // Check High/Low/Volume stats
    expect(screen.getAllByText('High').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Low').length).toBeGreaterThan(0)
    expect(screen.getAllByText('40,300.00').length).toBeGreaterThan(0) // High
    expect(screen.getAllByText('39,900.00').length).toBeGreaterThan(0) // Low
    expect(screen.getByText('273.40')).toBeInTheDocument() // Total volume (123.4 + 150)
  })

  it('renders candle rows in Historical OHLCV table', async () => {
    render(<App />)
    const rows = await screen.findAllByTestId('candle-row')
    expect(rows).toHaveLength(2)
    expect(screen.getByText('Historical OHLCV Data')).toBeInTheDocument()
  })

  it('handles changing symbol in dropdown', async () => {
    render(<App />)
    const select = (await screen.findByLabelText(/symbol/i)) as HTMLSelectElement
    await userEvent.selectOptions(select, 'ETHUSDT')
    expect(mockedKlines).toHaveBeenCalledWith('ETHUSDT', '1h')
  })

  it('handles changing timeframe via timeframe pills', async () => {
    render(<App />)
    const tf4h = screen.getByRole('button', { name: '4h' })
    await userEvent.click(tf4h)
    expect(mockedKlines).toHaveBeenCalledWith('BTCUSDT', '4h')
  })

  it('refreshes klines when clicking refresh button', async () => {
    render(<App />)
    const refreshBtn = screen.getByTitle('Refresh data')
    await userEvent.click(refreshBtn)
    expect(mockedKlines).toHaveBeenCalledTimes(2)
  })

  it('navigates between all tabs seamlessly (Dashboard -> Leaderboard -> Forecast -> Trading)', async () => {
    render(<App />)

    // 1. Leaderboard Tab
    const leaderboardTab = screen.getByRole('tab', { name: /Leaderboard/i })
    await userEvent.click(leaderboardTab)
    expect(await screen.findByText('Model Leaderboard')).toBeInTheDocument()
    expect(screen.getByTestId('model-picker')).toBeInTheDocument()

    // 2. Forecast Tab
    const forecastTab = screen.getByRole('tab', { name: /Forecast/i })
    await userEvent.click(forecastTab)
    expect(await screen.findByRole('button', { name: /Forecast AI/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Forecast Local/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Run AI vs Offline/i })).toBeInTheDocument()

    // 3. Trading Tab — futures terminal mới (không còn Alerts Feed)
    const tradingTab = screen.getByRole('tab', { name: /Trading/i })
    await userEvent.click(tradingTab)
    expect(await screen.findByTestId('mark-price')).toBeInTheDocument()
    expect(screen.getByTestId('order-form')).toBeInTheDocument()
    expect(screen.getByText('Futures')).toBeInTheDocument()

    // 4. Alerts Tab riêng — SP4 alerts giữ nguyên
    const alertsTab = screen.getByRole('tab', { name: /Alerts/i })
    await userEvent.click(alertsTab)
    expect(await screen.findByText('Alerts Feed')).toBeInTheDocument()

    // 5. Return to Dashboard Tab
    const dashboardTab = screen.getByRole('tab', { name: /Dashboard/i })
    await userEvent.click(dashboardTab)
    expect(await screen.findByTestId('last-price')).toBeInTheDocument()
  })

  it('shows error alert banner when fetch fails', async () => {
    mockedKlines.mockRejectedValue(new Error('Network error 500'))
    render(<App />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/Load failed: Network error 500/i)
  })
})

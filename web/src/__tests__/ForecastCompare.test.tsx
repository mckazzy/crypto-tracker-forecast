import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ForecastCompare from '../components/ForecastCompare'
import {
  deleteForecast,
  exportForecastsCsv,
  fetchAnalytics,
  fetchCompare,
  fetchForecasts,
  retrainModel,
  runForecast,
  scoreAllExpired,
  scoreForecast,
  submitUserForecast,
  type AnalyticsResponse,
  type ForecastRecord,
  type SignalPayload,
} from '../lib/forecast'

vi.mock('../lib/forecast', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/forecast')>()
  return {
    ...actual,
    fetchCompare: vi.fn(),
    fetchForecasts: vi.fn(),
    fetchAnalytics: vi.fn(),
    runForecast: vi.fn(),
    scoreForecast: vi.fn(),
    scoreAllExpired: vi.fn(),
    retrainModel: vi.fn(),
    exportForecastsCsv: vi.fn(),
    submitUserForecast: vi.fn(),
    deleteForecast: vi.fn(),
  }
})

const mockedCompare = vi.mocked(fetchCompare)
const mockedForecasts = vi.mocked(fetchForecasts)
const mockedAnalytics = vi.mocked(fetchAnalytics)
const mockedRunForecast = vi.mocked(runForecast)
const mockedScoreForecast = vi.mocked(scoreForecast)
const mockedScoreAllExpired = vi.mocked(scoreAllExpired)
const mockedRetrainModel = vi.mocked(retrainModel)
const mockedExportCsv = vi.mocked(exportForecastsCsv)
const mockedSubmitUserForecast = vi.mocked(submitUserForecast)
const mockedDeleteForecast = vi.mocked(deleteForecast)

const mockSignal: SignalPayload = {
  symbol: 'BTCUSDT',
  timeframe: '4h',
  direction: 'LONG',
  probability: 0.88,
  entry: 95500,
  take_profit: [99000],
  stop_loss: 93500,
  rr_ratio: 1.75,
  model: 'deepseek',
  valid_until: '2026-08-27T14:00:00Z',
  status: 'active',
  created_at: '2026-08-27T10:00:00Z',
  token_cost: 150,
}

const mockAnalyticsData: AnalyticsResponse = {
  total: 6,
  scored_total: 4,
  avg_accuracy: 75,
  direction_split: { LONG: 4, SHORT: 2, FLAT: 0 },
  by_source: {
    AI: { total: 3, scored: 2, score_sum: 160, wins: 2, losses: 0, accuracy: 80 },
    Local: { total: 2, scored: 1, score_sum: 60, wins: 1, losses: 0, accuracy: 60 },
    User: { total: 1, scored: 1, score_sum: 90, wins: 1, losses: 0, accuracy: 90 },
  },
  by_direction: {
    LONG: { total: 4, scored: 3, score_sum: 240, accuracy: 80 },
    SHORT: { total: 2, scored: 1, score_sum: 70, accuracy: 70 },
  },
}

const mockForecastRecords: ForecastRecord[] = [
  {
    id: 101,
    symbol: 'BTCUSDT',
    timeframe: '4h',
    provider: 'ai',
    source: 'AI',
    direction: 'LONG',
    probability: 0.85,
    entry: 95000,
    take_profit: [98000, 100000],
    stop_loss: 93000,
    created_at: '2026-08-27T06:00:00Z',
    valid_until: '2026-08-27T10:00:00Z',
    expired: true,
    scored: false,
    outcome: null,
  },
  {
    id: 102,
    symbol: 'BTCUSDT',
    timeframe: '4h',
    provider: 'intraday_lgbm@BTCUSDT@4h',
    source: 'Local',
    direction: 'SHORT',
    probability: 0.62,
    entry: 95200,
    take_profit: [93500],
    stop_loss: 96500,
    exit_price: 94200,
    created_at: '2026-08-27T06:00:00Z',
    valid_until: '2026-08-27T10:00:00Z',
    expired: true,
    scored: true,
    outcome: {
      score: 85,
      outcome: 'win',
      user_override: false,
      resolved_at: '2026-08-27T10:00:00Z',
      exit_price: 94200,
    },
  },
  {
    id: 103,
    symbol: 'BTCUSDT',
    timeframe: '4h',
    provider: 'user',
    source: 'User',
    direction: 'LONG',
    probability: 0.8,
    entry: 95000,
    take_profit: [98500],
    stop_loss: 93500,
    exit_price: 98200,
    created_at: '2026-08-27T06:00:00Z',
    valid_until: '2026-08-27T10:00:00Z',
    expired: true,
    scored: true,
    outcome: {
      score: 90,
      outcome: 'win',
      user_override: false,
      resolved_at: '2026-08-27T10:00:00Z',
      exit_price: 98200,
    },
  },
  {
    id: 104,
    symbol: 'BTCUSDT',
    timeframe: '15m',
    provider: 'intraday_lgbm@BTCUSDT@15m',
    source: 'Local',
    direction: 'LONG',
    probability: 0.75,
    entry: 80000,
    take_profit: [80500],
    stop_loss: 79500,
    exit_price: 80800,
    created_at: '2026-08-27T06:00:00Z',
    valid_until: '2026-08-27T06:15:00Z',
    expired: true,
    scored: true,
    outcome: {
      score: 160,
      outcome: 'win',
      user_override: false,
      resolved_at: '2026-08-27T06:15:00Z',
      exit_price: 80800,
    },
  },
  {
    id: 105,
    symbol: 'BTCUSDT',
    timeframe: '15m',
    provider: 'intraday_lgbm@BTCUSDT@15m',
    source: 'Local',
    direction: 'SHORT',
    probability: 0.6,
    entry: 80000,
    take_profit: [79500],
    stop_loss: 80500,
    exit_price: 80300,
    created_at: '2026-08-27T06:00:00Z',
    valid_until: '2026-08-27T06:15:00Z',
    expired: true,
    scored: true,
    outcome: {
      score: -60,
      outcome: 'lose',
      user_override: false,
      resolved_at: '2026-08-27T06:15:00Z',
      exit_price: 80300,
    },
  },
]

beforeEach(() => {
  vi.clearAllMocks()
  mockedForecasts.mockResolvedValue({ forecasts: mockForecastRecords })
  mockedAnalytics.mockResolvedValue(mockAnalyticsData)
  mockedRunForecast.mockResolvedValue({
    id: 103,
    symbol: 'BTCUSDT',
    timeframe: '4h',
    provider: 'ai',
    signal: mockSignal,
    valid_until: '2026-08-27T14:00:00Z',
    created_at: '2026-08-27T10:00:00Z',
  })
  mockedSubmitUserForecast.mockResolvedValue({
    id: 106,
    symbol: 'BTCUSDT',
    timeframe: '4h',
    provider: 'user',
    signal: {
      ...mockSignal,
      model: 'user',
      entry: 95500,
      take_profit: [99000],
      stop_loss: 93500,
      rr_ratio: 1.75,
    },
    valid_until: '2026-08-27T14:00:00Z',
    created_at: '2026-08-27T10:00:00Z',
  })
  mockedCompare.mockResolvedValue({
    symbol: 'BTCUSDT',
    timeframe: '4h',
    results: {
      ai: mockSignal,
      'intraday_lgbm@BTCUSDT@4h': {
        ...mockSignal,
        direction: 'SHORT',
        probability: 0.55,
        take_profit: [94000],
        stop_loss: 96500,
        rr_ratio: 1.5,
        model: 'intraday_lgbm',
      },
    },
  })
  mockedRetrainModel.mockResolvedValue({
    retrained: true,
    model: 'intraday_lgbm',
    message: 'Retrain completed successfully for BTCUSDT 4h',
  })
  mockedScoreForecast.mockResolvedValue({
    forecast_id: 101,
    scored: true,
    score: 90,
    outcome: 'win',
    exit_price: 98500,
  })
  mockedScoreAllExpired.mockResolvedValue({
    scored: 1,
    skipped: 0,
    details: [],
  })
})

describe('ForecastCompare UI and 3-Cluster Command Deck', () => {
  it('renders 3 main pods (AI, Local, User) and combo buttons', async () => {
    render(<ForecastCompare />)

    // 3 Main Pods
    expect(screen.getByRole('button', { name: /Forecast AI/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Forecast Local/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Lưu Dự Đoán User/i })).toBeInTheDocument()

    // Combo Launcher Buttons
    expect(screen.getByRole('button', { name: /AI \+ User/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /AI \+ Local/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Local \+ User/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Cả 3 Cùng Lúc/i })).toBeInTheDocument()

    // Header actions
    expect(screen.getByRole('button', { name: /Chấm tất cả/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Export CSV/i })).toBeInTheDocument()

    // Symbol and Timeframe
    const symbolSelect = screen.getByLabelText(/Forecast symbol/i) as HTMLSelectElement
    expect(symbolSelect.value).toBe('BTCUSDT')
    expect(screen.getByRole('button', { name: '4h' })).toBeInTheDocument()
  })

  it('renders analytics cards with accuracy and 3-source breakdowns (AI, Local, User)', async () => {
    render(<ForecastCompare />)
    expect(await screen.findByText('Tổng dự báo')).toBeInTheDocument()
    expect(screen.getByText('6')).toBeInTheDocument()
    expect(screen.getByText('+75%')).toBeInTheDocument()
    expect(screen.getByText('Nguồn AI')).toBeInTheDocument()
    expect(screen.getByText('+80%')).toBeInTheDocument()
    expect(screen.getByText('Nguồn Local')).toBeInTheDocument()
    expect(screen.getByText('+60%')).toBeInTheDocument()
    expect(screen.getByText('Nguồn User')).toBeInTheDocument()
    expect(screen.getAllByText('+90%').length).toBeGreaterThan(0)
  })

  it('renders forecast list table with 3 source badges (AI, Local, User)', async () => {
    render(<ForecastCompare />)
    expect(await screen.findByText('#101')).toBeInTheDocument()
    expect(screen.getByText('#102')).toBeInTheDocument()
    expect(screen.getByText('#103')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'TP' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Giá chốt' })).toBeInTheDocument()
    expect(screen.getByText('98,000.00 / 100,000.00')).toBeInTheDocument()
    expect(screen.getByText('QUÁ HẠN')).toBeInTheDocument()
    expect(screen.getByText('Đối chiếu & chấm')).toBeInTheDocument()
  })

  it('runs AI forecast when clicking "Forecast AI"', async () => {
    render(<ForecastCompare />)
    const aiBtn = screen.getByRole('button', { name: /Forecast AI/i })
    await userEvent.click(aiBtn)

    expect(mockedRunForecast).toHaveBeenCalledWith('ai', 'BTCUSDT', '4h')
    expect(await screen.findByText(/Dự báo #103 \(AI\) đã chạy/i)).toBeInTheDocument()
  })

  it('runs Local forecast when clicking "Forecast Local"', async () => {
    render(<ForecastCompare />)
    const localBtn = screen.getByRole('button', { name: /Forecast Local/i })
    await userEvent.click(localBtn)

    expect(mockedRunForecast).toHaveBeenCalledWith('local', 'BTCUSDT', '4h')
    expect(await screen.findByText(/Dự báo #103 \(Local\) đã chạy/i)).toBeInTheDocument()
  })

  it('allows user to input entry, TP, SL, toggle direction and submit User Forecast', async () => {
    render(<ForecastCompare />)

    const shortBtn = screen.getByRole('button', { name: /SHORT ↘/i })
    await userEvent.click(shortBtn)

    const entryInput = screen.getByPlaceholderText('Giá hiện tại')
    const tpInput = screen.getByPlaceholderText('Take Profit')
    const slInput = screen.getByPlaceholderText('Stop Loss')

    await userEvent.type(entryInput, '95000')
    await userEvent.type(tpInput, '92000')
    await userEvent.type(slInput, '96500')

    // R:R should be calculated: (95000 - 92000) / (96500 - 95000) = 3000 / 1500 = 2.00
    expect(screen.getByText('1 : 2.00')).toBeInTheDocument()

    const submitUserBtn = screen.getByRole('button', { name: /Lưu Dự Đoán User/i })
    await userEvent.click(submitUserBtn)

    expect(mockedSubmitUserForecast).toHaveBeenCalledWith({
      symbol: 'BTCUSDT',
      timeframe: '4h',
      direction: 'SHORT',
      entry: 95000,
      take_profit: [92000],
      stop_loss: 96500,
      probability: 0.8,
    })
    expect(await screen.findByText(/Dự báo #106 \(User\) đã lưu/i)).toBeInTheDocument()
  })

  it('applies quick percentage chips to auto-calculate TP and SL from Entry', async () => {
    render(<ForecastCompare />)

    const entryInput = screen.getByPlaceholderText('Giá hiện tại')
    await userEvent.type(entryInput, '100000')

    // Click +3% chip for TP
    const tpChip3 = screen.getByRole('button', { name: /\+3%/i })
    await userEvent.click(tpChip3)

    // Click -2% chip for SL
    const slChip2 = screen.getByRole('button', { name: /-2%/i })
    await userEvent.click(slChip2)

    // TP should be 103000.00 and SL should be 98000.00
    const tpInput = screen.getByPlaceholderText('Take Profit') as HTMLInputElement
    const slInput = screen.getByPlaceholderText('Stop Loss') as HTMLInputElement
    expect(tpInput.value).toBe('103000.00')
    expect(slInput.value).toBe('98000.00')

    // R:R should be (103000 - 100000) / (100000 - 98000) = 3000 / 2000 = 1.50
    expect(screen.getByText('1 : 1.50')).toBeInTheDocument()
  })

  it('runs AI + Local combination when clicking combo button', async () => {
    render(<ForecastCompare />)
    const comboBtn = screen.getByRole('button', { name: /AI \+ Local/i })
    await userEvent.click(comboBtn)

    expect(mockedRunForecast).toHaveBeenCalledWith('ai', 'BTCUSDT', '4h')
    expect(mockedRunForecast).toHaveBeenCalledWith('local', 'BTCUSDT', '4h')
    expect(await screen.findByText(/Đã đối chiếu song song AI/i)).toBeInTheDocument()
  })

  it('runs AI + User combination concurrently', async () => {
    render(<ForecastCompare />)
    const comboBtn = screen.getByRole('button', { name: /AI \+ User/i })
    await userEvent.click(comboBtn)

    expect(mockedRunForecast).toHaveBeenCalledWith('ai', 'BTCUSDT', '4h')
    expect(mockedSubmitUserForecast).toHaveBeenCalled()
    expect(await screen.findByText(/Đã khởi tạo dự báo User/i)).toBeInTheDocument()
  })

  it('runs Local + User combination concurrently', async () => {
    render(<ForecastCompare />)
    const comboBtn = screen.getByRole('button', { name: /Local \+ User/i })
    await userEvent.click(comboBtn)

    expect(mockedRunForecast).toHaveBeenCalledWith('local', 'BTCUSDT', '4h')
    expect(mockedSubmitUserForecast).toHaveBeenCalled()
    expect(await screen.findByText(/Đã khởi tạo dự báo User/i)).toBeInTheDocument()
  })

  it('runs ALL 3 (AI + Local + User) simultaneously when clicking "Cả 3 Cùng Lúc"', async () => {
    render(<ForecastCompare />)
    const all3Btn = screen.getByRole('button', { name: /Cả 3 Cùng Lúc/i })
    await userEvent.click(all3Btn)

    expect(mockedRunForecast).toHaveBeenCalledWith('ai', 'BTCUSDT', '4h')
    expect(mockedRunForecast).toHaveBeenCalledWith('local', 'BTCUSDT', '4h')
    expect(mockedSubmitUserForecast).toHaveBeenCalled()
    expect(await screen.findByText(/ĐẠI CHIẾN TAM MÃ: Đã khởi tạo User/i)).toBeInTheDocument()
  })

  it('retrains offline model when clicking retrain icon button', async () => {
    render(<ForecastCompare />)
    const retrainBtn = screen.getByTitle(/Retrain offline model/i)
    await userEvent.click(retrainBtn)

    expect(mockedRetrainModel).toHaveBeenCalledWith('BTCUSDT', '4h')
    expect(await screen.findByText(/Retrain completed successfully for BTCUSDT 4h/i)).toBeInTheDocument()
  })

  it('scores all expired forecasts when clicking "Chấm tất cả"', async () => {
    render(<ForecastCompare />)
    const btn = screen.getByRole('button', { name: /Chấm tất cả/i })
    await userEvent.click(btn)

    expect(mockedScoreAllExpired).toHaveBeenCalled()
    expect(await screen.findByText(/Đã chấm 1 dự báo quá hạn/i)).toBeInTheDocument()
  })

  it('scores individual forecast when clicking "Đối chiếu & chấm"', async () => {
    render(<ForecastCompare />)
    const scoreBtn = await screen.findByRole('button', { name: /Đối chiếu & chấm/i })
    await userEvent.click(scoreBtn)

    expect(mockedScoreForecast).toHaveBeenCalledWith(101)
    expect(await screen.findByText(/Dự báo #101: \+90% so với TP \(win\)/i)).toBeInTheDocument()
  })

  it('triggers CSV export with selected symbol and timeframe', async () => {
    render(<ForecastCompare />)
    const exportBtn = screen.getByRole('button', { name: /Export CSV/i })
    await userEvent.click(exportBtn)

    expect(mockedExportCsv).toHaveBeenCalledWith('BTCUSDT', '4h')
  })

  it('prompts confirmation when AI forecast has confidence < 60% and deletes when user clicks discard', async () => {
    mockedRunForecast.mockResolvedValueOnce({
      id: 201,
      symbol: 'BTCUSDT',
      timeframe: '4h',
      provider: 'ai',
      signal: {
        ...mockSignal,
        probability: 0.54, // < 60%
        entry: 95000,
        take_profit: [98000],
      },
      valid_until: '2026-08-27T14:00:00Z',
      created_at: '2026-08-27T10:00:00Z',
    })
    mockedDeleteForecast.mockResolvedValueOnce({ deleted: true, id: 201 })

    render(<ForecastCompare />)
    const aiBtn = screen.getByRole('button', { name: /Forecast AI/i })
    await userEvent.click(aiBtn)

    // Modal should appear
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toBeInTheDocument()
    expect(screen.getByText(/Cảnh Báo Chất Lượng Dự Báo/i)).toBeInTheDocument()

    // Click Discard
    const discardBtn = screen.getByRole('button', { name: /Bỏ qua & Không lưu/i })
    await userEvent.click(discardBtn)

    expect(mockedDeleteForecast).toHaveBeenCalledWith(201)
    expect(await screen.findByText(/Đã hủy & xóa dự báo #201/i)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('prompts confirmation when forecast price delta is < 1% and keeps it when user clicks proceed', async () => {
    mockedRunForecast.mockResolvedValueOnce({
      id: 202,
      symbol: 'BTCUSDT',
      timeframe: '4h',
      provider: 'local',
      signal: {
        ...mockSignal,
        probability: 0.75, // > 60%
        entry: 100000,
        take_profit: [100500], // (100500 - 100000) / 100000 = 0.5% < 1%
      },
      valid_until: '2026-08-27T14:00:00Z',
      created_at: '2026-08-27T10:00:00Z',
    })

    render(<ForecastCompare />)
    const localBtn = screen.getByRole('button', { name: /Forecast Local/i })
    await userEvent.click(localBtn)

    // Modal should appear
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toBeInTheDocument()

    // Click Proceed
    const proceedBtn = screen.getByRole('button', { name: /Vẫn tiếp tục lưu & hiển thị/i })
    await userEvent.click(proceedBtn)

    expect(mockedDeleteForecast).not.toHaveBeenCalled()
    expect(await screen.findByText(/Đã xác nhận lưu & hiển thị dự báo #202/i)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})


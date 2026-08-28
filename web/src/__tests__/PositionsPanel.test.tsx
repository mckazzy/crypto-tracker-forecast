import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import PositionsPanel from '../components/futures/PositionsPanel'

const positions = [
  {
    id: 1,
    user_id: 1,
    symbol: 'BTCUSDT',
    side: 'LONG',
    entry: 50000,
    qty: 0.01,
    leverage: 10,
    margin: 50,
    liq_price: 45250,
    tp: null,
    sl: null,
    status: 'OPEN',
    pnl: null,
    exit_price: null,
    close_reason: null,
    created_at: null,
  },
]

const orders = [
  {
    id: 7,
    symbol: 'BTCUSDT',
    side: 'LONG',
    type: 'LIMIT',
    price: 48000,
    qty: 0.01,
    leverage: 10,
    tp: null,
    sl: null,
    status: 'OPEN',
    created_at: null,
  },
]

const trades = [
  {
    id: 2,
    user_id: 1,
    symbol: 'ETHUSDT',
    side: 'SHORT',
    entry: 3000,
    qty: 1,
    leverage: 10,
    margin: 300,
    liq_price: 3298.5,
    tp: null,
    sl: null,
    status: 'CLOSED',
    pnl: 100,
    exit_price: 2900,
    close_reason: 'TP',
    created_at: null,
  },
]

vi.mock('../lib/futures', () => ({
  fetchPositions: vi.fn(async () => positions),
  fetchOrders: vi.fn(async () => orders),
  fetchTrades: vi.fn(async () => trades),
  closePosition: vi.fn(async () => ({ pnl: 10 })),
  cancelOrder: vi.fn(async () => {}),
}))

function renderPanel() {
  return render(
    <PositionsPanel
      mark={51000}
      refreshKey={0}
      onChanged={() => {}}
      onError={() => {}}
      onUnauthorized={() => {}}
    />,
  )
}

describe('PositionsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders position with live pnl', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('position-row')).toBeInTheDocument())
    // pnl live = (51000 - 50000) * 0.01 = +10
    expect(screen.getByText('+10.00')).toBeInTheDocument()
  })

  it('shows pnl in green when positive', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('position-row')).toBeInTheDocument())
    expect(screen.getByText('+10.00').className).toContain('emerald')
  })

  it('switches to open orders tab', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('position-row')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('tab', { name: /open orders/i }))
    await waitFor(() => expect(screen.getByTestId('order-row')).toBeInTheDocument())
    expect(screen.getByText('LIMIT')).toBeInTheDocument()
  })

  it('switches to history tab', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('position-row')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('tab', { name: /history/i }))
    await waitFor(() => expect(screen.getByTestId('trade-row')).toBeInTheDocument())
    expect(screen.getByText('TP')).toBeInTheDocument()
  })

  it('calls onUnauthorized on 401', async () => {
    const { fetchPositions: mockFetch } = await import('../lib/futures')
    ;(mockFetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('HTTP 401'))
    const onUnauthorized = vi.fn()
    render(
      <PositionsPanel mark={51000} refreshKey={0} onChanged={() => {}} onError={() => {}} onUnauthorized={onUnauthorized} />,
    )
    await waitFor(() => expect(onUnauthorized).toHaveBeenCalled())
  })
})

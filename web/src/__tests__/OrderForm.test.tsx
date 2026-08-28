import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import OrderForm from '../components/futures/OrderForm'
import type { OrderPayload } from '../lib/futures'

function renderForm(onSubmit: (p: OrderPayload) => Promise<void> = vi.fn(async () => {})) {
  return render(<OrderForm symbol="BTCUSDT" mark={50000} onSubmit={onSubmit} />)
}

describe('OrderForm', () => {
  it('shows leverage slider with default 10x', () => {
    renderForm()
    expect(screen.getByTestId('leverage-value')).toHaveTextContent('10x')
  })

  it('submits market order with notional_usdt payload', async () => {
    const onSubmit = vi.fn(async () => {})
    renderForm(onSubmit)
    fireEvent.click(screen.getByTestId('side-long'))
    fireEvent.change(screen.getByTestId('notional-input'), { target: { value: '500' } })
    fireEvent.click(screen.getByTestId('order-submit'))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        symbol: 'BTCUSDT',
        side: 'LONG',
        type: 'MARKET',
        notional_usdt: 500,
        leverage: 10,
      }),
    )
  })

  it('switches to SHORT side', async () => {
    const onSubmit = vi.fn(async () => {})
    renderForm(onSubmit)
    fireEvent.click(screen.getByTestId('side-short'))
    fireEvent.change(screen.getByTestId('notional-input'), { target: { value: '100' } })
    fireEvent.click(screen.getByTestId('order-submit'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ side: 'SHORT' }))
  })

  it('limit order requires price and includes it in payload', async () => {
    const onSubmit = vi.fn(async () => {})
    renderForm(onSubmit)
    fireEvent.click(screen.getByTestId('type-limit'))
    fireEvent.change(screen.getByTestId('notional-input'), { target: { value: '200' } })
    fireEvent.change(screen.getByTestId('limit-price-input'), { target: { value: '49000' } })
    fireEvent.click(screen.getByTestId('order-submit'))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'LIMIT', price: 49000 }),
    )
  })

  it('shows liq price pre-check', () => {
    renderForm()
    // LONG 100 USDT @ 50000, lev 10 → liq = 50000 * (1 - 0.1 + 0.005) = 45250
    fireEvent.change(screen.getByTestId('notional-input'), { target: { value: '100' } })
    const liq = screen.getByTestId('liq-price')
    expect(liq.textContent).toContain('45,250')
  })

  it('shows error when limit price missing', () => {
    const onSubmit = vi.fn(async () => {})
    renderForm(onSubmit)
    fireEvent.click(screen.getByTestId('type-limit'))
    fireEvent.change(screen.getByTestId('notional-input'), { target: { value: '200' } })
    fireEvent.click(screen.getByTestId('order-submit'))
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })
})

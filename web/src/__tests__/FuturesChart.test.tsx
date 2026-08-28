import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import FuturesChart from '../components/futures/FuturesChart'
import type { KlineFrame } from '../lib/futures'

const klines: KlineFrame[] = [
  {
    type: 'kline',
    symbol: 'BTCUSDT',
    timeframe: '1m',
    open_time: 1_760_000_000_000,
    close_time: 1_760_000_059_999,
    open: 50000,
    high: 50500,
    low: 49800,
    close: 50200,
    volume: 120.5,
    is_closed: false,
  },
  {
    type: 'kline',
    symbol: 'BTCUSDT',
    timeframe: '1m',
    open_time: 1_760_000_060_000,
    close_time: 1_760_000_119_999,
    open: 50200,
    high: 51000,
    low: 50100,
    close: 50800,
    volume: 245.8,
    is_closed: false,
  },
]

describe('FuturesChart (test env: no canvas)', () => {
  it('shows waiting message with no candles', () => {
    render(<FuturesChart candles={[]} />)
    expect(screen.getByTestId('futures-chart')).toHaveTextContent(/waiting for live klines/i)
  })

  it('shows candle count when data present', () => {
    render(<FuturesChart candles={klines} />)
    expect(screen.getByTestId('futures-chart')).toHaveTextContent('2 candles')
  })
})

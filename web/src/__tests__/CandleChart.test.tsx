import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import CandleChart from '../components/CandleChart'
import type { Kline } from '../lib/api'

const sampleCandles: Kline[] = [
  {
    open_time: 1_760_000_000_000,
    close_time: 1_760_000_359_999,
    open: 50000,
    high: 50500,
    low: 49800,
    close: 50200,
    volume: 120.5,
  },
  {
    open_time: 1_760_003_600_000,
    close_time: 1_760_003_959_999,
    open: 50200,
    high: 51000,
    low: 50100,
    close: 50800,
    volume: 245.8,
  },
]

describe('CandleChart', () => {
  it('shows empty message when candles array is empty', () => {
    render(<CandleChart candles={[]} symbol="BTCUSDT" timeframe="1h" />)
    expect(screen.getByText(/no candle data available/i)).toBeInTheDocument()
  })

  it('renders chart header with symbol and timeframe badge', () => {
    render(<CandleChart candles={sampleCandles} symbol="ETHUSDT" timeframe="4h" />)
    expect(screen.getByText('ETHUSDT')).toBeInTheDocument()
    expect(screen.getByText('4h')).toBeInTheDocument()
  })

  it('renders live OHLCV metrics for latest candle', () => {
    render(<CandleChart candles={sampleCandles} symbol="BTCUSDT" timeframe="1h" />)
    expect(screen.getByText('50,200.00')).toBeInTheDocument() // Open of last candle
    expect(screen.getByText('51,000.00')).toBeInTheDocument() // High
    expect(screen.getByText('50,100.00')).toBeInTheDocument() // Low
    expect(screen.getByText('50,800.00')).toBeInTheDocument() // Close
    expect(screen.getByText('245.8')).toBeInTheDocument() // Volume
    expect(screen.getByText('+1.20%')).toBeInTheDocument() // Price change percentage
  })

  it('renders price chart element in test environment', () => {
    render(<CandleChart candles={sampleCandles} symbol="BTCUSDT" timeframe="1h" />)
    const chart = screen.getByTestId('price-chart')
    expect(chart).toBeInTheDocument()
  })

  it('renders bearish price movement when close < open', () => {
    const bearishCandles: Kline[] = [
      {
        open_time: 1_760_000_000_000,
        close_time: 1_760_000_359_999,
        open: 50000,
        high: 50200,
        low: 49000,
        close: 49200,
        volume: 80.0,
      },
    ]
    render(<CandleChart candles={bearishCandles} symbol="BTCUSDT" timeframe="1h" />)
    expect(screen.getByText('49,200.00')).toBeInTheDocument()
    expect(screen.getByText('-1.60%')).toBeInTheDocument()
  })
})

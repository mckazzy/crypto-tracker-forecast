import { describe, expect, it } from 'vitest'
import { ema20 } from '../lib/indicators'
import type { KlineFrame } from '../lib/futures'

const BASE_TIME = 1_760_000_000_000
const STEP_MS = 60_000
const ALPHA = 2 / 21

function frame(openTime: number, close: number): KlineFrame {
  return {
    type: 'kline',
    symbol: 'BTCUSDT',
    timeframe: '1m',
    open_time: openTime,
    close_time: openTime + STEP_MS - 1,
    open: close,
    high: close,
    low: close,
    close,
    volume: 1,
    is_closed: true,
  }
}

// closes 1..n, one minute apart, ascending
function series(closes: number[]): KlineFrame[] {
  return closes.map((close, i) => frame(BASE_TIME + i * STEP_MS, close))
}

function expectNoPointBefore20(candles: KlineFrame[], points: { time: number }[]) {
  const firstAllowed = Math.floor(candles[19].open_time / 1000)
  for (const p of points) expect(p.time).toBeGreaterThanOrEqual(firstAllowed)
  expect(points.map((p) => p.time)).toEqual(
    candles.slice(19).map((c) => Math.floor(c.open_time / 1000)),
  )
}

describe('ema20', () => {
  it('returns zero points for fewer than 20 closes (19 closes)', () => {
    const closes = Array.from({ length: 19 }, (_, i) => i + 1)
    expect(ema20(series(closes))).toEqual([])
    expect(ema20([])).toEqual([])
  })

  it('returns exactly one point at the 20th candle whose value is the manual mean', () => {
    const closes = Array.from({ length: 20 }, (_, i) => i + 1)
    const candles = series(closes)
    const points = ema20(candles)

    expect(points).toHaveLength(1)
    const mean = closes.reduce((a, b) => a + b, 0) / 20
    expect(points[0].value).toBeCloseTo(mean, 10)
    expect(points[0].value).toBeCloseTo(10.5, 10)
    expect(points[0].time).toBe(Math.floor(candles[19].open_time / 1000))
  })

  it('applies the manual recurrence at the 21st candle', () => {
    const closes = Array.from({ length: 21 }, (_, i) => i + 1)
    const candles = series(closes)
    const points = ema20(candles)

    expect(points).toHaveLength(2)
    const mean = closes.slice(0, 20).reduce((a, b) => a + b, 0) / 20
    const expected = closes[20] * ALPHA + mean * (1 - ALPHA)
    expect(points[1].value).toBeCloseTo(expected, 10)
    expect(points[1].value).toBeCloseTo(11.5, 10)
    expect(points[1].time).toBe(Math.floor(candles[20].open_time / 1000))
    expectNoPointBefore20(candles, points)
  })

  it('never emits a point before the 20th candle and stays time-ascending', () => {
    const closes = Array.from({ length: 25 }, (_, i) => 100 + i * 3)
    const candles = series(closes)
    const points = ema20(candles)

    expect(points).toHaveLength(6)
    expectNoPointBefore20(candles, points)
    for (let i = 1; i < points.length; i++) {
      expect(points[i].time).toBeGreaterThan(points[i - 1].time)
    }
  })

  it('sorts ascending by open_time before seeding the warm-up', () => {
    const closes = Array.from({ length: 21 }, (_, i) => i + 1)
    const shuffled = series(closes)
    // scramble input order; warm-up must use the sorted first 20 closes
    const mixed = [shuffled[20], shuffled[5], shuffled[0], ...shuffled.slice(1, 5), ...shuffled.slice(6, 20)]
    const points = ema20(mixed)

    expect(points).toHaveLength(2)
    expect(points[0].value).toBeCloseTo(10.5, 10)
    expect(points[1].value).toBeCloseTo(11.5, 10)
    expect(points[0].time).toBeLessThan(points[1].time)
  })
})

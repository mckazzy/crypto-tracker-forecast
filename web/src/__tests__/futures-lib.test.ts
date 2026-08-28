import { describe, expect, it } from 'vitest'
import {
  calcLiqPrice,
  calcMargin,
  calcPnl,
  MMR_BUFFER,
  wsUrl,
} from '../lib/futures'

describe('futures pre-check math (mirror backend)', () => {
  it('calcMargin = notional / leverage', () => {
    expect(calcMargin(1000, 10)).toBe(100)
    expect(calcMargin(1000, 1)).toBe(1000)
  })

  it('calcLiqPrice LONG uses MMR buffer higher than bankruptcy', () => {
    expect(MMR_BUFFER).toBe(0.005)
    const liq = calcLiqPrice(100, 10, 'LONG')
    expect(liq).toBeCloseTo(100 * (1 - 1 / 10 + 0.005))
    expect(liq).toBeGreaterThan(90) // bankruptcy = 90
  })

  it('calcLiqPrice SHORT uses MMR buffer lower than bankruptcy', () => {
    const liq = calcLiqPrice(100, 10, 'SHORT')
    expect(liq).toBeCloseTo(100 * (1 + 1 / 10 - 0.005))
    expect(liq).toBeLessThan(110) // bankruptcy = 110
  })

  it('calcPnl long/short', () => {
    expect(calcPnl(50000, 51000, 1, 'LONG')).toBe(1000)
    expect(calcPnl(50000, 49000, 1, 'SHORT')).toBe(1000)
  })
})

describe('wsUrl', () => {
  it('builds ws url from current host', () => {
    expect(wsUrl('BTCUSDT')).toContain('/ws/trade/BTCUSDT')
  })
})

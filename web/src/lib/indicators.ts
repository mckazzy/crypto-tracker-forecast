// Pure technical indicators computed client-side from the candles the chart
// already holds. No padding, no backfill: a value only exists once its input
// window exists (indicators.ts owner: EMA20 overlay).

import type { KlineFrame } from './futures'

export interface IndicatorPoint {
  /** UTC seconds, matching the lightweight-charts time scale. */
  time: number
  value: number
}

const EMA20_PERIOD = 20

/**
 * EMA(20) of candle closes.
 *
 * Sorts ascending by open_time. The first 20 closes seed a single arithmetic
 * mean placed at the 20th candle; each following candle applies the standard
 * recurrence close * (2/21) + prev * (19/21). Fewer than 20 candles yields an
 * empty array — no points are invented before the 20th candle.
 */
export function ema20(candles: KlineFrame[]): IndicatorPoint[] {
  if (candles.length < EMA20_PERIOD) return []

  const sorted = [...candles].sort((a, b) => a.open_time - b.open_time)

  let sum = 0
  for (let i = 0; i < EMA20_PERIOD; i++) sum += sorted[i].close
  let prev = sum / EMA20_PERIOD

  const points: IndicatorPoint[] = [
    { time: Math.floor(sorted[EMA20_PERIOD - 1].open_time / 1000), value: prev },
  ]

  const alpha = 2 / (EMA20_PERIOD + 1)
  for (let i = EMA20_PERIOD; i < sorted.length; i++) {
    prev = sorted[i].close * alpha + prev * (1 - alpha)
    points.push({ time: Math.floor(sorted[i].open_time / 1000), value: prev })
  }

  return points
}

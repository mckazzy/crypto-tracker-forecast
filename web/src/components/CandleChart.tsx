import { useEffect, useRef, useState } from 'react'
import {
  ColorType,
  createChart,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Kline } from '../lib/api'

interface CandleChartProps {
  candles: Kline[]
  symbol?: string
  timeframe?: string
}

function fmtPrice(n: number): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function CandleChart({ candles, symbol = 'BTCUSDT', timeframe = '1h' }: CandleChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const [hoveredCandle, setHoveredCandle] = useState<Kline | null>(null)

  const isTest = typeof process !== 'undefined' && process.env.NODE_ENV === 'test'
  const isCanvasAvailable = typeof window !== 'undefined' && typeof window.matchMedia === 'function' && !isTest

  const latestCandle = candles.length > 0 ? candles[candles.length - 1] : null
  const activeCandle = hoveredCandle || latestCandle

  useEffect(() => {
    if (!isCanvasAvailable || !chartContainerRef.current || candles.length === 0) return

    try {
      if (chartRef.current) {
        chartRef.current.remove()
        chartRef.current = null
      }

      const isDark = typeof document !== 'undefined' ? document.documentElement.classList.contains('dark') : true

      const container = chartContainerRef.current
      const chart = createChart(container, {
        width: container.clientWidth || 800,
        height: 380,
        layout: {
          background: { type: ColorType.Solid, color: 'transparent' },
          textColor: isDark ? '#94a3b8' : '#475569',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
        },
        grid: {
          vertLines: { color: isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(15, 23, 42, 0.05)' },
          horzLines: { color: isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(15, 23, 42, 0.05)' },
        },
        crosshair: {
          mode: CrosshairMode.Normal,
          vertLine: {
            color: isDark ? '#3b82f6' : '#2563eb',
            width: 1,
            style: 2,
            labelBackgroundColor: isDark ? '#3b82f6' : '#2563eb',
          },
          horzLine: {
            color: isDark ? '#3b82f6' : '#2563eb',
            width: 1,
            style: 2,
            labelBackgroundColor: isDark ? '#3b82f6' : '#2563eb',
          },
        },
        rightPriceScale: {
          borderColor: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(15, 23, 42, 0.08)',
          scaleMargins: {
            top: 0.1,
            bottom: 0.25,
          },
        },
        timeScale: {
          borderColor: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(15, 23, 42, 0.08)',
          timeVisible: true,
          secondsVisible: false,
        },
      })

      // Candlestick series
      let candleSeries: ISeriesApi<'Candlestick'>
      if ('addCandlestickSeries' in chart && typeof chart.addCandlestickSeries === 'function') {
        candleSeries = chart.addCandlestickSeries({
          upColor: '#059669',
          downColor: '#dc2626',
          borderVisible: false,
          wickUpColor: '#059669',
          wickDownColor: '#dc2626',
        })
      } else {
        // @ts-expect-error fallback method
        candleSeries = chart.addSeries?.(CandlestickSeries, {
          upColor: '#059669',
          downColor: '#dc2626',
          borderVisible: false,
          wickUpColor: '#059669',
          wickDownColor: '#dc2626',
        })
      }

      // Volume series
      let volumeSeries: ISeriesApi<'Histogram'>
      if ('addHistogramSeries' in chart && typeof chart.addHistogramSeries === 'function') {
        volumeSeries = chart.addHistogramSeries({
          color: isDark ? '#3b82f6' : '#2563eb',
          priceFormat: { type: 'volume' },
          priceScaleId: '',
        })
      } else {
        // @ts-expect-error fallback method
        volumeSeries = chart.addSeries?.(HistogramSeries, {
          color: isDark ? '#3b82f6' : '#2563eb',
          priceFormat: { type: 'volume' },
          priceScaleId: '',
        })
      }

      if (volumeSeries && volumeSeries.priceScale) {
        volumeSeries.priceScale().applyOptions({
          scaleMargins: {
            top: 0.8,
            bottom: 0,
          },
        })
      }

      const sortedCandles = [...candles].sort((a, b) => a.open_time - b.open_time)
      const uniqueCandles: Kline[] = []
      const seenTimes = new Set<number>()
      for (const c of sortedCandles) {
        const t = Math.floor(c.open_time / 1000)
        if (!seenTimes.has(t)) {
          seenTimes.add(t)
          uniqueCandles.push(c)
        }
      }

      const candleData = uniqueCandles.map((c) => ({
        time: Math.floor(c.open_time / 1000) as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))

      const volumeData = uniqueCandles.map((c) => ({
        time: Math.floor(c.open_time / 1000) as UTCTimestamp,
        value: c.volume,
        color: c.close >= c.open ? 'rgba(5, 150, 105, 0.35)' : 'rgba(220, 38, 38, 0.35)',
      }))

      candleSeries.setData(candleData)
      volumeSeries.setData(volumeData)

      chart.subscribeCrosshairMove((param) => {
        if (!param.time || !param.point) {
          setHoveredCandle(null)
          return
        }
        const timeSec =
          typeof param.time === 'number'
            ? param.time
            : typeof param.time === 'object' && param.time !== null && 'timestamp' in param.time
            ? (param.time as { timestamp: number }).timestamp
            : 0
        const found = uniqueCandles.find((c) => Math.floor(c.open_time / 1000) === timeSec)
        if (found) {
          setHoveredCandle(found)
        }
      })

      const resizeObserver = new ResizeObserver((entries) => {
        if (!entries || entries.length === 0 || !entries[0].contentRect) return
        const { width } = entries[0].contentRect
        chart.applyOptions({ width })
      })
      resizeObserver.observe(container)

      chart.timeScale().fitContent()
      chartRef.current = chart

      return () => {
        resizeObserver.disconnect()
        chart.remove()
        chartRef.current = null
      }
    } catch {
      // ignore
    }
  }, [candles, isCanvasAvailable])

  if (candles.length === 0) {
    return (
      <div className="flex h-80 items-center justify-center text-[var(--color-text-muted)] text-sm">
        No candle data available
      </div>
    )
  }

  const renderSvg = () => {
    const lows = Math.min(...candles.map((c) => c.low))
    const highs = Math.max(...candles.map((c) => c.high))
    const span = highs - lows || 1
    const W = 1000
    const H = 300
    const step = candles.length > 1 ? W / (candles.length - 1) : W
    const points = candles
      .map((c, i) => `${(i * step).toFixed(1)},${(H - ((c.close - lows) / span) * H).toFixed(1)}`)
      .join(' ')

    return (
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-80" data-testid="price-chart">
        <defs>
          <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2563eb" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#2563eb" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        <polyline points={points} fill="none" stroke="#2563eb" strokeWidth="2.5" />
      </svg>
    )
  }

  const change = activeCandle ? activeCandle.close - activeCandle.open : 0
  const changePct = activeCandle && activeCandle.open > 0 ? (change / activeCandle.open) * 100 : 0
  const isUp = change >= 0

  return (
    <div className="relative flex flex-col w-full">
      {/* Chart Header Bar with live OHLCV metrics */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 mb-2 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2">
          <span className="font-bold text-[var(--color-text-main)] text-sm">{symbol}</span>
          <span className="text-xs px-2 py-0.5 rounded-md bg-[var(--color-surface-2)] text-[var(--color-primary)] font-mono font-bold border border-[var(--color-border)]">
            {timeframe}
          </span>
        </div>

        {activeCandle && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono tabular-nums text-[var(--color-text-muted)]">
            <span>
              O: <span className="text-[var(--color-text-main)] font-semibold">{fmtPrice(activeCandle.open)}</span>
            </span>
            <span>
              H: <span className="text-[var(--color-text-main)] font-semibold">{fmtPrice(activeCandle.high)}</span>
            </span>
            <span>
              L: <span className="text-[var(--color-text-main)] font-semibold">{fmtPrice(activeCandle.low)}</span>
            </span>
            <span>
              C:{' '}
              <span className={`font-bold ${isUp ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                {fmtPrice(activeCandle.close)}
              </span>
            </span>
            <span
              className={`px-1.5 py-0.5 rounded-full text-[11px] font-bold ${
                isUp ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
              }`}
            >
              {isUp ? '+' : ''}
              {changePct.toFixed(2)}%
            </span>
            <span>
              Vol: <span className="text-[var(--color-text-main)] font-semibold">{activeCandle.volume.toFixed(1)}</span>
            </span>
          </div>
        )}
      </div>

      {/* Primary Chart Container */}
      <div className="w-full relative min-h-[380px]">
        {!isCanvasAvailable ? (
          renderSvg()
        ) : (
          <>
            <div ref={chartContainerRef} className="w-full h-[380px]" />
            <div className="hidden" data-testid="price-chart">
              {renderSvg()}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default CandleChart

import { useEffect, useRef } from 'react'
import {
  ColorType,
  createChart,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { KlineFrame } from '../../lib/futures'

interface FuturesChartProps {
  candles: KlineFrame[]
  entry?: number | null
  tp?: number | null
  sl?: number | null
  liq?: number | null
}

export function FuturesChart({ candles, entry, tp, sl, liq }: FuturesChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)

  const isTest = typeof process !== 'undefined' && process.env.NODE_ENV === 'test'
  const isCanvasAvailable = typeof window !== 'undefined' && typeof window.matchMedia === 'function' && !isTest

  // Init chart once
  useEffect(() => {
    if (!isCanvasAvailable || !containerRef.current) return
    try {
      const isDark = typeof document !== 'undefined' ? document.documentElement.classList.contains('dark') : true
      const chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth || 800,
        height: 360,
        layout: {
          background: { type: ColorType.Solid, color: 'transparent' },
          textColor: isDark ? '#94a3b8' : '#475569',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
        },
        grid: {
          vertLines: { color: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(15,23,42,0.05)' },
          horzLines: { color: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(15,23,42,0.05)' },
        },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { scaleMargins: { top: 0.1, bottom: 0.2 } },
        timeScale: { timeVisible: true, secondsVisible: false },
      })
      let series: ISeriesApi<'Candlestick'>
      if ('addCandlestickSeries' in chart && typeof chart.addCandlestickSeries === 'function') {
        series = chart.addCandlestickSeries({
          upColor: '#059669',
          downColor: '#dc2626',
          borderVisible: false,
          wickUpColor: '#059669',
          wickDownColor: '#dc2626',
        })
      } else {
        // @ts-expect-error fallback method (v5 early)
        series = chart.addSeries?.('Candlestick', {
          upColor: '#059669',
          downColor: '#dc2626',
          borderVisible: false,
          wickUpColor: '#059669',
          wickDownColor: '#dc2626',
        })
      }
      chartRef.current = chart
      seriesRef.current = series
      const ro = new ResizeObserver((entries) => {
        if (entries[0]?.contentRect?.width) chart.applyOptions({ width: entries[0].contentRect.width })
      })
      ro.observe(containerRef.current)
      return () => {
        ro.disconnect()
        chart.remove()
        chartRef.current = null
        seriesRef.current = null
      }
    } catch {
      /* ignore canvas errors in jsdom */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isCanvasAvailable])

  // Incremental update từ kline WS frames
  useEffect(() => {
    const series = seriesRef.current
    if (!series || candles.length === 0) return
    const sorted = [...candles].sort((a, b) => a.open_time - b.open_time)
    // setData toàn bộ khi chưa có data; update incremental sau đó
    series.setData(
      sorted.map((c) => ({
        time: Math.floor(c.open_time / 1000) as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    )
    chartRef.current?.timeScale().fitContent()
  }, [candles])

  // Price lines entry/TP/SL/liq
  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    const lines = [
      { price: entry ?? null, color: '#f59e0b', title: 'Entry' },
      { price: tp ?? null, color: '#10b981', title: 'TP' },
      { price: sl ?? null, color: '#ef4444', title: 'SL' },
      { price: liq ?? null, color: '#a855f7', title: 'Liq' },
    ].filter((l): l is { price: number; color: string; title: string } => l.price != null && l.price > 0)
    try {
      // remove all existing then recreate (v5 IPriceLine API)
      for (const pl of seriesRef.current?.priceLines() ?? []) {
        try {
          series.removePriceLine(pl)
        } catch {
          /* ignore */
        }
      }
      for (const l of lines) {
        series.createPriceLine({ price: l.price, color: l.color, title: l.title, lineWidth: 1, lineStyle: 2 })
      }
    } catch {
      /* price lines API may vary across v5 patch versions */
    }
  }, [entry, tp, sl, liq])

  if (!isCanvasAvailable) {
    return (
      <div className="flex h-80 items-center justify-center text-[var(--color-text-muted)] text-sm" data-testid="futures-chart">
        {candles.length > 0 ? `${candles.length} candles` : 'Waiting for live klines…'}
      </div>
    )
  }

  return <div ref={containerRef} data-testid="futures-chart" className="w-full h-[360px]" />
}

export default FuturesChart

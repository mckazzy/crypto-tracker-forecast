import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  CrosshairMode,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { KlineFrame } from '../../lib/futures'
import { ema20 } from '../../lib/indicators'

const EMA20_COLOR = '#3b82f6'

interface FuturesChartProps {
  candles: KlineFrame[]
  entry?: number | null
  tp?: number | null
  sl?: number | null
  liq?: number | null
  ema20Enabled?: boolean
}

export function FuturesChart({ candles, entry, tp, sl, liq, ema20Enabled = false }: FuturesChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const emaSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)

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
      // PRE-EXISTING BUG FIX (separate from the EMA feature, revertible on its own):
      // the old v4-style probe for chart.addCandlestickSeries plus the
      // chart.addSeries?.('Candlestick', ...) string fallback always threw in
      // lightweight-charts v5.2.1 (no such method; v5 takes an imported series
      // definition), and the outer try/catch swallowed it, so the base chart
      // never rendered. Series options are byte-for-byte unchanged.
      const series = chart.addSeries(CandlestickSeries, {
        upColor: '#059669',
        downColor: '#dc2626',
        borderVisible: false,
        wickUpColor: '#059669',
        wickDownColor: '#dc2626',
      })
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
        emaSeriesRef.current = null
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

  // EMA(20) overlay — opt-in line series. OFF by default: with ema20Enabled
  // false no series exists, so base chart behaviour is untouched. The series is
  // created once while enabled and removed when toggled off (or when there are
  // fewer than 20 candles to seed it); the full window is recomputed on each
  // candles change. Teardown clears the ref alongside the base chart.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const points = ema20Enabled ? ema20(candles) : []
    if (points.length === 0) {
      if (emaSeriesRef.current) {
        try {
          chart.removeSeries(emaSeriesRef.current)
        } catch {
          /* ignore */
        }
        emaSeriesRef.current = null
      }
      return
    }
    let line = emaSeriesRef.current
    if (!line) {
      line = chart.addSeries(LineSeries, { color: EMA20_COLOR, lineWidth: 2 })
      emaSeriesRef.current = line
    }
    line.setData(
      points.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })),
    )
  }, [candles, ema20Enabled, isCanvasAvailable])

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

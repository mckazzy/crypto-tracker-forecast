## 1. EMA(20) DESIGN

- Put pure `ema20(candles: KlineFrame[])` math in a new `web/src/lib/indicators.ts`; keep chart lifecycle in `FuturesChart` and the toggle state in `FuturesTerminal`. The input has `open_time`, `close`, and `is_closed` (`web/src/lib/futures.ts:51-63`); the terminal already owns up to 500 candles (`web/src/components/futures/FuturesTerminal.tsx:22,70-79`).
- Sort by `open_time`; use the first 20 observed `close` values to seed their arithmetic mean at candle 20, then `EMA = close * (2/21) + previousEMA * (19/21)`. Emit no point at candles 1-19 and never pad or fabricate history. Recalculate the latest point when an unclosed candle's close changes (`web/src/lib/futures.ts:60-62`; `web/src/components/futures/FuturesTerminal.tsx:74-79`).
- Recompute the full bounded candle window on each data update or toggle-on. This handles REST seed, replaced live candles, and window truncation consistently; at 500 candles it is small enough to avoid incremental state and reset logic (`web/src/components/futures/FuturesTerminal.tsx:22,86-97`).
- Default toggle OFF in `FuturesTerminal`; pass `ema20Enabled` to `FuturesChart`. With OFF, create no EMA series and leave the existing candlestick `setData`, `fitContent`, and Entry/TP/SL/Liq price-line effects unchanged (`web/src/components/futures/FuturesChart.tsx:87-130`). With ON and at least 20 closes, add one line series to the existing chart, set its computed points, and retain its ref; on OFF remove only that series and clear its ref. With fewer than 20 closes, create no line series. Chart teardown also clears the EMA ref (`web/src/components/futures/FuturesChart.tsx:28-85`).

## 2. TEST CASES

- Pure math: 19 closes yield zero points; 20 closes yield exactly one point at the twentieth candle.
- Pure math: that first point equals a manually calculated mean; the twenty-first equals the manual `2/21` recurrence. Replacing the last candle's close updates that point without duplicating its time.
- Chart toggle OFF: no EMA line series is created; existing candles and Entry/TP/SL/Liq price lines still work.
- Chart toggle ON with fewer than 20 candles: no EMA line is rendered. ON with 20 creates one; toggling OFF removes only it.
- Keep the existing no-canvas two-candle test passing: it still says `2 candles` (`web/src/__tests__/FuturesChart.test.tsx:35-44`). Exercise line-series behavior with a chart API stub because the current test environment skips canvas (`web/src/components/futures/FuturesChart.tsx:25-30,132-140`).

## 3. 12 REMAINING INDICATORS (13 TOTAL INCLUDING EMA20)

- Overlay — SMA(20): 20 close values; pure math in `indicators.ts`, line series in `FuturesChart`.
- Overlay — EMA(50): 50 close values; same math/series boundary as EMA(20).
- Overlay — Bollinger Bands(20,2): 20 closes for mean and standard deviation; three chart line series.
- Overlay — VWAP: typical price and volume from OHLCV; chart line series, with session reset policy to decide.
- Overlay — Donchian Channel(20): rolling highs/lows; two chart line series.
- Separate pane — RSI(14): close deltas; oscillator pane below `FuturesChart`.
- Separate pane — MACD(12,26,9): closes; MACD/signal lines and histogram in oscillator pane.
- Separate pane — Stochastic(14,3): high/low/close; %K/%D in oscillator pane.
- Separate pane — OBV: close direction and volume; volume-derived pane.
- Separate pane — Volume: per-candle volume; histogram pane.
- Stats — ATR(14): true range from high/low/previous close; compact chart-adjacent metric.
- Stats — ADX(14): high/low/close directional movement; compact chart-adjacent metric.

## 4. GRID + FUNDING DISAMBIGUATION

- **Grid:** For this single-chart EMA pilot, `grid` means chart gridlines: `FuturesChart` configures `vertLines` and `horzLines` (`web/src/components/futures/FuturesChart.tsx:42-45`), while `FuturesTerminal` renders one `FuturesChart` beside the order form (`web/src/components/futures/FuturesTerminal.tsx:202-213`). A multi-chart grid is a different backlog item: the roadmap names a five-symbol futures dashboard (`docs/roadmap.md:83-88`); the existing Bento grid is page layout (`web/src/App.tsx:335-343`; `docs/design-specs.md:45-55`).
- **Funding:** Treat funding-rate **display** as the closer UI meaning, pending a data source: the inspected market frame has mark and OHLCV but no funding rate (`web/src/lib/futures.ts:44-65`), and the terminal subscribes only to mark/kline callbacks (`web/src/components/futures/FuturesTerminal.tsx:59-82`). Funding **settlement** would change the demo wallet balance, whose inspected client contract exposes only balance, margin used, and unrealized P&L (`web/src/lib/futures.ts:5-9`), and whose UI currently offers a reset action (`web/src/components/futures/FuturesTerminal.tsx:141-160,173-179`); it needs a separate engine/account decision.

**OPEN DECISIONS**

- Confirm whether `grid` means the existing chart gridlines or the roadmap's five-symbol layout for any later scope (`web/src/components/futures/FuturesChart.tsx:42-45`; `docs/roadmap.md:83-88`).
- Confirm funding scope: display-only rate and source, or wallet settlement rules and accounting contract (`web/src/lib/futures.ts:5-9,44-65`).
- Decide whether VWAP resets per UTC day, exchange session, or visible window.

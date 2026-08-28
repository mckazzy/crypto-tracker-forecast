# Design Specifications: Crypto Tracker & Forecast (Cyber Obsidian Terminal)

> Tài liệu quy chuẩn thiết kế UI/UX được tổng hợp và chắt lọc từ 3 nền tảng crypto hàng đầu: **TradingView** (độ chuẩn xác biểu đồ), **Binance / Hyperliquid** (bố cục terminal & vị thế giao dịch), và **DexScreener / Arkham** (Bento grid phân tích & AI Leaderboard).

---

## 1. 🎨 Color Palette & Design Tokens

### Background & Surface Hierarchy
| Token | Hex / Class | Mô tả / Mục đích sử dụng |
| :--- | :--- | :--- |
| `bg-app` | `#080b11` | Nền canvas toàn app (Deep Space Obsidian, chống mỏi mắt) |
| `bg-surface` | `#0f172a` (Slate 900) | Nền card, widget, bento panels |
| `bg-surface-elevated`| `#1e293b` (Slate 800) | Nền dropdown, modal, table header, button phụ |
| `border-subtle` | `rgba(255, 255, 255, 0.08)` | Viền kính mờ tinh tế cho card và table rows |
| `border-accent` | `rgba(6, 182, 212, 0.4)` | Viền sáng nhẹ cho card active hoặc AI forecast |

### Trading & Data Colors
| Token | Hex / RGB | Mô tả / Mục đích sử dụng |
| :--- | :--- | :--- |
| `color-bull` | `#10b981` (Emerald 500) | Tăng giá, Nến xanh, Lệnh LONG, Win, Lợi nhuận PnL dương |
| `color-bull-glow` | `rgba(16, 185, 129, 0.15)` | Hiệu ứng phát sáng nhẹ sau nút Long, Badge Win |
| `color-bear` | `#f43f5e` (Rose 500) | Giảm giá, Nến đỏ, Lệnh SHORT, Lose, Thua lỗ PnL âm |
| `color-bear-glow` | `rgba(244, 63, 94, 0.15)` | Hiệu ứng phát sáng sau nút Short, Badge Lose |
| `color-brand` | `#06b6d4` (Cyan 500) | Accent AI Prediction, Active Tab, Key action buttons |
| `text-primary` | `#f8fafc` (Slate 50) | Tiêu đề, con số giá chính |
| `text-secondary` | `#94a3b8` (Slate 400) | Nhãn thuộc tính, thông số phụ |
| `text-muted` | `#64748b` (Slate 500) | Timestamps, đơn vị nhỏ |

---

## 2. 📝 Typography System

| Role | Font Family | Size | Weight | Line Height | Usage |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Display / Price** | `Inter / JetBrains Mono` | `32px - 40px` | `800 (Extrabold)` | `1.1` | Giá realtime, Total PnL |
| **Heading 1 / Title**| `Inter` | `24px` | `700 (Bold)` | `1.2` | Tên App, Section Header |
| **Heading 2 / Card** | `Inter` | `16px - 18px` | `600 (Semibold)`| `1.3` | Tiêu đề card, Ticker name |
| **Data / Numbers** | `JetBrains Mono, monospace` | `13px - 15px` | `500 (Medium)` | `1.4` | `tabular-nums` giá OHLCV, volume, PnL% |
| **Body / Labels** | `Inter, sans-serif` | `13px - 14px` | `400 (Regular)` | `1.5` | Chữ hiển thị, mô tả |
| **Badge / Micro** | `Inter, sans-serif` | `11px - 12px` | `600 (Semibold)`| `1.0` | Status badge, Timeframe pills |

---

## 3. 📐 Layout Architecture (Bento Grid Style)

```
+------------------------------------------------------------------------------------+
| 🟢 LIVE | 🪙 Crypto Tracker & Forecast   [Dashboard] [Leaderboard] [Paper Trading]   |
+------------------------------------------------------------------------------------+
| [BTCUSDT ▼] [15m] [1h] [4h] [1d] [1w]         $91,420.50  ▲ +3.42% (24h Volume $48B)|
+------------------------------------------------------------------------------------+
|                                                  |   🎯 QUICK STATS / AI FORECAST  |
|         📈 CANDLESTICK & VOLUME CHART            |   - AI Signal: STRONG BUY (84%) |
|         (Nến Nhật, Volume Bars, Gridlines)       |   - Target TP: $94,500          |
|                                                  |   - Stop Loss: $89,200          |
+------------------------------------------------------------------------------------+
| 📊 HISTORICAL OHLCV / RECENT TRADES (Data Table with Glass Hover & Tabular Digits) |
+------------------------------------------------------------------------------------+
```

---

## 4. 🧩 Component Specifications

### 1. Navigation & Ticker Header
* Thẻ kính mờ cố định `backdrop-blur-md bg-slate-950/80 border-b border-slate-800`.
* Logo đi kèm đèn LED xanh nhấp nháy (`animate-pulse`) báo hiệu kết nối dữ liệu trực tiếp.
* Tab menu dạng **Segmented Pill Selector** có transition chuyển động êm.

### 2. Timeframe & Symbol Selector
* Nút khung thời gian (5m, 15m, 1h, 4h, 1d, 1w) thiết kế dạng **Pills** viền mỏng. Khi active: nền Cyan/Emerald phát sáng nhẹ.
* Symbol Selector dạng Dropdown hiện đại có logo crypto thu nhỏ.

### 3. Chart Container
* Nâng cấp biểu đồ từ đường kẻ đơn giản sang:
  * Trục giá (Y-axis) và trục thời gian (X-axis) rõ ràng.
  * Hiển thị nến xanh/đỏ hoặc đường diện tích Gradient (Area Chart) mượt mà.
  * Cột khối lượng giao dịch (Volume Histogram) đặt ở đáy biểu đồ.
  * Crosshair tooltip tương tác khi rê chuột hiển thị OHLCV chính xác của từng nến.

### 4. Paper Trading Cards & Table
* **Bento Metric Cards**:
  * Card 1: *Total P&L* với % đổi màu xanh/đỏ kèm icon xu hướng.
  * Card 2: *Win Rate* với thanh tiến trình gradient.
  * Card 3: *Active Positions / Closed* hiển thị đếm số lượng.
* **Positions Table**:
  * Badge `LONG` xanh emerald nền mờ, `SHORT` đỏ rose nền mờ.
  * Các nút hành động `Close`, `Win`, `Lose` thiết kế dạng micro-buttons bo góc đẹp mắt.

### 5. AI Leaderboard
* Bảng xếp hạng các AI Model (DeepSeek, Claude, Gemini, Qwen, v.v.) với badge huy chương 🥇 🥈 🥉.
* Cột `Signals`, `Win Rate`, `Token Cost` kèm thanh chỉ số trực quan (progress bar) thay vì chỉ hiện text thô.

---

## 5. ✨ Micro-Interactions & Animation Tokens
* **Hover transition**: `transition-all duration-200 ease-in-out`
* **Card Hover**: `hover:border-slate-700 hover:shadow-lg hover:shadow-cyan-500/5`
* **Pulsing Indicator**: `animate-pulse` cho live feeds.
* **Number Rendering**: Luôn thêm class `tabular-nums font-mono` để số không bị nhảy layout khi giá cập nhật realtime.

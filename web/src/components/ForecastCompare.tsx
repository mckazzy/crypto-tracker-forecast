import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle,
  Award,
  Brain,
  CheckCircle2,
  Cpu,
  Download,
  FileCheck2,
  Flame,
  Frown,
  RefreshCw,
  RotateCcw,
  Sparkles,
  Target,
  Trash2,
  TrendingDown,
  TrendingUp,
  UserCheck,
  Zap,
} from 'lucide-react'
import { fetchKlines } from '../lib/api'
import {
  deleteForecast,
  evaluateForecastQuality,
  exportForecastsCsv,
  fetchAnalytics,
  fetchForecasts,
  retrainModel,
  runForecast,
  scoreAllExpired,
  scoreForecast,
  submitUserForecast,
  type AnalyticsResponse,
  type CompareResponse,
  type ForecastRecord,
  type PendingForecastConfirmation,
  type SignalPayload,
} from '../lib/forecast'

const TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d', '1w']
const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']
const GMT7_OFFSET_MS = 7 * 3600 * 1000

function fmtPrice(n: number | null | undefined): string {
  if (n == null) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtGmt7(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const shifted = new Date(d.getTime() + GMT7_OFFSET_MS)
  return shifted.toISOString().replace('T', ' ').slice(0, 16)
}

function DirectionBadge({ dir }: { dir?: string }) {
  if (dir === 'LONG') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
        <TrendingUp className="w-3 h-3" />
        <span>LONG</span>
      </span>
    )
  }
  if (dir === 'SHORT') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-rose-500/10 text-rose-400 border border-rose-500/30">
        <TrendingDown className="w-3 h-3" />
        <span>SHORT</span>
      </span>
    )
  }
  return <span className="text-[var(--color-text-subtle)] text-[11px]">FLAT</span>
}

function SourceBadge({ source }: { source?: string }) {
  if (source === 'AI') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-violet-500/15 text-violet-300 border border-violet-500/40 shadow-sm shadow-violet-500/10">
        <Brain className="w-3 h-3 text-violet-400" />
        <span>AI</span>
      </span>
    )
  }
  if (source === 'User') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/40 shadow-sm shadow-amber-500/10">
        <UserCheck className="w-3 h-3 text-amber-400" />
        <span>User</span>
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-sky-500/15 text-sky-300 border border-sky-500/40 shadow-sm shadow-sky-500/10">
      <Cpu className="w-3 h-3 text-sky-400" />
      <span>Local</span>
    </span>
  )
}

function OutcomeScoreBadge({
  direction,
  outcome,
}: {
  direction?: string
  outcome: NonNullable<ForecastRecord['outcome']>
}) {
  const score = outcome.score
  if (score == null) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold bg-[var(--color-surface-2)] text-[var(--color-text-main)] border border-[var(--color-border)]">
        <CheckCircle2 className="w-3 h-3" />
        <span>{outcome.outcome}</span>
      </span>
    )
  }

  const isPositive = score > 0
  const isNegative = score < 0
  const isTargetAchieved = score >= 100

  const isPriceUp = direction === 'SHORT' ? isNegative : isPositive

  const colorClass = isPositive
    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
    : isNegative
      ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
      : 'bg-[var(--color-surface-2)] text-[var(--color-text-main)] border border-[var(--color-border)]'

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold border ${colorClass} ${
        isTargetAchieved ? 'ring-1 ring-amber-400/40 shadow-sm shadow-amber-500/10' : ''
      }`}
    >
      {isTargetAchieved && (
        <span title="Đạt mục tiêu >= 100%" aria-label="Huy hiệu đạt mục tiêu >= 100%">
          <Award className="w-3.5 h-3.5 text-amber-400 fill-amber-400/20 shrink-0" />
        </span>
      )}

      {isNegative && (
        <span title="Điểm âm" aria-label="Mặt khóc">
          <Frown className="w-3.5 h-3.5 text-rose-400 shrink-0" />
        </span>
      )}

      {score !== 0 ? (
        isPriceUp ? (
          <TrendingUp className="w-3 h-3 shrink-0" />
        ) : (
          <TrendingDown className="w-3 h-3 shrink-0" />
        )
      ) : (
        <CheckCircle2 className="w-3 h-3 shrink-0" />
      )}

      <span>{score > 0 ? `+${score}%` : `${score}%`}</span>
    </span>
  )
}

function Countdown({ validUntil }: { validUntil: string | null }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  if (!validUntil) return <span className="text-slate-600">—</span>
  const diff = new Date(validUntil).getTime() - now
  if (diff <= 0) return <span className="text-rose-400 font-bold">Đã chốt</span>
  const s = Math.floor(diff / 1000)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    <span className="font-mono tabular-nums text-cyan-300">
      {pad(h)}:{pad(m)}:{pad(sec)}
    </span>
  )
}

function SignalCard({
  title,
  icon,
  badgeText,
  badgeClass,
  signal,
  error,
}: {
  title: string
  icon: React.ReactNode
  badgeText?: string
  badgeClass?: string
  signal?: SignalPayload
  error?: string
}) {
  return (
    <div className="p-4 rounded-xl surface-card flex flex-col gap-2.5 transition-all hover:border-[var(--color-border)]">
      <div className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] pb-2">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[var(--color-text-main)]">
          <span className="p-1.5 rounded-lg bg-[var(--color-surface-2)] text-cyan-400 border border-[var(--color-border)]/60">
            {icon}
          </span>
          {title}
        </div>
        {badgeText && (
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${badgeClass ?? 'bg-[var(--color-surface-2)] text-[var(--color-text-muted)] border-[var(--color-border)]'}`}>
            {badgeText}
          </span>
        )}
      </div>
      {error ? (
        <div className="text-xs text-rose-400 py-4">{error}</div>
      ) : signal ? (
        <>
          <div className="flex items-center justify-between">
            <DirectionBadge dir={signal.direction} />
            <span className="font-mono text-xs text-[var(--color-text-main)] bg-[var(--color-surface-2)] px-2 py-0.5 rounded border border-[var(--color-border)]">
              Độ tin cậy: {(signal.probability * 100).toFixed(1)}%
            </span>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs bg-[var(--color-surface-2)] p-2.5 rounded-lg border border-[var(--color-border)]/50 font-mono tabular-nums">
            <span className="text-[var(--color-text-subtle)] font-sans">Entry</span>
            <span className="text-[var(--color-text-main)] text-right font-bold">{fmtPrice(signal.entry)}</span>
            <span className="text-[var(--color-text-subtle)] font-sans">Take Profit (TP)</span>
            <span className="text-emerald-400 text-right font-bold">
              {signal.take_profit.length > 0 ? signal.take_profit.map(fmtPrice).join(' / ') : '—'}
            </span>
            <span className="text-[var(--color-text-subtle)] font-sans">Stop Loss (SL)</span>
            <span className="text-rose-400 text-right font-bold">{fmtPrice(signal.stop_loss)}</span>
            <span className="text-[var(--color-text-subtle)] font-sans">Risk : Reward (R:R)</span>
            <span className="text-cyan-300 text-right font-bold">
              {signal.rr_ratio != null ? `1 : ${signal.rr_ratio.toFixed(2)}` : '—'}
            </span>
          </div>
        </>
      ) : (
        <div className="text-xs text-[var(--color-text-subtle)] py-6 text-center italic">
          Chưa chạy — chọn nút kích hoạt phía trên
        </div>
      )}
    </div>
  )
}

function AnalyticsCards({ data }: { data: AnalyticsResponse }) {
  const srcEntries = Object.entries(data.by_source)
  return (
    <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <div className="p-4 rounded-xl surface-card border border-[var(--color-border)]">
        <div className="text-xs text-[var(--color-text-muted)] font-medium mb-1 flex items-center justify-between">
          <span>Tổng dự báo</span>
          <Zap className="w-3.5 h-3.5 text-cyan-400" />
        </div>
        <div className="text-2xl font-extrabold font-mono text-[var(--color-text-main)]">{data.total}</div>
        <div className="text-[11px] text-[var(--color-text-subtle)] mt-1">Đã chấm kết quả: {data.scored_total}</div>
      </div>
      <div className="p-4 rounded-xl surface-card border border-[var(--color-border)]">
        <div className="text-xs text-[var(--color-text-muted)] font-medium mb-1 flex items-center justify-between">
          <span>Độ chính xác TB</span>
          <Award className="w-3.5 h-3.5 text-amber-400" />
        </div>
        <div className="text-2xl font-extrabold font-mono text-cyan-300">
          {data.avg_accuracy > 0 ? `+${data.avg_accuracy}` : data.avg_accuracy}%
        </div>
        <div className="text-[11px] text-[var(--color-text-subtle)] mt-1">
          LONG {data.direction_split.LONG} · SHORT {data.direction_split.SHORT} · FLAT {data.direction_split.FLAT}
        </div>
      </div>
      {srcEntries.map(([src, v]) => (
        <div key={src} className="p-4 rounded-xl surface-card border border-[var(--color-border)]">
          <div className="text-xs text-[var(--color-text-muted)] font-medium mb-1 flex items-center justify-between">
            <span>Nguồn {src}</span>
            {src === 'AI' ? (
              <Brain className="w-3.5 h-3.5 text-violet-400" />
            ) : src === 'User' ? (
              <UserCheck className="w-3.5 h-3.5 text-amber-400" />
            ) : (
              <Cpu className="w-3.5 h-3.5 text-sky-400" />
            )}
          </div>
          <div className="text-2xl font-extrabold font-mono text-[var(--color-text-main)]">
            {v.accuracy > 0 ? `+${v.accuracy}` : v.accuracy}%
          </div>
          <div className="text-[11px] text-[var(--color-text-subtle)] mt-1">
            {v.wins} win / {v.losses} lose (scored {v.scored})
          </div>
        </div>
      ))}
    </section>
  )
}

function ForecastCompare() {
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [timeframe, setTimeframe] = useState('4h')
  const [compare, setCompare] = useState<CompareResponse | null>(null)
  const [userSignal, setUserSignal] = useState<SignalPayload | null>(null)
  const [forecasts, setForecasts] = useState<ForecastRecord[]>([])
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null)

  // Running action state for independent loading indicators
  const [runningAction, setRunningAction] = useState<
    'ai' | 'local' | 'user' | 'combo_ai_user' | 'combo_ai_local' | 'combo_local_user' | 'combo_all' | 'score_all' | null
  >(null)
  const [retraining, setRetraining] = useState(false)
  const [retrainMsg, setRetrainMsg] = useState<string | null>(null)
  const [scoreMsg, setScoreMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Pending confirmation for low confidence or narrow TP delta
  const [pendingConfirm, setPendingConfirm] = useState<PendingForecastConfirmation | null>(null)

  const handleDiscardPending = async (item: PendingForecastConfirmation) => {
    try {
      await deleteForecast(item.id)
      setScoreMsg(`Đã hủy & xóa dự báo #${item.id} (${item.source}) do không đạt chuẩn chất lượng`)
    } catch (e) {
      setError(String(e))
    } finally {
      setPendingConfirm(null)
      loadAll()
    }
  }

  const handleProceedPending = (item: PendingForecastConfirmation) => {
    const name = item.source === 'AI' ? 'ai' : `intraday_lgbm@${item.symbol}@${item.timeframe}`
    setCompare((c) => ({
      ...(c ?? { symbol: item.symbol, timeframe: item.timeframe, results: {} }),
      results: { ...(c?.results ?? {}), [name]: item.signal },
    }))
    setScoreMsg(`Đã xác nhận lưu & hiển thị dự báo #${item.id} (${item.source}) — chốt lúc ${fmtGmt7(item.valid_until)} GMT+7`)
    setPendingConfirm(null)
    loadAll()
  }

  // User input form states
  const [userDirection, setUserDirection] = useState<'LONG' | 'SHORT'>('LONG')
  const [userEntry, setUserEntry] = useState('')
  const [userTP, setUserTP] = useState('')
  const [userSL, setUserSL] = useState('')
  const [userConfidence, setUserConfidence] = useState(80)
  const [currentPrice, setCurrentPrice] = useState<number | null>(null)

  const isBusy = runningAction !== null || retraining

  // Tự động lấy giá live hiện tại khi symbol hoặc timeframe thay đổi
  useEffect(() => {
    let active = true
    const fetchLive = () => {
      fetchKlines(symbol, timeframe, 5)
        .then((res) => {
          if (!active || !res.data || res.data.length === 0) return
          const latestClose = res.data[res.data.length - 1].close
          setCurrentPrice(latestClose)
        })
        .catch(() => {})
    }
    fetchLive()
    const timer = setInterval(fetchLive, 15_000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [symbol, timeframe])

  // Giá entry hiệu dụng: giá user gõ hoặc giá live hiện tại
  const effectiveEntry = useMemo(() => {
    const parsed = parseFloat(userEntry)
    if (!isNaN(parsed) && parsed > 0) return parsed
    return currentPrice || 0
  }, [userEntry, currentPrice])

  // Tính % tăng/giảm của TP so với Entry
  const tpPct = useMemo(() => {
    const tpNum = parseFloat(userTP)
    if (!effectiveEntry || isNaN(tpNum) || tpNum <= 0) return null
    return ((tpNum - effectiveEntry) / effectiveEntry) * 100
  }, [effectiveEntry, userTP])

  // Tính % tăng/giảm của SL so với Entry
  const slPct = useMemo(() => {
    const slNum = parseFloat(userSL)
    if (!effectiveEntry || isNaN(slNum) || slNum <= 0) return null
    return ((slNum - effectiveEntry) / effectiveEntry) * 100
  }, [effectiveEntry, userSL])

  // Gán % TP tự động
  const applyTpPct = (pct: number) => {
    if (!effectiveEntry) return
    const sign = userDirection === 'LONG' ? 1 : -1
    const target = effectiveEntry * (1 + (sign * pct) / 100)
    setUserTP(target >= 10 ? target.toFixed(2) : target.toPrecision(4))
  }

  // Gán % SL tự động
  const applySlPct = (pct: number) => {
    if (!effectiveEntry) return
    const sign = userDirection === 'LONG' ? -1 : 1
    const target = effectiveEntry * (1 + (sign * pct) / 100)
    setUserSL(target >= 10 ? target.toFixed(2) : target.toPrecision(4))
  }

  // Chuyển hướng LONG / SHORT và tự đảo chiều % TP & SL
  const toggleDirection = (dir: 'LONG' | 'SHORT') => {
    if (dir === userDirection) return
    setUserDirection(dir)
    if (effectiveEntry && userTP) {
      const oldTpPct = Math.abs(((parseFloat(userTP) - effectiveEntry) / effectiveEntry) * 100)
      if (oldTpPct > 0) {
        const sign = dir === 'LONG' ? 1 : -1
        const newTp = effectiveEntry * (1 + (sign * oldTpPct) / 100)
        setUserTP(newTp >= 10 ? newTp.toFixed(2) : newTp.toPrecision(4))
      }
    }
    if (effectiveEntry && userSL) {
      const oldSlPct = Math.abs(((parseFloat(userSL) - effectiveEntry) / effectiveEntry) * 100)
      if (oldSlPct > 0) {
        const sign = dir === 'LONG' ? -1 : 1
        const newSl = effectiveEntry * (1 + (sign * oldSlPct) / 100)
        setUserSL(newSl >= 10 ? newSl.toFixed(2) : newSl.toPrecision(4))
      }
    }
  }

  // Live R:R calculator for user form
  const userCalculatedRR = useMemo(() => {
    const entryNum = parseFloat(userEntry) || currentPrice || 0
    const tpNum = parseFloat(userTP)
    const slNum = parseFloat(userSL)
    if (!entryNum || !tpNum || !slNum) return null
    const risk = Math.abs(entryNum - slNum)
    const reward = Math.abs(tpNum - entryNum)
    if (risk <= 0) return null
    return (reward / risk).toFixed(2)
  }, [userEntry, userTP, userSL, currentPrice])

  const loadAll = useCallback(() => {
    fetchForecasts()
      .then((r) => setForecasts(r.forecasts))
      .catch((e) => setError(String((e as Error)?.message ?? e)))
    fetchAnalytics()
      .then(setAnalytics)
      .catch(() => setAnalytics(null))
  }, [])

  useEffect(() => {
    loadAll()
    const t = setInterval(loadAll, 60_000)
    return () => clearInterval(t)
  }, [loadAll])

  // Chạy riêng AI hoặc Local
  const runSingle = async (provider: 'ai' | 'local') => {
    setRunningAction(provider)
    setError(null)
    setScoreMsg(null)
    try {
      const name = provider === 'ai' ? 'ai' : `intraday_lgbm@${symbol}@${timeframe}`
      const r = await runForecast(provider, symbol, timeframe)
      const quality = evaluateForecastQuality(r.signal)
      if (quality.isMarginal) {
        setPendingConfirm({
          id: r.id,
          symbol: r.symbol,
          timeframe: r.timeframe,
          provider: r.provider,
          source: provider === 'ai' ? 'AI' : 'Local',
          signal: r.signal,
          reasons: quality.reasons,
          probPct: quality.probPct,
          priceDeltaPct: quality.priceDeltaPct,
          valid_until: r.valid_until,
        })
        setScoreMsg(`⚠️ Dự báo #${r.id} (${provider === 'ai' ? 'AI' : 'Local'}) cần xác nhận (${quality.reasons.join(' & ')})`)
        loadAll()
        return r
      }
      setScoreMsg(`Dự báo #${r.id} (${provider === 'ai' ? 'AI' : 'Local'}) đã chạy — chốt lúc ${fmtGmt7(r.valid_until)} GMT+7`)
      setCompare((c) => ({ ...(c ?? { symbol, timeframe, results: {} }), results: { ...(c?.results ?? {}), [name]: r.signal } }))
      loadAll()
      return r
    } catch (e) {
      setError(String(e))
      throw e
    } finally {
      setRunningAction(null)
    }
  }

  // Chạy User forecast — LUÔN LƯU & CHẤM ĐIỂM
  const runUser = async () => {
    setRunningAction('user')
    setError(null)
    setScoreMsg(null)
    try {
      const tpList = userTP ? [parseFloat(userTP)] : []
      const resolvedEntry = userEntry ? parseFloat(userEntry) : (currentPrice || null)
      const r = await submitUserForecast({
        symbol,
        timeframe,
        direction: userDirection,
        entry: resolvedEntry,
        take_profit: tpList,
        stop_loss: userSL ? parseFloat(userSL) : null,
        probability: userConfidence / 100,
      })
      setUserSignal(r.signal)
      setScoreMsg(`Dự báo #${r.id} (User) đã lưu — chốt lúc ${fmtGmt7(r.valid_until)} GMT+7`)
      loadAll()
      return r
    } catch (e) {
      setError(String(e))
      throw e
    } finally {
      setRunningAction(null)
    }
  }

  // Chạy tổ hợp AI + Local
  const runComboAiLocal = async () => {
    setRunningAction('combo_ai_local')
    setError(null)
    setScoreMsg(null)
    try {
      const [aiRes, localRes] = await Promise.all([
        runForecast('ai', symbol, timeframe),
        runForecast('local', symbol, timeframe),
      ])
      const aiQuality = evaluateForecastQuality(aiRes.signal)
      const localQuality = evaluateForecastQuality(localRes.signal)
      const nameLocal = `intraday_lgbm@${symbol}@${timeframe}`

      const validResults: Record<string, SignalPayload> = {}
      if (!aiQuality.isMarginal) validResults['ai'] = aiRes.signal
      if (!localQuality.isMarginal) validResults[nameLocal] = localRes.signal

      setCompare((c) => ({
        ...(c ?? { symbol, timeframe, results: {} }),
        results: { ...(c?.results ?? {}), ...validResults },
      }))

      if (aiQuality.isMarginal) {
        setPendingConfirm({
          id: aiRes.id,
          symbol: aiRes.symbol,
          timeframe: aiRes.timeframe,
          provider: aiRes.provider,
          source: 'AI',
          signal: aiRes.signal,
          reasons: aiQuality.reasons,
          probPct: aiQuality.probPct,
          priceDeltaPct: aiQuality.priceDeltaPct,
          valid_until: aiRes.valid_until,
        })
      } else if (localQuality.isMarginal) {
        setPendingConfirm({
          id: localRes.id,
          symbol: localRes.symbol,
          timeframe: localRes.timeframe,
          provider: localRes.provider,
          source: 'Local',
          signal: localRes.signal,
          reasons: localQuality.reasons,
          probPct: localQuality.probPct,
          priceDeltaPct: localQuality.priceDeltaPct,
          valid_until: localRes.valid_until,
        })
      }

      setScoreMsg(`Đã đối chiếu song song AI (#${aiRes.id}) và Local Machine (#${localRes.id}) cho ${symbol} ${timeframe}`)
      loadAll()
    } catch (e) {
      setError(String((e as Error)?.message ?? e))
    } finally {
      setRunningAction(null)
    }
  }

  // Chạy tổ hợp AI + User
  const runComboAiUser = async () => {
    setRunningAction('combo_ai_user')
    setError(null)
    setScoreMsg(null)
    try {
      const tpList = userTP ? [parseFloat(userTP)] : []
      const resolvedEntry = userEntry ? parseFloat(userEntry) : (currentPrice || null)
      const [aiRes, userRes] = await Promise.all([
        runForecast('ai', symbol, timeframe),
        submitUserForecast({
          symbol,
          timeframe,
          direction: userDirection,
          entry: resolvedEntry,
          take_profit: tpList,
          stop_loss: userSL ? parseFloat(userSL) : null,
          probability: userConfidence / 100,
        }),
      ])
      setUserSignal(userRes.signal)

      const aiQuality = evaluateForecastQuality(aiRes.signal)
      if (aiQuality.isMarginal) {
        setPendingConfirm({
          id: aiRes.id,
          symbol: aiRes.symbol,
          timeframe: aiRes.timeframe,
          provider: aiRes.provider,
          source: 'AI',
          signal: aiRes.signal,
          reasons: aiQuality.reasons,
          probPct: aiQuality.probPct,
          priceDeltaPct: aiQuality.priceDeltaPct,
          valid_until: aiRes.valid_until,
        })
      } else {
        setCompare((c) => ({ ...(c ?? { symbol, timeframe, results: {} }), results: { ...(c?.results ?? {}), ai: aiRes.signal } }))
      }

      setScoreMsg(`Đã khởi tạo dự báo User (#${userRes.id}) & AI (#${aiRes.id})!`)
      loadAll()
    } catch (e) {
      setError(String(e))
    } finally {
      setRunningAction(null)
    }
  }

  // Chạy tổ hợp Local + User
  const runComboLocalUser = async () => {
    setRunningAction('combo_local_user')
    setError(null)
    setScoreMsg(null)
    try {
      const name = `intraday_lgbm@${symbol}@${timeframe}`
      const tpList = userTP ? [parseFloat(userTP)] : []
      const resolvedEntry = userEntry ? parseFloat(userEntry) : (currentPrice || null)
      const [localRes, userRes] = await Promise.all([
        runForecast('local', symbol, timeframe),
        submitUserForecast({
          symbol,
          timeframe,
          direction: userDirection,
          entry: resolvedEntry,
          take_profit: tpList,
          stop_loss: userSL ? parseFloat(userSL) : null,
          probability: userConfidence / 100,
        }),
      ])
      setUserSignal(userRes.signal)

      const localQuality = evaluateForecastQuality(localRes.signal)
      if (localQuality.isMarginal) {
        setPendingConfirm({
          id: localRes.id,
          symbol: localRes.symbol,
          timeframe: localRes.timeframe,
          provider: localRes.provider,
          source: 'Local',
          signal: localRes.signal,
          reasons: localQuality.reasons,
          probPct: localQuality.probPct,
          priceDeltaPct: localQuality.priceDeltaPct,
          valid_until: localRes.valid_until,
        })
      } else {
        setCompare((c) => ({ ...(c ?? { symbol, timeframe, results: {} }), results: { ...(c?.results ?? {}), [name]: localRes.signal } }))
      }

      setScoreMsg(`Đã khởi tạo dự báo User (#${userRes.id}) & Local (#${localRes.id})!`)
      loadAll()
    } catch (e) {
      setError(String(e))
    } finally {
      setRunningAction(null)
    }
  }

  // Chạy tổ hợp ALL 3 (Cả 3 cùng lúc)
  const runComboAll = async () => {
    setRunningAction('combo_all')
    setError(null)
    setScoreMsg(null)
    try {
      const name = `intraday_lgbm@${symbol}@${timeframe}`
      const tpList = userTP ? [parseFloat(userTP)] : []
      const resolvedEntry = userEntry ? parseFloat(userEntry) : (currentPrice || null)
      const [aiRes, localRes, userRes] = await Promise.all([
        runForecast('ai', symbol, timeframe),
        runForecast('local', symbol, timeframe),
        submitUserForecast({
          symbol,
          timeframe,
          direction: userDirection,
          entry: resolvedEntry,
          take_profit: tpList,
          stop_loss: userSL ? parseFloat(userSL) : null,
          probability: userConfidence / 100,
        }),
      ])
      setUserSignal(userRes.signal)

      const aiQuality = evaluateForecastQuality(aiRes.signal)
      const localQuality = evaluateForecastQuality(localRes.signal)

      const validResults: Record<string, SignalPayload> = {}
      if (!aiQuality.isMarginal) validResults['ai'] = aiRes.signal
      if (!localQuality.isMarginal) validResults[name] = localRes.signal

      setCompare((c) => ({
        ...(c ?? { symbol, timeframe, results: {} }),
        results: { ...(c?.results ?? {}), ...validResults },
      }))

      if (aiQuality.isMarginal) {
        setPendingConfirm({
          id: aiRes.id,
          symbol: aiRes.symbol,
          timeframe: aiRes.timeframe,
          provider: aiRes.provider,
          source: 'AI',
          signal: aiRes.signal,
          reasons: aiQuality.reasons,
          probPct: aiQuality.probPct,
          priceDeltaPct: aiQuality.priceDeltaPct,
          valid_until: aiRes.valid_until,
        })
      } else if (localQuality.isMarginal) {
        setPendingConfirm({
          id: localRes.id,
          symbol: localRes.symbol,
          timeframe: localRes.timeframe,
          provider: localRes.provider,
          source: 'Local',
          signal: localRes.signal,
          reasons: localQuality.reasons,
          probPct: localQuality.probPct,
          priceDeltaPct: localQuality.priceDeltaPct,
          valid_until: localRes.valid_until,
        })
      }

      setScoreMsg(`🔥 ĐẠI CHIẾN TAM MÃ: Đã khởi tạo User (#${userRes.id}), AI (#${aiRes.id}) và Local (#${localRes.id})!`)
      loadAll()
    } catch (e) {
      setError(String(e))
    } finally {
      setRunningAction(null)
    }
  }

  const onScore = async (id: number) => {
    try {
      const r = await scoreForecast(id)
      if (r.scored) {
        const scoreStr = r.score != null ? `${r.score > 0 ? '+' : ''}${r.score}%` : ''
        setScoreMsg(`Dự báo #${id}: ${scoreStr} so với TP (${r.outcome}) — giá chốt ${fmtPrice(r.exit_price)}`)
      } else {
        setScoreMsg(r.message ?? `#${id} chưa chốt`)
      }
      loadAll()
    } catch (e) {
      setError(String(e))
    }
  }

  const onScoreAll = async () => {
    setRunningAction('score_all')
    setError(null)
    try {
      const r = await scoreAllExpired()
      setScoreMsg(`Đã chấm ${r.scored} dự báo quá hạn, bỏ qua ${r.skipped} chưa tới hạn`)
      loadAll()
    } catch (e) {
      setError(String(e))
    } finally {
      setRunningAction(null)
    }
  }

  const onRetrain = async () => {
    setRetraining(true)
    setRetrainMsg(null)
    try {
      const r = await retrainModel(symbol, timeframe)
      setRetrainMsg(r.message)
    } catch (e) {
      setError(String(e))
    } finally {
      setRetraining(false)
    }
  }

  const onDelete = async (id: number) => {
    try {
      await deleteForecast(id)
      setForecasts((prev) => prev.filter((f) => f.id !== id))
      loadAll()
    } catch (e) {
      setError(String(e))
    }
  }

  const ai = compare?.results['ai']
  const offline = compare?.results[`intraday_lgbm@${symbol}@${timeframe}`]

  const expiredUnscores = useMemo(
    () => forecasts.filter((f) => f.expired && !f.scored),
    [forecasts],
  )

  return (
    <div className="space-y-6">
      {/* 1. Header Toolbar (Symbol, Timeframe, Utility Actions) */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-2xl surface-card border border-[var(--color-border)]">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Cặp:</span>
            <select
              aria-label="Forecast symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl px-3 py-1.5 text-xs font-bold text-cyan-300 focus:outline-none focus:border-cyan-500 cursor-pointer shadow-inner"
            >
              {SYMBOLS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Khung:</span>
            <div role="group" aria-label="Forecast timeframe" className="flex items-center p-0.5 rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)]">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-mono font-medium transition ${
                    tf === timeframe
                      ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm shadow-cyan-500/20'
                      : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-main)] hover:bg-[var(--color-surface-2)]'
                  }`}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Chấm tất cả & Export CSV */}
        <div className="flex items-center gap-2">
          <button
            onClick={onScoreAll}
            disabled={isBusy}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 text-xs font-semibold border border-rose-500/30 transition disabled:opacity-50 shadow-sm"
            title="Chấm tất cả dự báo quá hạn chưa đối chiếu"
          >
            <FileCheck2 className={`w-3.5 h-3.5 ${runningAction === 'score_all' ? 'animate-spin' : ''}`} />
            {runningAction === 'score_all' ? 'Đang chấm…' : `Chấm tất cả (${expiredUnscores.length})`}
          </button>
          <button
            onClick={() => exportForecastsCsv(symbol, timeframe)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[var(--color-surface-2)] border border-[var(--color-border)] text-[var(--color-text-main)] text-xs font-semibold hover:bg-slate-700 transition shadow-sm"
          >
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </button>
        </div>
      </div>

      {/* 2. Three Main Control Pods (Option 1: Command Deck Cards) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* POD 1: AI ORACLE */}
        <div className="relative flex flex-col justify-between p-5 rounded-2xl border border-violet-500/30 bg-gradient-to-b from-violet-950/30 via-slate-900/80 to-slate-950/90 shadow-xl shadow-violet-950/20 backdrop-blur-sm">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-violet-500/20 text-violet-300 border border-violet-500/30 shadow-inner">
                  <Brain className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-[var(--color-text-main)] flex items-center gap-1.5">
                    AI Oracle
                    <Sparkles className="w-3.5 h-3.5 text-violet-400" />
                  </h3>
                  <span className="text-[11px] text-violet-300/80 font-mono">DeepSeek LLM</span>
                </div>
              </div>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-violet-500/10 text-violet-300 border border-violet-500/20">
                Cloud AI
              </span>
            </div>
            <p className="text-xs text-[var(--color-text-muted)] leading-relaxed mb-4">
              Phân tích đa chiều mẫu hình nến, cấu trúc thị trường, kháng cự / hỗ trợ và sentiment qua mô hình ngôn ngữ lớn.
            </p>
          </div>

          <button
            onClick={() => runSingle('ai')}
            disabled={isBusy}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 via-purple-600 to-indigo-600 text-white text-xs font-bold shadow-lg shadow-violet-500/25 hover:opacity-95 active:scale-[0.98] disabled:opacity-50 transition cursor-pointer"
          >
            <Brain className={`w-4 h-4 ${runningAction === 'ai' ? 'animate-bounce' : ''}`} />
            {runningAction === 'ai' ? 'Running…' : 'Forecast AI'}
          </button>
        </div>

        {/* POD 2: LOCAL MACHINE */}
        <div className="relative flex flex-col justify-between p-5 rounded-2xl border border-sky-500/30 bg-gradient-to-b from-sky-950/30 via-slate-900/80 to-slate-950/90 shadow-xl shadow-sky-950/20 backdrop-blur-sm">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-sky-500/20 text-sky-300 border border-sky-500/30 shadow-inner">
                  <Cpu className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-[var(--color-text-main)] flex items-center gap-1.5">
                    Local Machine
                    <Zap className="w-3.5 h-3.5 text-sky-400" />
                  </h3>
                  <span className="text-[11px] text-sky-300/80 font-mono">LightGBM Intraday</span>
                </div>
              </div>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-sky-500/10 text-sky-300 border border-sky-500/20">
                Offline ML
              </span>
            </div>
            <p className="text-xs text-[var(--color-text-muted)] leading-relaxed mb-4">
              Mô hình học máy định lượng cục bộ, tối ưu hóa tốc độ tính toán, chi phí 0 token và liên tục học lại từ outcomes.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => runSingle('local')}
              disabled={isBusy}
              className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-sky-600 via-cyan-600 to-teal-600 text-white text-xs font-bold shadow-lg shadow-sky-500/25 hover:opacity-95 active:scale-[0.98] disabled:opacity-50 transition cursor-pointer"
            >
              <Cpu className={`w-4 h-4 ${runningAction === 'local' ? 'animate-pulse' : ''}`} />
              {runningAction === 'local' ? 'Running…' : 'Forecast Local'}
            </button>
            <button
              onClick={onRetrain}
              disabled={isBusy}
              title="Retrain offline model từ outcomes"
              className="inline-flex items-center justify-center p-2.5 rounded-xl bg-[var(--color-surface-2)] border border-[var(--color-border)] text-[var(--color-text-main)] hover:text-white hover:bg-slate-700 disabled:opacity-50 transition"
            >
              <RotateCcw className={`w-4 h-4 ${retraining ? 'animate-spin text-cyan-400' : ''}`} />
            </button>
          </div>
        </div>

        {/* POD 3: USER PREDICTION (CÁ NHÂN DỰ ĐOÁN) */}
        <div className="relative flex flex-col justify-between p-5 rounded-2xl border border-amber-500/30 bg-gradient-to-b from-amber-950/30 via-slate-900/80 to-slate-950/90 shadow-xl shadow-amber-950/20 backdrop-blur-sm">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-amber-500/20 text-amber-300 border border-amber-500/30 shadow-inner">
                  <UserCheck className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-[var(--color-text-main)] flex items-center gap-1.5">
                    User Prediction
                    <Target className="w-3.5 h-3.5 text-amber-400" />
                  </h3>
                  <span className="text-[11px] text-amber-300/80 font-mono">Nhận định cá nhân</span>
                </div>
              </div>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-300 border border-amber-500/20">
                Human Trader
              </span>
            </div>

            {/* Direction toggle */}
            <div className="grid grid-cols-2 gap-2 mb-3">
              <button
                type="button"
                onClick={() => toggleDirection('LONG')}
                className={`py-1.5 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition cursor-pointer ${
                  userDirection === 'LONG'
                    ? 'bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/30 border border-emerald-400'
                    : 'bg-[var(--color-surface-2)] text-[var(--color-text-muted)] border border-[var(--color-border)]/60 hover:text-[var(--color-text-main)]'
                }`}
              >
                <TrendingUp className="w-3.5 h-3.5" />
                <span>LONG ↗</span>
              </button>
              <button
                type="button"
                onClick={() => toggleDirection('SHORT')}
                className={`py-1.5 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition cursor-pointer ${
                  userDirection === 'SHORT'
                    ? 'bg-rose-500 text-white shadow-md shadow-rose-500/30 border border-rose-400'
                    : 'bg-[var(--color-surface-2)] text-[var(--color-text-muted)] border border-[var(--color-border)]/60 hover:text-[var(--color-text-main)]'
                }`}
              >
                <TrendingDown className="w-3.5 h-3.5" />
                <span>SHORT ↘</span>
              </button>
            </div>

            {/* Inputs: Entry, TP, SL with dynamic % badges and quick offset chips */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 mb-3">
              {/* Entry */}
              <div className="flex flex-col justify-between">
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[10px] font-semibold text-[var(--color-text-main)]">Entry ($)</label>
                  {currentPrice !== null && (
                    <button
                      type="button"
                      onClick={() => setUserEntry(String(currentPrice))}
                      className="text-[9px] font-mono text-cyan-400 hover:text-cyan-300 transition flex items-center gap-0.5 underline cursor-pointer"
                      title="Gán giá live hiện tại vào ô Entry"
                    >
                      ⚡ Live: ${fmtPrice(currentPrice)}
                    </button>
                  )}
                </div>
                <input
                  type="number"
                  placeholder={currentPrice ? `${currentPrice}` : "Giá hiện tại"}
                  value={userEntry}
                  onChange={(e) => setUserEntry(e.target.value)}
                  className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded-lg px-2.5 py-1.5 text-xs font-mono text-[var(--color-text-main)] placeholder:text-[var(--color-text-subtle)] focus:outline-none focus:border-amber-500 shadow-inner"
                />
                <span className="text-[9px] text-[var(--color-text-subtle)] mt-1 font-mono">
                  {userEntry ? `Entry thủ công` : (currentPrice ? `Tự lấy $${fmtPrice(currentPrice)}` : `Đang kết nối live...`)}
                </span>
              </div>

              {/* TP Mục tiêu */}
              <div className="flex flex-col justify-between">
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[10px] font-semibold text-emerald-400">TP Mục tiêu ($)</label>
                  {tpPct !== null && (
                    <span className={`text-[10px] font-mono font-bold ${tpPct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {tpPct >= 0 ? `+${tpPct.toFixed(1)}%` : `${tpPct.toFixed(1)}%`}
                    </span>
                  )}
                </div>
                <input
                  type="number"
                  placeholder="Take Profit"
                  value={userTP}
                  onChange={(e) => setUserTP(e.target.value)}
                  className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded-lg px-2.5 py-1.5 text-xs font-mono text-emerald-300 placeholder:text-[var(--color-text-subtle)] focus:outline-none focus:border-emerald-500 shadow-inner"
                />
                {/* Quick % chips for TP */}
                <div className="flex items-center gap-1 mt-1">
                  {[1.5, 3, 5, 8].map((pct) => (
                    <button
                      key={pct}
                      type="button"
                      onClick={() => applyTpPct(pct)}
                      className="flex-1 py-0.5 rounded text-[9px] font-mono font-semibold bg-emerald-500/10 hover:bg-emerald-500/25 text-emerald-300 border border-emerald-500/20 transition cursor-pointer text-center"
                      title={`Đặt TP ${userDirection === 'LONG' ? `+${pct}%` : `-${pct}%`} từ Entry`}
                    >
                      {userDirection === 'LONG' ? `+${pct}%` : `-${pct}%`}
                    </button>
                  ))}
                </div>
              </div>

              {/* SL Dừng lỗ */}
              <div className="flex flex-col justify-between">
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[10px] font-semibold text-rose-400">SL Dừng lỗ ($)</label>
                  {slPct !== null && (
                    <span className={`text-[10px] font-mono font-bold ${slPct <= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                      {slPct >= 0 ? `+${slPct.toFixed(1)}%` : `${slPct.toFixed(1)}%`}
                    </span>
                  )}
                </div>
                <input
                  type="number"
                  placeholder="Stop Loss"
                  value={userSL}
                  onChange={(e) => setUserSL(e.target.value)}
                  className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded-lg px-2.5 py-1.5 text-xs font-mono text-rose-300 placeholder:text-[var(--color-text-subtle)] focus:outline-none focus:border-rose-500 shadow-inner"
                />
                {/* Quick % chips for SL */}
                <div className="flex items-center gap-1 mt-1">
                  {[1, 2, 3, 5].map((pct) => (
                    <button
                      key={pct}
                      type="button"
                      onClick={() => applySlPct(pct)}
                      className="flex-1 py-0.5 rounded text-[9px] font-mono font-semibold bg-rose-500/10 hover:bg-rose-500/25 text-rose-300 border border-rose-500/20 transition cursor-pointer text-center"
                      title={`Đặt SL ${userDirection === 'LONG' ? `-${pct}%` : `+${pct}%`} từ Entry`}
                    >
                      {userDirection === 'LONG' ? `-${pct}%` : `+${pct}%`}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* R:R & Confidence indicators */}
            <div className="flex items-center justify-between text-[11px] font-mono text-[var(--color-text-muted)] mb-3 px-1">
              <span>
                R:R: <b className="text-amber-300">{userCalculatedRR ? `1 : ${userCalculatedRR}` : '—'}</b>
              </span>
              <div className="flex items-center gap-1">
                <span>Tự tin:</span>
                <select
                  value={userConfidence}
                  onChange={(e) => setUserConfidence(Number(e.target.value))}
                  className="bg-[var(--color-surface-2)] border border-[var(--color-border)] text-amber-300 text-[11px] rounded px-1.5 py-0.5 focus:outline-none"
                >
                  <option value={90}>90%</option>
                  <option value={80}>80%</option>
                  <option value={70}>70%</option>
                  <option value={60}>60%</option>
                </select>
              </div>
            </div>
          </div>

          <button
            onClick={runUser}
            disabled={isBusy}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-amber-600 via-orange-600 to-amber-700 text-white text-xs font-bold shadow-lg shadow-amber-600/25 hover:opacity-95 active:scale-[0.98] disabled:opacity-50 transition cursor-pointer"
          >
            <Target className={`w-4 h-4 ${runningAction === 'user' ? 'animate-spin' : ''}`} />
            {runningAction === 'user' ? 'Saving…' : 'Lưu Dự Đoán User'}
          </button>
        </div>
      </div>

      {/* 3. Combination Triggers Dock (🚀 Thanh Tổ Hợp Nhanh / Đấu Trí) */}
      <div className="p-4 rounded-2xl bg-[var(--color-surface-2)] border border-[var(--color-border)] shadow-2xl backdrop-blur-md flex flex-col md:flex-row items-center justify-between gap-3.5">
        <div className="flex items-center gap-2.5 text-xs font-bold uppercase tracking-wider text-[var(--color-text-main)]">
          <span className="p-1.5 rounded-lg bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
            <Zap className="w-4 h-4" />
          </span>
          <div>
            <span className="text-[var(--color-text-main)]">Đấu Trí Tổ Hợp & So Tài Đa Nguồn</span>
            <div className="text-[10px] text-[var(--color-text-subtle)] normal-case font-normal">
              Chạy song song 2 hoặc cả 3 phương án dự báo cùng một lúc
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5 w-full md:w-auto">
          {/* AI + User */}
          <button
            onClick={runComboAiUser}
            disabled={isBusy}
            className="flex-1 md:flex-none inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-xl bg-gradient-to-r from-violet-600 to-amber-600 text-white text-xs font-semibold shadow-md shadow-violet-500/20 hover:opacity-90 disabled:opacity-50 transition cursor-pointer"
          >
            <Brain className="w-3.5 h-3.5 text-violet-200" />
            <span>+</span>
            <UserCheck className="w-3.5 h-3.5 text-amber-200" />
            <span>{runningAction === 'combo_ai_user' ? 'Running…' : 'AI + User'}</span>
          </button>

          {/* AI + Local */}
          <button
            onClick={runComboAiLocal}
            disabled={isBusy}
            className="flex-1 md:flex-none inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-xl bg-gradient-to-r from-violet-600 to-sky-600 text-white text-xs font-semibold shadow-md shadow-sky-500/20 hover:opacity-90 disabled:opacity-50 transition cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${runningAction === 'combo_ai_local' ? 'animate-spin' : ''}`} />
            <span>{runningAction === 'combo_ai_local' ? 'Comparing…' : 'AI + Local (Run AI vs Offline)'}</span>
          </button>

          {/* Local + User */}
          <button
            onClick={runComboLocalUser}
            disabled={isBusy}
            className="flex-1 md:flex-none inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-xl bg-gradient-to-r from-sky-600 to-amber-600 text-white text-xs font-semibold shadow-md shadow-amber-500/20 hover:opacity-90 disabled:opacity-50 transition cursor-pointer"
          >
            <Cpu className="w-3.5 h-3.5 text-sky-200" />
            <span>+</span>
            <UserCheck className="w-3.5 h-3.5 text-amber-200" />
            <span>{runningAction === 'combo_local_user' ? 'Running…' : 'Local + User'}</span>
          </button>

          {/* ALL 3 (CẢ 3 CÙNG LÚC) */}
          <button
            onClick={runComboAll}
            disabled={isBusy}
            className="flex-1 md:flex-none inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-violet-600 via-sky-500 to-amber-500 text-slate-950 text-xs font-extrabold shadow-lg shadow-amber-500/20 ring-1 ring-amber-400/50 hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 transition cursor-pointer"
          >
            <Flame className={`w-4 h-4 text-amber-950 ${runningAction === 'combo_all' ? 'animate-bounce' : ''}`} />
            <span>{runningAction === 'combo_all' ? 'Executing All 3…' : '🔥 Cả 3 Cùng Lúc (All 3)'}</span>
          </button>
        </div>
      </div>

      {/* Alert / Notification bar */}
      {(error || scoreMsg || retrainMsg) && (
        <div
          role="alert"
          className={`flex items-center gap-2.5 p-3.5 rounded-xl text-xs shadow-lg ${
            error
              ? 'bg-rose-950/50 border border-rose-800/80 text-rose-300'
              : 'bg-emerald-950/50 border border-emerald-800/80 text-emerald-300'
          }`}
        >
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error ?? scoreMsg ?? retrainMsg}</span>
        </div>
      )}

      {/* Analytics Cards */}
      {analytics && <AnalyticsCards data={analytics} />}

      {/* 4. 3-Way Comparison Arena (Signal Cards 3 Cột) */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-muted)] flex items-center gap-1.5">
            <Target className="w-4 h-4 text-cyan-400" />
            Lưới So Sánh 3 Cột Trực Diện ({symbol} · {timeframe})
          </h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <SignalCard
            title="AI Forecast (DeepSeek)"
            badgeText="Cloud LLM"
            badgeClass="bg-violet-500/20 text-violet-300 border-violet-500/40"
            icon={<Brain className="w-4 h-4 text-violet-400" />}
            signal={'error' in (ai ?? {}) ? undefined : (ai as SignalPayload)}
            error={'error' in (ai ?? {}) ? (ai as { error: string }).error : undefined}
          />
          <SignalCard
            title="Offline Model (LightGBM)"
            badgeText="Local ML"
            badgeClass="bg-sky-500/20 text-sky-300 border-sky-500/40"
            icon={<Cpu className="w-4 h-4 text-sky-400" />}
            signal={'error' in (offline ?? {}) ? undefined : (offline as SignalPayload)}
            error={'error' in (offline ?? {}) ? (offline as { error: string }).error : undefined}
          />
          <SignalCard
            title="User Prediction (Cá nhân)"
            badgeText="Human"
            badgeClass="bg-amber-500/20 text-amber-300 border-amber-500/40"
            icon={<UserCheck className="w-4 h-4 text-amber-400" />}
            signal={userSignal ?? undefined}
          />
        </div>
      </section>

      {/* 5. Forecast Table / Matrix */}
      <section className="rounded-2xl overflow-hidden surface-card border border-[var(--color-border)] shadow-xl">
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)] bg-[var(--color-surface)]/70">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-[var(--color-text-main)] uppercase tracking-wide">
              Lịch Sử & Bảng Đối Chiếu Dự Báo
            </h3>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2 text-[11px] text-[var(--color-text-muted)]">
              <span className="inline-flex items-center gap-1 font-mono text-violet-300">
                <span className="w-2 h-2 rounded-full bg-violet-400"></span> AI
              </span>
              <span className="inline-flex items-center gap-1 font-mono text-sky-300">
                <span className="w-2 h-2 rounded-full bg-sky-400"></span> Local
              </span>
              <span className="inline-flex items-center gap-1 font-mono text-amber-300">
                <span className="w-2 h-2 rounded-full bg-amber-400"></span> User
              </span>
            </div>
            <span className="text-xs text-[var(--color-text-muted)] font-mono bg-[var(--color-surface-2)] px-2 py-0.5 rounded-md border border-[var(--color-border)]">
              {forecasts.length} bản ghi
            </span>
          </div>
        </div>

        {forecasts.length === 0 ? (
          <div className="py-12 text-center text-[var(--color-text-subtle)] text-sm">
            Chưa có dự báo nào — chọn <b>Forecast AI</b>, <b>Forecast Local</b> hoặc nhập <b>User Prediction</b> để bắt đầu.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-[var(--color-surface-2)] text-left text-[var(--color-text-muted)] uppercase tracking-wider border-b border-[var(--color-border)] font-medium">
                  <th className="py-3 px-4">#</th>
                  <th className="py-3 px-4">Nguồn</th>
                  <th className="py-3 px-4">Dir</th>
                  <th className="py-3 px-4 text-right">Entry</th>
                  <th className="py-3 px-4 text-right">TP</th>
                  <th className="py-3 px-4 text-right">Giá chốt</th>
                  <th className="py-3 px-4">Bắt đầu (GMT+7)</th>
                  <th className="py-3 px-4">Chốt (GMT+7)</th>
                  <th className="py-3 px-4 text-right">Countdown</th>
                  <th className="py-3 px-4">Đối chiếu</th>
                  <th className="py-3 px-4 text-right">Hành động</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono tabular-nums">
                {forecasts.map((f) => {
                  const overdue = f.expired && !f.scored
                  const sourceBorderClass =
                    f.source === 'AI'
                      ? 'border-l-2 border-l-violet-500/70 hover:bg-violet-950/15'
                      : f.source === 'User'
                        ? 'border-l-2 border-l-amber-500/70 hover:bg-amber-950/15'
                        : 'border-l-2 border-l-sky-500/70 hover:bg-sky-950/15'

                  const rowClass = overdue
                    ? 'bg-rose-950/30 border-l-4 border-l-rose-500'
                    : sourceBorderClass

                  return (
                    <tr key={f.id} className={`transition-colors ${rowClass}`}>
                      <td className="py-3 px-4 font-sans">
                        <span className="font-bold text-[var(--color-text-main)]">#{f.id}</span>
                        {overdue && (
                          <span className="ml-1.5 px-1.5 py-0.5 rounded bg-rose-600/30 text-rose-300 text-[10px] font-bold border border-rose-500/40 animate-pulse">
                            QUÁ HẠN
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 font-sans">
                        <SourceBadge source={f.source} />
                      </td>
                      <td className="py-3 px-4 font-sans">
                        <DirectionBadge dir={f.direction} />
                      </td>
                      <td className="py-3 px-4 text-right text-[var(--color-text-main)]">{fmtPrice(f.entry)}</td>
                      <td className="py-3 px-4 text-right font-mono text-emerald-400">
                        {f.take_profit && f.take_profit.length > 0 ? f.take_profit.map(fmtPrice).join(' / ') : '—'}
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-cyan-300">
                        {fmtPrice(f.exit_price ?? f.outcome?.exit_price)}
                      </td>
                      <td className="py-3 px-4 text-[var(--color-text-muted)] text-[11px]">{fmtGmt7(f.created_at)}</td>
                      <td className="py-3 px-4 text-[var(--color-text-main)] text-[11px]">{fmtGmt7(f.valid_until)}</td>
                      <td className="py-3 px-4 text-right">
                        <Countdown validUntil={f.valid_until} />
                      </td>
                      <td className="py-3 px-4 font-sans">
                        {f.scored && f.outcome ? (
                          <OutcomeScoreBadge direction={f.direction} outcome={f.outcome} />
                        ) : (
                          <span
                            className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${
                              overdue
                                ? 'bg-rose-600/30 text-rose-300 border border-rose-500/40'
                                : 'bg-[var(--color-surface-2)] text-[var(--color-text-muted)]'
                            }`}
                          >
                            {overdue ? 'Chưa đối chiếu' : 'Chờ chốt'}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right font-sans">
                        <div className="flex items-center justify-end gap-1.5">
                          {!f.scored && f.expired && (f.direction === 'LONG' || f.direction === 'SHORT') ? (
                            <button
                              onClick={() => onScore(f.id)}
                              className="px-2.5 py-1 rounded bg-rose-600/20 hover:bg-rose-600/40 text-rose-300 text-[11px] font-semibold border border-rose-500/30 transition shadow-sm"
                            >
                              Đối chiếu & chấm
                            </button>
                          ) : (
                            <span className="text-slate-600 text-[11px]">—</span>
                          )}
                          <button
                            onClick={() => onDelete(f.id)}
                            className="p-1 rounded text-[var(--color-text-subtle)] hover:text-rose-400 hover:bg-rose-500/10 transition"
                            title={`Xóa dự báo #${f.id}`}
                            aria-label={`Xóa dự báo #${f.id}`}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Dialog Xác Nhận Khi Dự Báo Có Độ Tin Cậy < 60% hoặc Độ Lệch Giá < 1% */}
      {pendingConfirm && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Cảnh báo chất lượng dự báo"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[var(--color-surface-2)]/80 backdrop-blur-sm animate-in fade-in duration-200"
        >
          <div className="max-w-md w-full p-6 rounded-2xl bg-[var(--color-surface)] border border-amber-500/40 shadow-2xl shadow-amber-950/50 space-y-4">
            <div className="flex items-start gap-3">
              <div className="p-2.5 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30 shrink-0">
                <AlertCircle className="w-6 h-6" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-[var(--color-text-main)]">Cảnh Báo Chất Lượng Dự Báo</h3>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    pendingConfirm.source === 'AI' ? 'bg-violet-500/20 text-violet-300 border border-violet-500/30' : 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                  }`}>
                    Nguồn: {pendingConfirm.source}
                  </span>
                </div>
                <p className="text-xs text-[var(--color-text-muted)] mt-1 leading-relaxed">
                  Dự báo #{pendingConfirm.id} từ <b>{pendingConfirm.source}</b> không đạt chuẩn chất lượng khuyến nghị (độ tin cậy &ge; 60% hoặc biên độ giá &ge; 1%).
                </p>
              </div>
            </div>

            {/* Lý do cảnh báo */}
            <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-500/30 space-y-1.5">
              <span className="text-[11px] font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1">
                ⚠️ Lý do cảnh báo:
              </span>
              <ul className="text-xs text-amber-200/90 list-disc list-inside space-y-1">
                {pendingConfirm.reasons.map((r, i) => (
                  <li key={i} className="font-medium">{r}</li>
                ))}
              </ul>
            </div>

            {/* Chi tiết tín hiệu */}
            <div className="p-3 rounded-xl bg-[var(--color-surface-2)]/80 border border-[var(--color-border)] text-xs font-mono grid grid-cols-2 gap-2">
              <div>
                <span className="text-[var(--color-text-subtle)] block text-[10px]">Cặp & Khung:</span>
                <b className="text-cyan-300">{pendingConfirm.symbol} {pendingConfirm.timeframe}</b>
              </div>
              <div>
                <span className="text-[var(--color-text-subtle)] block text-[10px]">Hướng dự báo:</span>
                <b className={pendingConfirm.signal.direction === 'LONG' ? 'text-emerald-400' : 'text-rose-400'}>
                  {pendingConfirm.signal.direction}
                </b>
              </div>
              <div>
                <span className="text-[var(--color-text-subtle)] block text-[10px]">Độ tin cậy:</span>
                <b className="text-amber-300">{pendingConfirm.probPct.toFixed(1)}%</b>
              </div>
              <div>
                <span className="text-[var(--color-text-subtle)] block text-[10px]">Biên độ mục tiêu:</span>
                <b className="text-amber-300">{pendingConfirm.priceDeltaPct.toFixed(2)}%</b>
              </div>
              <div>
                <span className="text-[var(--color-text-subtle)] block text-[10px]">Entry:</span>
                <span className="text-[var(--color-text-main)]">${fmtPrice(pendingConfirm.signal.entry)}</span>
              </div>
              <div>
                <span className="text-[var(--color-text-subtle)] block text-[10px]">TP:</span>
                <span className="text-emerald-300">${fmtPrice(pendingConfirm.signal.take_profit?.[0])}</span>
              </div>
            </div>

            <p className="text-xs text-[var(--color-text-main)] font-medium">
              Bạn có muốn tiếp tục lưu và hiển thị dự báo này ra bảng theo dõi không?
            </p>

            {/* Action buttons */}
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => handleDiscardPending(pendingConfirm)}
                className="px-3.5 py-2 rounded-xl bg-[var(--color-surface-2)] hover:bg-slate-700 text-[var(--color-text-main)] hover:text-white text-xs font-semibold border border-[var(--color-border)] transition cursor-pointer"
              >
                ❌ Bỏ qua & Không lưu
              </button>
              <button
                type="button"
                onClick={() => handleProceedPending(pendingConfirm)}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-amber-600 to-orange-600 hover:opacity-95 text-white text-xs font-bold shadow-lg shadow-amber-600/30 transition cursor-pointer"
              >
                ✅ Vẫn tiếp tục lưu & hiển thị
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ForecastCompare

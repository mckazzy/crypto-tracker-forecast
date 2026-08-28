import { useEffect, useState } from 'react'
import { Bot, Sparkles } from 'lucide-react'
import { fetchAiModels, type AiModelsResponse } from '../lib/ai'

function ModelPicker() {
  const [data, setData] = useState<AiModelsResponse | null>(null)
  const [selected, setSelected] = useState<string>('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchAiModels()
      .then((d) => {
        setData(d)
        setSelected(d.default_model ?? (d.models[0] ?? ''))
        setError(null)
      })
      .catch((e) => setError(String(e.message ?? e)))
  }, [])

  if (!data) {
    return (
      <div className="flex items-center gap-2 text-[var(--color-text-muted)] text-xs px-3 py-1.5 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] shadow-sm" data-testid="model-picker-loading">
        <Bot className="w-4 h-4 animate-pulse text-[var(--color-primary)]" />
        <span>{error ? `AI models unavailable: ${error}` : 'Loading models…'}</span>
      </div>
    )
  }

  return (
    <label className="flex items-center gap-2 text-xs" data-testid="model-picker">
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] shadow-sm">
        <Sparkles className="w-3.5 h-3.5 text-[var(--color-primary)]" />
        <span className="text-[var(--color-text-muted)] font-medium">Model:</span>
        <select
          aria-label="AI model"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          className="bg-transparent text-[var(--color-text-main)] font-mono text-xs focus:outline-none focus:text-[var(--color-primary)] cursor-pointer max-w-[240px] truncate"
        >
          {data.models.length === 0 && <option value="" className="bg-[var(--color-surface)] text-[var(--color-text-muted)]">No models</option>}
          {data.models.map((m) => (
            <option key={m} value={m} className="bg-[var(--color-surface)] text-[var(--color-text-main)]">
              {m}
            </option>
          ))}
        </select>
      </div>
    </label>
  )
}

export default ModelPicker

import { useEffect, useState } from 'react'
import { LogIn, UserPlus, X } from 'lucide-react'
import { login, register, setToken } from '../../lib/futures'

interface AuthModalProps {
  open: boolean
  onClose: () => void
  onAuthed: (token: string) => void
}

export function AuthModal({ open, onClose, onAuthed }: AuthModalProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open) {
      setError(null)
      setMode('login')
    }
  }, [open])

  if (!open) return null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const token = mode === 'login' ? await login(username, password) : await register(username, password)
      setToken(token)
      onAuthed(token)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-sm surface-card p-6 relative">
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute top-3 right-3 p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-2)] transition"
        >
          <X className="w-4 h-4" />
        </button>
        <div className="flex items-center gap-2 mb-4">
          {mode === 'login' ? (
            <LogIn className="w-4 h-4 text-[var(--color-primary)]" />
          ) : (
            <UserPlus className="w-4 h-4 text-[var(--color-primary)]" />
          )}
          <h2 className="text-sm font-bold text-[var(--color-text-main)] uppercase tracking-wide">
            {mode === 'login' ? 'Sign In' : 'Create Account'}
          </h2>
        </div>

        <form onSubmit={submit} className="space-y-3" data-testid="auth-form">
          <div>
            <label className="block text-[11px] font-semibold text-[var(--color-text-muted)] mb-1">
              Username
            </label>
            <input
              data-testid="auth-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-xs text-[var(--color-text-main)] focus:outline-none focus:border-[var(--color-primary)]"
              placeholder="username"
              required
              minLength={1}
              maxLength={64}
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-[var(--color-text-muted)] mb-1">
              Password
            </label>
            <input
              data-testid="auth-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-xs text-[var(--color-text-main)] focus:outline-none focus:border-[var(--color-primary)]"
              placeholder={mode === 'register' ? 'min 8 characters' : 'password'}
              required
              minLength={mode === 'register' ? 8 : 1}
              maxLength={64}
            />
          </div>

          {error && (
            <div role="alert" className="text-xs text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={busy}
            data-testid="auth-submit"
            className="w-full py-2 rounded-lg bg-[var(--color-primary)] text-white text-xs font-bold hover:opacity-90 disabled:opacity-50 transition"
          >
            {busy ? 'Please wait…' : mode === 'login' ? 'Sign In' : 'Create Account'}
          </button>
        </form>

        <button
          onClick={() => setMode((m) => (m === 'login' ? 'register' : 'login'))}
          className="mt-3 w-full text-center text-[11px] text-[var(--color-text-muted)] hover:text-[var(--color-primary)] transition"
        >
          {mode === 'login' ? 'No account? Create one' : 'Already registered? Sign in'}
        </button>
      </div>
    </div>
  )
}

export default AuthModal

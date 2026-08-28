import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AuthModal from '../components/futures/AuthModal'

vi.mock('../lib/futures', () => ({
  login: vi.fn(async () => 'token-login'),
  register: vi.fn(async () => 'token-register'),
  setToken: vi.fn(),
}))

function renderModal(props = {}) {
  return render(
    <AuthModal open onClose={() => {}} onAuthed={() => {}} {...props} />,
  )
}

describe('AuthModal', () => {
  it('renders login form by default', () => {
    renderModal()
    expect(screen.getByTestId('auth-form')).toBeInTheDocument()
    expect(screen.getByTestId('auth-submit')).toHaveTextContent('Sign In')
  })

  it('submits login and saves token', async () => {
    const { login } = await import('../lib/futures')
    const onAuthed = vi.fn()
    renderModal({ onAuthed })
    fireEvent.change(screen.getByTestId('auth-username'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByTestId('auth-password'), { target: { value: 'password123' } })
    fireEvent.click(screen.getByTestId('auth-submit'))
    await waitFor(() => expect(login).toHaveBeenCalledWith('alice', 'password123'))
    await waitFor(() => expect(onAuthed).toHaveBeenCalledWith('token-login'))
  })

  it('switches to register mode', async () => {
    renderModal()
    fireEvent.click(screen.getByText(/create one/i))
    await waitFor(() => expect(screen.getByTestId('auth-submit')).toHaveTextContent('Create Account'))
  })

  it('shows error on failed login', async () => {
    const { login } = await import('../lib/futures')
    ;(login as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('invalid credentials'))
    renderModal()
    fireEvent.change(screen.getByTestId('auth-username'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByTestId('auth-password'), { target: { value: 'wrongpass1' } })
    fireEvent.click(screen.getByTestId('auth-submit'))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('invalid credentials'))
  })

  it('renders nothing when closed', () => {
    render(<AuthModal open={false} onClose={() => {}} onAuthed={() => {}} />)
    expect(screen.queryByTestId('auth-form')).not.toBeInTheDocument()
  })
})

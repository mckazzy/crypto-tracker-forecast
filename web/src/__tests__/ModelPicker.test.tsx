import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ModelPicker from '../components/ModelPicker'
import { fetchAiModels } from '../lib/ai'

vi.mock('../lib/ai', () => ({
  fetchAiModels: vi.fn(),
}))

const mockedFetch = vi.mocked(fetchAiModels)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ModelPicker Component', () => {
  it('renders model options from API with default selected', async () => {
    mockedFetch.mockResolvedValue({
      enabled: true,
      provider: 'openrouter',
      base_url: 'https://openrouter.ai/api/v1',
      default_model: 'deepseek/deepseek-v4-flash-0731',
      models: ['deepseek/deepseek-v4-flash-0731', 'openai/gpt-4o-mini'],
    })
    render(<ModelPicker />)
    const picker = await screen.findByTestId('model-picker')
    const select = picker.querySelector('select') as HTMLSelectElement
    expect(select).toBeInTheDocument()
    expect(select.value).toBe('deepseek/deepseek-v4-flash-0731')
    expect(select.options).toHaveLength(2)
  })

  it('allows user to change the selected model', async () => {
    mockedFetch.mockResolvedValue({
      enabled: true,
      provider: 'openrouter',
      base_url: 'https://openrouter.ai/api/v1',
      default_model: 'deepseek/deepseek-v4-flash-0731',
      models: ['deepseek/deepseek-v4-flash-0731', 'openai/gpt-4o-mini'],
    })
    render(<ModelPicker />)
    const select = (await screen.findByRole('combobox', { name: /AI model/i })) as HTMLSelectElement
    await userEvent.selectOptions(select, 'openai/gpt-4o-mini')
    expect(select.value).toBe('openai/gpt-4o-mini')
  })

  it('handles empty models list gracefully', async () => {
    mockedFetch.mockResolvedValue({
      enabled: true,
      provider: 'openrouter',
      base_url: 'https://openrouter.ai/api/v1',
      default_model: null,
      models: [],
    })
    render(<ModelPicker />)
    expect(await screen.findByText('No models')).toBeInTheDocument()
  })

  it('shows loading state while fetching', () => {
    mockedFetch.mockReturnValue(new Promise(() => {}))
    render(<ModelPicker />)
    expect(screen.getByTestId('model-picker-loading')).toBeInTheDocument()
    expect(screen.getByText('Loading models…')).toBeInTheDocument()
  })

  it('shows error message when API fails', async () => {
    mockedFetch.mockRejectedValue(new Error('ai models 500'))
    render(<ModelPicker />)
    expect(await screen.findByTestId('model-picker-loading')).toHaveTextContent(/AI models unavailable: ai models 500/i)
  })
})

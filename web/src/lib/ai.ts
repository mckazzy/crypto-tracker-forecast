export interface AiModelsResponse {
  enabled: boolean
  provider: string
  base_url: string
  default_model: string | null
  models: string[]
}

export async function fetchAiModels(): Promise<AiModelsResponse> {
  const resp = await fetch('/api/ai/models')
  if (!resp.ok) throw new Error(`ai models ${resp.status}`)
  return resp.json()
}

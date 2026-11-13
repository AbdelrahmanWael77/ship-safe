// AI model reviews (Gemini, OpenAI) requested through the API server, which holds the keys.
import { api } from './api'
import type { AIProvider, AIProviderName, AIReview } from './types'

export const getAIProviders = () => api<AIProvider[]>('/api/ai/providers')

/** Send a stored scan to an AI provider. `acknowledged` is the person's confirmation for non-demo code. */
export const runModelReview = (scanId: string, provider: AIProviderName, acknowledged: boolean) =>
  api<AIReview>(`/api/scans/${encodeURIComponent(scanId)}/ai/model-reviews`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, acknowledge_source_sharing: acknowledged }),
  })

const PROVIDER_LABELS: Record<AIProviderName, string> = { gemini: 'Gemini', openai: 'OpenAI' }
/** Who sends the code where, for the confirmation text. */
export const PROVIDER_COMPANY: Record<AIProviderName, string> = { gemini: 'Google Gemini', openai: 'OpenAI' }

export const isModelReview = (review: AIReview) => review.source === 'gemini_api_generated_unverified' || review.source === 'openai_api_generated_unverified'

/** "OpenAI · gpt-6-luna", "Gemini · gemini-3.6-flash" or "Claude import". */
export const reviewOrigin = (review: AIReview) => {
  if (!isModelReview(review)) return 'Claude import'
  const provider = review.generator?.provider ?? (review.source === 'openai_api_generated_unverified' ? 'openai' : 'gemini')
  return `${PROVIDER_LABELS[provider]}${review.generator?.model ? ` · ${review.generator.model}` : ''}`
}

const number = (value: number) => value.toLocaleString('en-US')

/** "6,000 tokens (3,400 in · 2,600 out, 700 reasoning) · ≈ $0.0016 · 18.2 s", or null for imports. */
export function usageText(review: AIReview): string | null {
  const generator = review.generator
  if (!generator?.usage) return null
  const { input_tokens: input, output_tokens: output, reasoning_tokens: reasoning } = generator.usage
  const parts = [`${number(input + output)} tokens (${number(input)} in · ${number(output)} out${reasoning ? `, ${number(reasoning)} reasoning` : ''})`]
  if (generator.estimated_cost_usd != null) parts.push(`≈ $${generator.estimated_cost_usd < 0.01 ? generator.estimated_cost_usd.toFixed(4) : generator.estimated_cost_usd.toFixed(3)}`)
  if (generator.duration_ms != null) parts.push(`${(generator.duration_ms / 1000).toFixed(1)} s`)
  return parts.join(' · ')
}

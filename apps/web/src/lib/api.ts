import type { Projection } from './events'

export type Session = {
  id: string; seq: number; created_at: string; title: string
  title_source: 'fallback' | 'automatic' | 'manual'
  persona?: string
  archived_at?: string | null
}

/** A simulated identity; its roles decide which knowledge documents the agent can read. */
export type Persona = { id: string; name: string; title: string; roles: string[]; description: string }
export type PersonaRegistry = { default: string; personas: Persona[] }

export class ApiError extends Error {
  status: number
  body: Record<string, unknown>
  constructor(message: string, status: number, body: Record<string, unknown>) {
    super(message)
    this.status = status
    this.body = body
  }
}
export type RuntimeHealth = {
  status: 'ok'
  mode: 'scripted' | 'replay' | 'record' | 'live'
}

export type PrivacyBinding = { token: string; value: string; kind: string }
export type XrayData = {
  display: Projection
  model: Projection
  bindings: PrivacyBinding[]
  executions: { conversation_turn_id: string; tool: string; arguments: Record<string, unknown> }[]
  requests: {
    request_id: string
    conversation_turn_id: string
    request: {
      model: string
      messages: { role: string; content?: string | null; tool_calls?: unknown[]; tool_call_id?: string }[]
      tools?: unknown[]
    }
    audit: { purpose: string; mode: string; request_hash: string; outcome: string }
  }[]
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(
      typeof body?.detail === 'string'
        ? body.detail
        : `Request failed (${response.status})`, response.status, body ?? {},
    )
  }
  return response.json() as Promise<T>
}

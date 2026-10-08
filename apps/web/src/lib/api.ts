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

/**
 * Opens a citation on the intranet in a new tab, signed in as the session's persona. The BFF
 * mints the sign-in; a form post keeps the quotation out of URLs and access logs.
 */
export function openCitation(sessionId: string, fields: Record<string, string | undefined>) {
  const form = document.createElement('form')
  form.method = 'post'
  form.action = `/api/sessions/${encodeURIComponent(sessionId)}/citations/open`
  form.target = '_blank'
  form.rel = 'noopener noreferrer'
  for (const [name, value] of Object.entries(fields)) {
    if (!value) continue
    const input = document.createElement('input')
    input.type = 'hidden'
    input.name = name
    input.value = value
    form.append(input)
  }
  document.body.append(form)
  form.submit()
  form.remove()
}

export type Session = { id: string; seq: number; created_at: string }
export type RuntimeHealth = {
  status: 'ok'
  mode: 'scripted' | 'replay' | 'record' | 'live'
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(
      typeof body?.detail === 'string'
        ? body.detail
        : `Request failed (${response.status})`,
    )
  }
  return response.json() as Promise<T>
}

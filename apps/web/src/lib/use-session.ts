import { useEffect, useState } from 'react'
import { request } from './api'
import type { PrivacyBinding } from './api'
import { reduceEvent } from './events'
import type { LogEvent, Projection } from './events'

export function resolveDisplayText(text: string, bindings: PrivacyBinding[]) {
  return text.replace(/\[[A-Z][A-Z0-9]*_\d+\]/g, (token) =>
    bindings.find((binding) => binding.token === token)?.value ?? token,
  )
}

export function useSession(sessionId: string) {
  const [state, setState] = useState<Projection | null>(null)
  const [bindingState, setBindingState] = useState<{ sessionId: string; values: PrivacyBinding[] }>({
    sessionId: '', values: [],
  })
  const bindings = bindingState.sessionId === sessionId ? bindingState.values : []
  const [connection, setConnection] = useState<
    'connecting' | 'live' | 'reconnecting'
  >('connecting')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    let disposed = false
    let source: EventSource | null = null
    let current: Projection | null = null
    let recovery: ReturnType<typeof setTimeout> | undefined
    let loading = false
    let knownBindings: PrivacyBinding[] = []
    let refreshingBindings = false
    let bindingsPending = false

    async function refreshBindings() {
      if (disposed) return
      if (refreshingBindings) { bindingsPending = true; return }
      refreshingBindings = true
      try {
        const result = await request<PrivacyBinding[]>(`/sessions/${sessionId}/bindings`, {
          signal: controller.signal,
        })
        if (!disposed) { knownBindings = result; setBindingState({ sessionId, values: result }) }
      } catch (reason) {
        if (!disposed) setError(reason instanceof Error ? reason.message : 'Display bindings unavailable')
      } finally {
        refreshingBindings = false
        if (bindingsPending && !disposed) {
          bindingsPending = false
          void refreshBindings()
        }
      }
    }

    function retry() {
      if (recovery === undefined && !disposed) {
        recovery = setTimeout(() => {
          recovery = undefined
          void initialize()
        }, 3000)
      }
    }

    async function initialize() {
      if (loading || disposed) return
      loading = true
      source?.close()
      try {
        const snapshot = await request<Projection>(
          `/sessions/${sessionId}/snapshot?representation=model`,
          {
            signal: controller.signal,
          },
        )
        if (disposed) return
        setError(null)
        await refreshBindings()
        if (disposed) return
        current = snapshot
        setState(snapshot)
        const stream = new EventSource(
          `/api/sessions/${sessionId}/events?from=${snapshot.seq}&follow=true&representation=model`,
        )
        source = stream
        stream.onopen = () => {
          if (disposed || source !== stream) return
          clearTimeout(recovery)
          recovery = undefined
          setConnection('live')
        }
        stream.addEventListener('log', (message: MessageEvent<string>) => {
          if (disposed || source !== stream || !current) return
          try {
            const event = JSON.parse(message.data) as LogEvent
            if (message.lastEventId !== String(event.seq))
              throw new Error('Event cursor mismatch')
            current = reduceEvent(current, event)
            setState(current)
            const tokens = JSON.stringify(current).match(/\[[A-Z][A-Z0-9]*_\d+\]/g) ?? []
            if (tokens.some((token) => !knownBindings.some((binding) => binding.token === token))) {
              void refreshBindings()
            }
          } catch {
            stream.close()
            setConnection('reconnecting')
            void initialize()
          }
        })
        stream.onerror = () => {
          if (disposed || source !== stream) return
          setConnection('reconnecting')
          retry()
        }
      } catch (reason) {
        if (disposed) return
        setError(
          reason instanceof Error ? reason.message : 'Connection unavailable',
        )
        setConnection('reconnecting')
        retry()
      } finally {
        loading = false
      }
    }

    void initialize()
    return () => {
      disposed = true
      controller.abort()
      source?.close()
      clearTimeout(recovery)
    }
  }, [sessionId])

  let displayed: Projection | null = null
  if (state?.session_id === sessionId) {
    const { messages, ...metadata } = state
    displayed = { ...JSON.parse(JSON.stringify(metadata, (_key, value) =>
      typeof value === 'string' ? resolveDisplayText(value, bindings) : value,
    )), messages }
  }
  return {
    state: displayed,
    bindings,
    connection,
    error,
  }
}

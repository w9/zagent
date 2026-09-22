import { useEffect, useState } from 'react'
import { request } from './api'
import { reduceEvent } from './events'
import type { LogEvent, Projection } from './events'

export function useSession(sessionId: string) {
  const [state, setState] = useState<Projection | null>(null)
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
          `/sessions/${sessionId}/snapshot`,
          {
            signal: controller.signal,
          },
        )
        if (disposed) return
        current = snapshot
        setState(snapshot)
        setError(null)
        const stream = new EventSource(
          `/api/sessions/${sessionId}/events?from=${snapshot.seq}&follow=true`,
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

  return {
    state: state?.session_id === sessionId ? state : null,
    connection,
    error,
  }
}

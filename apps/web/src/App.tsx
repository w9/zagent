import { useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { MessageSquare, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ChatPanel } from './components/chat/chat-panel'
import { AppShell } from './components/shell/app-shell'
import { SessionLayout } from './components/shell/session-layout'
import { SessionList } from './components/shell/session-list'
import { WorkingSurface } from './components/surface/working-surface'
import { Button } from './components/ui/button'
import { EmptyState } from './components/ui/empty-state'
import { Spinner } from './components/ui/spinner'
import { XrayPanel } from './components/xray/xray-panel'
import { request } from './lib/api'
import type { RuntimeHealth, Session } from './lib/api'
import { useSession } from './lib/use-session'
import type { TableData } from './lib/views'

function SessionWorkspace({ sessionId, name }: { sessionId: string; name: string }) {
  const session = useSession(sessionId)
  const search = useSearch({ strict: false })
  const navigate = useNavigate()
  const views = session.state?.views ?? []
  const hasSnapshot = session.state !== null

  useEffect(() => {
    if (!hasSnapshot) return
    try {
      localStorage.setItem('zagent.session', sessionId)
    } catch {
      // Remembering the last session is a convenience.
    }
  }, [sessionId, hasSnapshot])

  if (search.xray) return <XrayPanel sessionId={sessionId} seq={session.state?.seq ?? 0} />

  function update(next: { view?: string; panel?: 'surface' }) {
    void navigate({ to: '/sessions/$sessionId', params: { sessionId }, search: { ...search, ...next }, replace: true })
  }

  return (
    <SessionLayout
      panel={search.panel === 'surface' ? 'surface' : 'chat'}
      onPanelChange={(panel) => update({ panel: panel === 'surface' ? 'surface' : undefined })}
      viewCount={views.length}
      chat={
        <ChatPanel
          sessionId={sessionId}
          name={name}
          state={session.state}
          bindings={session.bindings}
          connection={session.connection}
          error={session.error}
          onSend={async (text) => {
            await request(`/sessions/${sessionId}/messages`, { method: 'POST', body: JSON.stringify({ text }) })
          }}
        />
      }
      surface={
        <WorkingSurface
          sessionId={sessionId}
          views={views}
          drafts={session.state?.drafts}
          jobs={session.state?.jobs}
          selectedId={search.view}
          onSelect={(view) => update({ view })}
          resolveHandle={(handle, signal) =>
            request<TableData>(`/sessions/${sessionId}/handles/${encodeURIComponent(handle)}`, { signal })
          }
        />
      }
    />
  )
}

export default function App() {
  const { sessionId } = useParams({ strict: false })
  const navigate = useNavigate()
  const search = useSearch({ strict: false })
  const [sessions, setSessions] = useState<Session[] | null>(null)
  const [mode, setMode] = useState<RuntimeHealth['mode'] | null>(null)
  const [creating, setCreating] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    async function refresh() {
      try {
        const [items, health] = await Promise.all([
          request<Session[]>('/sessions', { signal: controller.signal }),
          request<RuntimeHealth>('/health', { signal: controller.signal }),
        ])
        setSessions(items)
        setMode(health.mode)
        setError(null)
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Sessions unavailable')
      }
    }
    void refresh()
    const changes = new EventSource('/api/session-list/events')
    changes.addEventListener('sessions', (event) => {
      try {
        setSessions(JSON.parse((event as MessageEvent).data) as Session[])
      } catch {
        void refresh()
      }
    })
    window.addEventListener('focus', refresh)
    return () => {
      controller.abort()
      changes.close()
      window.removeEventListener('focus', refresh)
    }
  }, [])

  useEffect(() => {
    if (sessionId || !sessions?.length) return
    let previous: string | null = null
    try {
      previous = localStorage.getItem('zagent.session')
    } catch {
      previous = null
    }
    const selected = sessions.find((session) => session.id === previous) ?? sessions[0]
    void navigate({ to: '/sessions/$sessionId', params: { sessionId: selected.id }, search: {}, replace: true })
  }, [sessionId, sessions, navigate])

  async function createSession() {
    if (creating) return
    setCreating(true)
    try {
      const session = await request<Session>('/sessions', { method: 'POST' })
      setSessions((current) => [session, ...(current ?? []).filter((item) => item.id !== session.id)])
      setDrawerOpen(false)
      setError(null)
      await navigate({ to: '/sessions/$sessionId', params: { sessionId: session.id }, search: {} })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Session could not be created')
    } finally {
      setCreating(false)
    }
  }

  async function renameSession(id: string, title: string) {
    const updated = await request<Session>(`/sessions/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) })
    setSessions((current) => (current ?? []).map((item) => (item.id === id ? updated : item)))
  }

  const list = sessions ?? []
  const current = list.find((session) => session.id === sessionId)

  return (
    <AppShell
      mode={mode}
      error={error}
      drawerOpen={drawerOpen}
      onDrawerOpenChange={setDrawerOpen}
      xray={
        sessionId
          ? {
              active: search.xray === true,
              onToggle: () => {
                void navigate({
                  to: '/sessions/$sessionId',
                  params: { sessionId },
                  search: { ...search, xray: search.xray ? undefined : true },
                })
              },
            }
          : undefined
      }
      sidebar={(inDrawer) => (
        <SessionList
          sessions={list}
          selectedId={sessionId}
          creating={creating}
          showTitle={!inDrawer}
          onCreate={() => void createSession()}
          onNavigate={() => setDrawerOpen(false)}
          onRename={renameSession}
        />
      )}
    >
      {sessionId ? (
        <SessionWorkspace key={sessionId} sessionId={sessionId} name={current?.title ?? 'Session'} />
      ) : sessions && !sessions.length ? (
        <EmptyState
          icon={MessageSquare}
          title="No sessions yet"
          description="Start a session to ask about specimens, libraries and analysis jobs."
          action={<Button variant="primary" icon={Plus} loading={creating} onClick={() => void createSession()}>New session</Button>}
          className="flex-1"
        />
      ) : (
        <div role="status" className="flex flex-1 items-center justify-center gap-2 text-sm text-muted">
          <Spinner />
          Loading sessions…
        </div>
      )}
    </AppShell>
  )
}

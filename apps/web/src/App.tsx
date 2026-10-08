import { useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { MessageSquare, Plus, Undo2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ChatPanel } from './components/chat/chat-panel'
import { AppShell } from './components/shell/app-shell'
import { SessionLayout } from './components/shell/session-layout'
import { SessionList } from './components/shell/session-list'
import type { SessionListView } from './components/shell/session-list'
import { WorkingSurface } from './components/surface/working-surface'
import { Button } from './components/ui/button'
import { Dialog } from './components/ui/dialog'
import { EmptyState } from './components/ui/empty-state'
import { Spinner } from './components/ui/spinner'
import { Toast } from './components/ui/toast'
import { XrayPanel } from './components/xray/xray-panel'
import { ApiError, request } from './lib/api'
import type { Persona, PersonaRegistry, RuntimeHealth, Session } from './lib/api'
import { plural } from './lib/format'
import { useSession } from './lib/use-session'
import type { TableData } from './lib/views'

const newestFirst = (first: Session, second: Session) =>
  second.created_at.localeCompare(first.created_at) || second.id.localeCompare(first.id)

function SessionWorkspace({
  sessionId,
  name,
  persona,
  onUnarchive,
}: {
  sessionId: string
  name: string
  persona?: Persona
  onUnarchive?: () => void
}) {
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
          persona={persona}
          state={session.state}
          bindings={session.bindings}
          connection={session.connection}
          error={session.error}
          onSend={async (text) => {
            await request(`/sessions/${sessionId}/messages`, { method: 'POST', body: JSON.stringify({ text }) })
          }}
          onUnarchive={onUnarchive}
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
          readOnly={Boolean(onUnarchive)}
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
  const [personas, setPersonas] = useState<PersonaRegistry | null>(null)
  const [persona, setPersona] = useState<string | null>(null)
  const [mode, setMode] = useState<RuntimeHealth['mode'] | null>(null)
  const [creating, setCreating] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sidebarView, setSidebarView] = useState<SessionListView>('active')
  const [archived, setArchived] = useState<Session[] | null>(null)
  const [undo, setUndo] = useState<{ session: Session; wasOpen: boolean } | null>(null)
  const [unfinished, setUnfinished] = useState<{ session: Session; responding: boolean; jobs: number } | null>(null)
  const [archiving, setArchiving] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    // Without the registry, new sessions use the server's default persona.
    request<PersonaRegistry>('/personas', { signal: controller.signal }).then(setPersonas, () => {})
    return () => controller.abort()
  }, [])

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

  const chosenPersona = persona ?? personas?.default
  // An open session missing from the active list may be archived.
  const needArchived =
    sidebarView === 'archived' || Boolean(sessionId && sessions && !sessions.some((item) => item.id === sessionId))

  useEffect(() => {
    if (!needArchived) return
    const controller = new AbortController()
    request<Session[]>('/sessions?archived=true', { signal: controller.signal }).then(setArchived, (reason) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Archived sessions unavailable')
    })
    return () => controller.abort()
  }, [needArchived, sessions])

  async function createSession() {
    if (creating) return
    setCreating(true)
    try {
      const session = await request<Session>('/sessions', {
        method: 'POST',
        body: chosenPersona ? JSON.stringify({ persona: chosenPersona }) : undefined,
      })
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

  // Without work in progress the archive happens at once and can be undone; otherwise the user confirms first.
  async function archiveSession(session: Session, force = false) {
    setArchiving(true)
    try {
      await request<Session>(`/sessions/${session.id}/archive`, { method: 'POST', body: JSON.stringify({ force }) })
    } catch (reason) {
      if (reason instanceof ApiError && reason.body.code === 'work_in_progress') {
        setUnfinished({ session, responding: reason.body.responding === true, jobs: Number(reason.body.jobs) || 0 })
      } else {
        setUnfinished(null)
        setError(reason instanceof Error ? reason.message : 'Session could not be archived')
      }
      return
    } finally {
      setArchiving(false)
    }
    setUnfinished(null)
    // The drawer is modal; closing it lets the user reach Undo and the next session.
    setDrawerOpen(false)
    setUndo(force ? null : { session, wasOpen: session.id === sessionId })
    const remaining = (sessions ?? []).filter((item) => item.id !== session.id)
    setSessions(remaining)
    if (session.id !== sessionId) return
    if (remaining.length) {
      await navigate({ to: '/sessions/$sessionId', params: { sessionId: remaining[0].id }, search: {} })
    } else {
      await navigate({ to: '/', search: {} })
    }
  }

  async function unarchiveSession(session: Session, open = false) {
    try {
      const restored = await request<Session>(`/sessions/${session.id}/unarchive`, { method: 'POST' })
      setSessions((current) => [restored, ...(current ?? []).filter((item) => item.id !== restored.id)].sort(newestFirst))
      setArchived((current) => current && current.filter((item) => item.id !== restored.id))
      if (open) await navigate({ to: '/sessions/$sessionId', params: { sessionId: restored.id }, search: {} })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Session could not be unarchived')
    }
  }

  const list = sessions ?? []
  const current = list.find((session) => session.id === sessionId) ?? archived?.find((session) => session.id === sessionId)

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
          personas={personas?.personas}
          persona={chosenPersona}
          onPersonaChange={setPersona}
          onCreate={() => void createSession()}
          onNavigate={() => setDrawerOpen(false)}
          onRename={renameSession}
          view={sidebarView}
          archived={archived}
          onViewChange={setSidebarView}
          onArchive={(session) => void archiveSession(session)}
          onUnarchive={(session) => void unarchiveSession(session)}
        />
      )}
    >
      {sessionId ? (
        <SessionWorkspace
          key={sessionId}
          sessionId={sessionId}
          name={current?.title ?? 'Session'}
          persona={personas?.personas.find((item) => item.id === current?.persona)}
          onUnarchive={current?.archived_at ? () => void unarchiveSession(current) : undefined}
        />
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
      {undo && (
        <Toast
          key={undo.session.id}
          onDismiss={() => setUndo(null)}
          action={
            <Button
              variant="ghost"
              size="sm"
              icon={Undo2}
              onClick={() => {
                setUndo(null)
                void unarchiveSession(undo.session, undo.wasOpen)
              }}
            >
              Undo
            </Button>
          }
        >
          Archived “{undo.session.title}”
        </Toast>
      )}
      <Dialog
        open={unfinished !== null}
        onOpenChange={(open) => {
          if (!open) setUnfinished(null)
        }}
        title={`Archive “${unfinished?.session.title ?? ''}”?`}
        actions={
          <>
            <Button disabled={archiving} onClick={() => setUnfinished(null)}>Cancel</Button>
            <Button
              variant="primary"
              loading={archiving}
              onClick={() => {
                if (unfinished) void archiveSession(unfinished.session, true)
              }}
            >
              {unfinished?.responding ? 'Stop and archive' : 'Archive'}
            </Button>
          </>
        }
      >
        {unfinished?.responding && <p>The agent is still responding. Archiving stops the response, and it can't be resumed.</p>}
        {Boolean(unfinished?.jobs) && (
          <p>{plural(unfinished?.jobs ?? 0, 'job', 'jobs')} will keep running, and the results stay with the session.</p>
        )}
        <p>You can unarchive the session later from Archived.</p>
      </Dialog>
    </AppShell>
  )
}

import * as Dialog from '@radix-ui/react-dialog'
import * as Tooltip from '@radix-ui/react-tooltip'
import { Link, useNavigate, useParams, useSearch } from '@tanstack/react-router'
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  Check,
  Dna,
  FlaskConical,
  Hash,
  LoaderCircle,
  MessageSquare,
  PanelLeft,
  Plus,
  Pencil,
  ScanEye,
  ShieldCheck,
  Table2,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Button } from './components/ui/button'
import { IconButton } from './components/ui/icon-button'
import { StepMarker } from './components/step-marker'
import { RefusalChip } from './components/refusal-chip'
import { WorkingSurface } from './components/working-surface'
import { XrayPanel } from './components/xray-panel'
import { TranscriptText } from './components/transcript-text'
import { request } from './lib/api'
import { toolView } from './lib/events'
import type { RuntimeHealth, Session } from './lib/api'
import { useSession } from './lib/use-session'

function Sidebar({
  sessions,
  selected,
  creating,
  onCreate,
  onSelect,
  onRename,
}: {
  sessions: Session[]
  selected?: string
  creating: boolean
  onCreate: () => void
  onSelect: () => void
  onRename: (id: string, title: string) => Promise<void>
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [saving, setSaving] = useState(false)
  const [renameError, setRenameError] = useState<string | null>(null)

  async function saveTitle(id: string) {
    if (saving || !title.trim()) return
    setSaving(true)
    try { await onRename(id, title.trim()); setEditing(null); setRenameError(null) }
    catch (reason) { setRenameError(reason instanceof Error ? reason.message : 'Rename failed') }
    finally { setSaving(false) }
  }
  return (
    <div className="sidebar-content">
      <div className="sidebar-heading">
        <span>Sessions</span>
        <span className="session-count">{sessions.length}</span>
      </div>
      <Button
        variant="ghost"
        className="new-session"
        onClick={onCreate}
        disabled={creating}
      >
        {creating ? <LoaderCircle className="spin" /> : <Plus />} New session
      </Button>
      <nav aria-label="Sessions" className="session-list">
        {sessions.map((session) => <div key={session.id} className="session-entry" data-session-id={session.id}>
          {editing === session.id ? <form className="session-rename" onSubmit={(event) => {
            event.preventDefault(); void saveTitle(session.id)
          }}>
            <input aria-label="Session title" value={title} maxLength={120} autoFocus
              onChange={(event) => setTitle(event.target.value)} />
            <IconButton label="Save session title" type="submit" disabled={saving || !title.trim()}><Check /></IconButton>
            <IconButton label="Cancel rename" onClick={() => setEditing(null)}><X /></IconButton>
          </form> : <>
          <Link
            to="/sessions/$sessionId"
            params={{ sessionId: session.id }}
            search={{}}
            className={`session-link ${selected === session.id ? 'selected' : ''}`}
            aria-current={selected === session.id ? 'page' : undefined}
            onClick={onSelect}
          >
            <MessageSquare size={16} aria-hidden="true" />
            <span>
              {session.title}
              <small>
                {new Date(session.created_at).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                })}
              </small>
            </span>
          </Link>
          <IconButton label={`Rename ${session.title}`} className="session-rename-trigger"
            onClick={() => { setEditing(session.id); setTitle(session.title); setRenameError(null) }}><Pencil /></IconButton>
          </>}
        </div>)}
        {renameError && <p role="alert" className="surface-error">{renameError}</p>}
      </nav>
      <div className="sidebar-footer">
        <ShieldCheck size={15} /> Synthetic data <span>01</span>
      </div>
    </div>
  )
}

function Chat({
  sessionId,
  name,
  state,
  bindings,
  connection,
  error,
}: {
  sessionId: string
  name: string
} & ReturnType<typeof useSession>) {
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [atBottom, setAtBottom] = useState(true)
  const scrollArea = useRef<HTMLDivElement>(null)
  const hasSnapshot = state !== null
  const responding = state?.conversation_turn?.status === 'running'
  const canSend = Boolean(
    state && connection === 'live' && !responding && !sending && draft.trim(),
  )
  const status =
    connection !== 'live'
      ? connection === 'connecting'
        ? 'Connecting'
        : 'Reconnecting'
      : responding
        ? 'Responding'
        : state?.conversation_turn?.status === 'failed'
          ? 'Failed'
          : state?.conversation_turn
            ? 'Complete'
            : 'Ready'
  const views = state?.views ?? []
  const stepViews = new Set((state?.steps ?? []).flatMap((step) =>
    (step.tools ?? []).flatMap((tool) => toolView(tool)?.id ?? [])))
  const timeline = [
    ...(state?.messages ?? []).map((value) => ({
      kind: 'message' as const,
      value,
    })),
    ...(state?.steps ?? []).map((value) => ({ kind: 'step' as const, value })),
    ...(state?.refusals ?? []).map((value) => ({ kind: 'refusal' as const, value })),
    ...views.filter((view) => !stepViews.has(view.id))
      .map((value) => ({ kind: 'view' as const, value })),
  ].sort((first, second) => first.value.seq - second.value.seq)
  const viewLink = (viewId: string, children: ReactNode) => views.some((view) => view.id === viewId)
    ? <Link className="view-link" data-view-id={viewId} to="/sessions/$sessionId" params={{ sessionId }}
      search={{ view: viewId, panel: 'surface' }}>{children}</Link>
    : children

  useEffect(() => {
    if (atBottom && scrollArea.current)
      scrollArea.current.scrollTop = scrollArea.current.scrollHeight
  }, [state?.seq, atBottom])

  useEffect(() => {
    if (hasSnapshot) {
      try {
        localStorage.setItem('zagent.session', sessionId)
      } catch {
        return
      }
    }
  }, [sessionId, hasSnapshot])

  async function send() {
    if (!canSend) return
    const text = draft
    setSending(true)
    setSendError(null)
    setAtBottom(true)
    try {
      await request(`/sessions/${sessionId}/messages`, {
        method: 'POST',
        body: JSON.stringify({ text }),
      })
      setDraft((current) => (current === text ? '' : current))
    } catch (reason) {
      setSendError(
        reason instanceof Error ? reason.message : 'Message could not be sent',
      )
    } finally {
      setSending(false)
    }
  }

  return (
    <main className="chat-panel" id="conversation-panel">
      <header className="panel-heading chat-heading">
        <div>
          <h2>Conversation</h2>
          <span className="session-subtitle">{name}</span>
        </div>
        <div className="chat-state">
          <span
            className={`conversation-turn-status ${status.toLowerCase()}`}
            role="status"
            aria-label="Conversation turn status"
            data-testid="conversation-turn-status"
          >
            <i />
            {status}
          </span>
          <span className="sequence" title="Last event sequence">
            <Hash size={12} />
            {String(state?.seq ?? 0).padStart(4, '0')}
          </span>
        </div>
      </header>
      <div className="conversation-wrap">
        <div
          className="conversation-scroll"
          ref={scrollArea}
          onScroll={(event) => {
            const area = event.currentTarget
            setAtBottom(
              area.scrollHeight - area.scrollTop - area.clientHeight < 80,
            )
          }}
        >
          {!state?.messages.length ? (
            <div className="empty-chat">
              <Dna size={32} strokeWidth={1.4} aria-hidden="true" />
              <span className="eyebrow">{name}</span>
              <h2>{state ? 'A new conversation' : 'Opening conversation'}</h2>
              <span className="empty-rule" />
            </div>
          ) : (
            <ol className="messages" aria-label="Conversation">
              {timeline.map((item) => {
                if (item.kind === 'view') return <li key={`view:${item.value.id}`} className="view-reference-item">
                  <Link className="view-reference" data-view-id={item.value.id} to="/sessions/$sessionId" params={{ sessionId }}
                    search={{ view: item.value.id, panel: 'surface' }}>
                    <Table2 size={15} aria-hidden="true" />
                    <span>{String(item.value.spec.props.title ?? item.value.spec.kind)}</span>
                    <ArrowUpRight size={14} aria-hidden="true" />
                  </Link>
                </li>
                if (item.kind === 'refusal')
                  return (
                    <li key={`refusal:${item.value.id}`} className="message">
                      <RefusalChip refusal={item.value} />
                    </li>
                  )
                if (item.kind === 'step')
                  return (
                    <li key={`step:${item.value.id}`} className="step-message">
                      <StepMarker step={item.value} viewLink={viewLink} />
                    </li>
                  )
                const message = item.value
                return (
                  <li
                    key={message.id}
                    className={`message ${message.role}`}
                    data-testid={`${message.role}-message`}
                  >
                    <TranscriptText text={message.text} role={message.role} bindings={bindings}
                      viewLink={viewLink}
                      streaming={message.status === 'streaming'} />
                    {message.status === 'failed' && (
                      <span className="interrupted">Interrupted</span>
                    )}
                  </li>
                )
              })}
            </ol>
          )}
        </div>
        {!atBottom && (
          <IconButton
            label="Latest message"
            className="latest-message"
            onClick={() => setAtBottom(true)}
          >
            <ArrowDown />
          </IconButton>
        )}
      </div>
      <div className="composer-area">
        {(error || sendError || state?.conversation_turn?.error) && (
          <div className="error-notice" role="alert">
            <AlertTriangle size={16} />
            <span>{error || sendError || state?.conversation_turn?.error}</span>
          </div>
        )}
        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault()
            void send()
          }}
        >
          <textarea
            aria-label="Message"
            placeholder="Message Zagent..."
            rows={2}
            maxLength={20000}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            disabled={!state}
            onKeyDown={(event) => {
              if (
                event.key === 'Enter' &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing
              ) {
                event.preventDefault()
                void send()
              }
            }}
          />
          <IconButton
            label="Send message"
            type="submit"
            variant="default"
            className="send-message"
            disabled={!canSend}
          >
            <ArrowUp />
          </IconButton>
        </form>
        <div className="composer-footer">
          <span>
            <FlaskConical size={13} />
            Genomics agent
          </span>
          <span>Synthetic data only</span>
        </div>
      </div>
    </main>
  )
}

function SessionWorkspace({
  sessionId,
  name,
}: {
  sessionId: string
  name: string
}) {
  const session = useSession(sessionId)
  const search = useSearch({ strict: false })
  const navigate = useNavigate()
  const views = session.state?.views ?? []
  const surface = search.panel === 'surface'

  if (search.xray) return <XrayPanel sessionId={sessionId} seq={session.state?.seq ?? 0} />

  function selectPanel(showSurface: boolean) {
    void navigate({
      to: '/sessions/$sessionId',
      params: { sessionId },
      search: { ...search, panel: showSurface ? 'surface' : undefined },
      replace: true,
    })
  }

  return (
    <section
      className="session-workspace"
      data-mobile-panel={surface ? 'surface' : 'chat'}
    >
      <div
        className="workspace-mobile-tabs"
        role="tablist"
        aria-label="Workspace panels"
      >
        <button
          type="button"
          role="tab"
          aria-selected={!surface}
          aria-controls="conversation-panel"
          onClick={() => selectPanel(false)}
        >
          <MessageSquare size={15} />
          Conversation
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={surface}
          aria-controls="working-surface"
          onClick={() => selectPanel(true)}
        >
          <Table2 size={15} />
          Working surface<span>{views.length}</span>
        </button>
      </div>
      <Chat sessionId={sessionId} name={name} {...session} />
      <WorkingSurface
        sessionId={sessionId}
        views={views}
        drafts={session.state?.drafts}
        jobs={session.state?.jobs}
        selectedId={search.view}
        onSelect={(view) => {
          void navigate({
            to: '/sessions/$sessionId',
            params: { sessionId },
            search: { ...search, view },
            replace: true,
          })
        }}
      />
    </section>
  )
}

export default function App() {
  const { sessionId } = useParams({ strict: false })
  const navigate = useNavigate()
  const search = useSearch({ strict: false })
  const [sessions, setSessions] = useState<Session[]>([])
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
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error ? reason.message : 'Sessions unavailable',
          )
      }
    }
    void refresh()
    const changes = new EventSource('/api/session-list/events')
    changes.addEventListener('sessions', (event) => {
      try { setSessions(JSON.parse((event as MessageEvent).data) as Session[]) }
      catch { void refresh() }
    })
    window.addEventListener('focus', refresh)
    return () => {
      controller.abort()
      changes.close()
      window.removeEventListener('focus', refresh)
    }
  }, [])

  useEffect(() => {
    if (sessionId || !sessions.length) return
    let previous: string | null = null
    try {
      previous = localStorage.getItem('zagent.session')
    } catch {
      previous = null
    }
    const selected =
      sessions.find((session) => session.id === previous) ?? sessions[0]
    void navigate({
      to: '/sessions/$sessionId',
      params: { sessionId: selected.id },
      search: {},
      replace: true,
    })
  }, [sessionId, sessions, navigate])

  async function createSession() {
    if (creating) return
    setCreating(true)
    try {
      const session = await request<Session>('/sessions', { method: 'POST' })
      setSessions((current) => [session, ...current.filter((item) => item.id !== session.id)])
      setDrawerOpen(false)
      setError(null)
      await navigate({
        to: '/sessions/$sessionId',
        params: { sessionId: session.id },
        search: {},
      })
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Session could not be created',
      )
    } finally {
      setCreating(false)
    }
  }

  const sidebar = (
    <Sidebar
      sessions={sessions}
      selected={sessionId}
      creating={creating}
      onCreate={() => void createSession()}
      onSelect={() => setDrawerOpen(false)}
      onRename={async (id, title) => {
        const updated = await request<Session>(`/sessions/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) })
        setSessions((current) => current.map((item) => item.id === id ? updated : item))
      }}
    />
  )
  const selectedIndex = sessions.findIndex(
    (session) => session.id === sessionId,
  )

  return (
    <Tooltip.Provider delayDuration={300}>
      <Dialog.Root open={drawerOpen} onOpenChange={setDrawerOpen}>
        <div className="workspace">
          <header className="topbar">
            <div className="brand-group">
              <Dialog.Trigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="mobile-menu"
                  aria-label="Open sessions"
                >
                  <PanelLeft />
                </Button>
              </Dialog.Trigger>
              <div className="brand">
                <Dna size={25} strokeWidth={1.6} />
                <h1>
                  Zagent<span>.</span>
                </h1>
              </div>
              <span className="domain-label">Clinical genomics</span>
            </div>
            <div className="environment">
              {sessionId && <IconButton label="X-ray" aria-pressed={search.xray === true}
                onClick={() => { void navigate({
                  to: '/sessions/$sessionId', params: { sessionId },
                  search: { ...search, xray: search.xray ? undefined : true },
                }) }}><ScanEye /></IconButton>}
              <span>LOCAL</span>
              <span className="environment-dot" />
              {mode ? mode[0].toUpperCase() + mode.slice(1) : 'Agent'}
            </div>
          </header>
          {error && (
            <div className="app-error" role="alert">
              {error}
            </div>
          )}
          <div className="workspace-panels">
            <aside className="sidebar">{sidebar}</aside>
            {sessionId ? (
              <SessionWorkspace
                key={sessionId}
                sessionId={sessionId}
                name={
                  selectedIndex < 0 ? 'Session' : sessions[selectedIndex].title
                }
              />
            ) : (
              <main className="loading-panel">
                <LoaderCircle className="spin" aria-label="Loading sessions" />
              </main>
            )}
          </div>
        </div>
        <Dialog.Portal>
          <Dialog.Overlay className="drawer-overlay" />
          <Dialog.Content className="drawer" aria-describedby={undefined}>
            <Dialog.Title className="sr-only">Sessions</Dialog.Title>
            <Dialog.Close asChild>
              <Button
                variant="ghost"
                size="icon"
                className="drawer-close"
                aria-label="Close sessions"
              >
                <X />
              </Button>
            </Dialog.Close>
            {sidebar}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </Tooltip.Provider>
  )
}

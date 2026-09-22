import * as Dialog from '@radix-ui/react-dialog'
import * as Tooltip from '@radix-ui/react-tooltip'
import { Link, useNavigate, useParams } from '@tanstack/react-router'
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Dna,
  FlaskConical,
  Hash,
  LoaderCircle,
  MessageSquare,
  PanelLeft,
  PanelRight,
  Plus,
  ShieldCheck,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button } from './components/ui/button'
import { IconButton } from './components/ui/icon-button'
import { request } from './lib/api'
import type { Session } from './lib/api'
import { useSession } from './lib/use-session'

function sessionName(index: number) {
  return `Session ${String(index + 1).padStart(2, '0')}`
}

function Sidebar({
  sessions,
  selected,
  creating,
  onCreate,
  onSelect,
}: {
  sessions: Session[]
  selected?: string
  creating: boolean
  onCreate: () => void
  onSelect: () => void
}) {
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
        {sessions.map((session, index) => (
          <Link
            key={session.id}
            to="/sessions/$sessionId"
            params={{ sessionId: session.id }}
            className={`session-link ${selected === session.id ? 'selected' : ''}`}
            aria-current={selected === session.id ? 'page' : undefined}
            onClick={onSelect}
          >
            <MessageSquare size={16} aria-hidden="true" />
            <span>
              {sessionName(index)}
              <small>
                {new Date(session.created_at).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                })}
              </small>
            </span>
          </Link>
        ))}
      </nav>
      <div className="sidebar-footer">
        <ShieldCheck size={15} /> Synthetic data <span>01</span>
      </div>
    </div>
  )
}

function Chat({ sessionId, name }: { sessionId: string; name: string }) {
  const { state, connection, error } = useSession(sessionId)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [atBottom, setAtBottom] = useState(true)
  const scrollArea = useRef<HTMLDivElement>(null)
  const hasSnapshot = state !== null
  const running = state?.run?.status === 'running'
  const canSend = Boolean(
    state && connection === 'live' && !running && !sending && draft.trim(),
  )
  const status =
    connection !== 'live'
      ? connection === 'connecting'
        ? 'Connecting'
        : 'Reconnecting'
      : running
        ? 'Running'
        : state?.run?.status === 'failed'
          ? 'Failed'
          : state?.run
            ? 'Complete'
            : 'Ready'

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
    <main className="chat-panel">
      <header className="panel-heading chat-heading">
        <div>
          <h2>Conversation</h2>
          <span className="session-subtitle">{name}</span>
        </div>
        <div className="chat-state">
          <span
            className={`run-status ${status.toLowerCase()}`}
            role="status"
            data-testid="run-status"
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
              {state.messages.map((message) => (
                <li
                  key={message.id}
                  className={`message ${message.role}`}
                  data-testid={`${message.role}-message`}
                >
                  <div className="message-label">
                    {message.role === 'assistant' && <Dna size={15} />}
                    {message.role === 'user' ? 'You' : 'Zagent'}
                    {message.status === 'failed' && (
                      <span className="interrupted">Interrupted</span>
                    )}
                  </div>
                  <p className="message-text" data-testid="message-text">
                    {message.text}
                    {message.status === 'streaming' && (
                      <span className="stream-cursor" aria-hidden="true" />
                    )}
                  </p>
                </li>
              ))}
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
        {(error || sendError || state?.run?.error) && (
          <div className="error-notice" role="alert">
            <AlertTriangle size={16} />
            <span>{error || sendError || state?.run?.error}</span>
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
            Scripted agent
          </span>
          <span>Synthetic data only</span>
        </div>
      </div>
    </main>
  )
}

export default function App() {
  const { sessionId } = useParams({ strict: false })
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<Session[]>([])
  const [creating, setCreating] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    async function refresh() {
      try {
        const items = await request<Session[]>('/sessions', {
          signal: controller.signal,
        })
        setSessions(items)
        setError(null)
      } catch (reason) {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error ? reason.message : 'Sessions unavailable',
          )
      }
    }
    void refresh()
    window.addEventListener('focus', refresh)
    return () => {
      controller.abort()
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
      replace: true,
    })
  }, [sessionId, sessions, navigate])

  async function createSession() {
    if (creating) return
    setCreating(true)
    try {
      const session = await request<Session>('/sessions', { method: 'POST' })
      setSessions((current) => [...current, session])
      setDrawerOpen(false)
      setError(null)
      await navigate({
        to: '/sessions/$sessionId',
        params: { sessionId: session.id },
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
              <span>LOCAL</span>
              <span className="environment-dot" />
              Scripted
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
              <Chat
                key={sessionId}
                sessionId={sessionId}
                name={
                  selectedIndex < 0 ? 'Session' : sessionName(selectedIndex)
                }
              />
            ) : (
              <main className="loading-panel">
                <LoaderCircle className="spin" aria-label="Loading sessions" />
              </main>
            )}
            <aside className="working-panel" aria-label="Working surface">
              <header className="panel-heading">
                <h2>Working surface</h2>
                <PanelRight size={16} />
              </header>
            </aside>
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

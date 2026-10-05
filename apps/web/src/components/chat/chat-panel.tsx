import { Link } from '@tanstack/react-router'
import { ArrowDown, Dna, FlaskConical, Hash } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { PrivacyBinding } from '../../lib/api'
import { toolView } from '../../lib/events'
import type { ChatMessage, Projection, RefusedState, StepState } from '../../lib/events'
import type { PushedView } from '../../lib/views'
import { cn } from '../../lib/utils'
import { EmptyState } from '../ui/empty-state'
import { IconButton } from '../ui/icon-button'
import { Notice } from '../ui/notice'
import { PanelHeader } from '../ui/panel-header'
import { Spinner } from '../ui/spinner'
import { Composer } from './composer'
import { RefusalChip } from './refusal-chip'
import { StepMarker } from './step-marker'
import { TranscriptText } from './transcript-text'
import type { ViewLink } from './transcript-text'
import { TurnStatus } from './turn-status'
import type { Connection, TurnStatusLabel } from './turn-status'
import { ViewReference } from './view-reference'

function turnStatus(state: Projection | null, connection: Connection): TurnStatusLabel {
  if (connection === 'connecting') return 'Connecting'
  if (connection === 'reconnecting') return 'Reconnecting'
  const turn = state?.conversation_turn
  if (turn?.status === 'running') return 'Responding'
  if (turn?.status === 'failed') return 'Failed'
  return turn ? 'Complete' : 'Ready'
}

type Entry =
  | { kind: 'message'; value: ChatMessage }
  | { kind: 'steps'; value: StepState[] }
  | { kind: 'refusal'; value: RefusedState }
  | { kind: 'view'; value: PushedView }

/** Messages, steps, refusals and unreferenced views in log order; consecutive steps form one group. */
function timeline(state: Projection): Entry[] {
  const linked = new Set(state.steps.flatMap((step) => (step.tools ?? []).flatMap((tool) => toolView(tool)?.id ?? [])))
  const items = [
    ...state.messages.map((value) => ({ kind: 'message' as const, value })),
    ...state.steps.map((value) => ({ kind: 'step' as const, value })),
    ...(state.refusals ?? []).map((value) => ({ kind: 'refusal' as const, value })),
    ...state.views.filter((view) => !linked.has(view.id)).map((value) => ({ kind: 'view' as const, value })),
  ].sort((first, second) => first.value.seq - second.value.seq)
  const entries: Entry[] = []
  for (const item of items) {
    const last = entries.at(-1)
    if (item.kind === 'step' && last?.kind === 'steps') last.value.push(item.value)
    else if (item.kind === 'step') entries.push({ kind: 'steps', value: [item.value] })
    else entries.push(item)
  }
  return entries
}

export function ChatPanel({
  sessionId,
  name,
  state,
  bindings,
  connection,
  error,
  onSend,
  className,
}: {
  sessionId: string
  name: string
  state: Projection | null
  bindings: PrivacyBinding[]
  connection: Connection
  error?: string | null
  onSend: (text: string) => Promise<void>
  className?: string
}) {
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [atBottom, setAtBottom] = useState(true)
  const scrollArea = useRef<HTMLDivElement>(null)
  const status = turnStatus(state, connection)
  const canSend = Boolean(state && connection === 'live' && status !== 'Responding' && !sending && draft.trim())
  const views = state?.views ?? []
  const problem = error || sendError || state?.conversation_turn?.error

  const viewLink: ViewLink = (viewId, children: ReactNode) =>
    views.some((view) => view.id === viewId) ? (
      <Link
        data-testid="view-link"
        data-view-id={viewId}
        to="/sessions/$sessionId"
        params={{ sessionId }}
        search={{ view: viewId, panel: 'surface' }}
        className="text-accent underline decoration-dotted underline-offset-2 hover:decoration-solid"
      >
        {children}
      </Link>
    ) : (
      children
    )

  useEffect(() => {
    if (atBottom && scrollArea.current) scrollArea.current.scrollTop = scrollArea.current.scrollHeight
  }, [state?.seq, atBottom])

  async function send() {
    if (!canSend) return
    const text = draft
    setSending(true)
    setSendError(null)
    setAtBottom(true)
    try {
      await onSend(text)
      setDraft((current) => (current === text ? '' : current))
    } catch (reason) {
      setSendError(reason instanceof Error ? reason.message : 'Message could not be sent')
    } finally {
      setSending(false)
    }
  }

  return (
    <section id="conversation-panel" aria-label="Conversation" className={cn('@container flex min-h-0 min-w-0 flex-1 flex-col bg-surface', className)}>
      <PanelHeader
        title="Conversation"
        subtitle={name}
        subtitleTestId="session-title"
        actions={
          <>
            <TurnStatus status={status} />
            <span title="Last event sequence" className="hidden items-center gap-0.5 font-mono text-xs @narrow:inline-flex">
              <Hash aria-hidden className="size-icon-sm" />
              {String(state?.seq ?? 0).padStart(4, '0')}
            </span>
          </>
        }
      />
      <div className="relative min-h-0 flex-1">
        <div
          ref={scrollArea}
          className="h-full overflow-y-auto overscroll-contain"
          onScroll={(event) => {
            const area = event.currentTarget
            setAtBottom(area.scrollHeight - area.scrollTop - area.clientHeight < 80)
          }}
        >
          {!state ? (
            <div role="status" className="flex h-full items-center justify-center gap-2 text-sm text-muted">
              <Spinner />
              Opening conversation…
            </div>
          ) : !state.messages.length ? (
            <EmptyState
              icon={Dna}
              display
              eyebrow={name}
              title="A new conversation"
              description="Ask about specimens, libraries, sequencing runs or analysis jobs."
              className="h-full"
            />
          ) : (
            <ol aria-label="Conversation" className="mx-auto flex max-w-prose flex-col gap-6 px-4 py-6 @medium:px-6 @medium:py-8">
              {timeline(state).map((entry) => {
                if (entry.kind === 'view') {
                  return (
                    <li key={`view:${entry.value.id}`} className="min-w-0 animate-enter">
                      <ViewReference sessionId={sessionId} view={entry.value} />
                    </li>
                  )
                }
                if (entry.kind === 'refusal') {
                  return (
                    <li key={`refusal:${entry.value.id}`} className="min-w-0 animate-enter">
                      <RefusalChip refusal={entry.value} />
                    </li>
                  )
                }
                if (entry.kind === 'steps') {
                  return (
                    <li key={`steps:${entry.value[0].id}`} className="flex min-w-0 flex-col gap-0.5">
                      {entry.value.map((step) => <StepMarker key={step.id} step={step} viewLink={viewLink} />)}
                    </li>
                  )
                }
                const message = entry.value
                return (
                  <li
                    key={message.id}
                    data-testid={`${message.role}-message`}
                    className={
                      message.role === 'user'
                        ? 'ml-8 min-w-0 self-end rounded-lg bg-muted px-4 py-2 text-default animate-enter'
                        : 'min-w-0 text-default animate-enter'
                    }
                  >
                    <TranscriptText
                      text={message.text}
                      role={message.role}
                      bindings={bindings}
                      viewLink={viewLink}
                      streaming={message.status === 'streaming'}
                    />
                    {message.status === 'failed' && <p className="mt-1 text-xs text-danger">Interrupted</p>}
                  </li>
                )
              })}
            </ol>
          )}
        </div>
        {!atBottom && (
          <IconButton
            variant="secondary"
            label="Latest message"
            icon={ArrowDown}
            className="absolute bottom-3 left-1/2 -translate-x-1/2 shadow-sm"
            onClick={() => setAtBottom(true)}
          />
        )}
      </div>
      <div className="mx-auto w-full max-w-prose shrink-0 px-4 pb-4 @medium:px-6 @medium:pb-6">
        {problem && <Notice tone="danger" role="alert" className="mb-3">{problem}</Notice>}
        <Composer value={draft} onChange={setDraft} onSubmit={() => void send()} disabled={!state} canSend={canSend} />
        <footer data-testid="composer-footer" className="mt-2 flex flex-wrap justify-between gap-x-4 gap-y-1 text-xs text-muted">
          <span className="inline-flex items-center gap-1.5">
            <FlaskConical aria-hidden className="size-icon-sm" />
            Genomics agent
          </span>
          <span>Synthetic data only</span>
        </footer>
      </div>
    </section>
  )
}

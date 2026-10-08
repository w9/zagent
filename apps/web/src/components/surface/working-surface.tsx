import { ArrowRightToLine, ChevronLeft, ChevronRight, Table2 } from 'lucide-react'
import { Component, useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import type { DraftState, JobState } from '../../lib/events'
import { plural } from '../../lib/format'
import { cn } from '../../lib/utils'
import { selectionAt, viewPosition } from '../../lib/views'
import type { PushedView } from '../../lib/views'
import { Button } from '../ui/button'
import { EmptyState } from '../ui/empty-state'
import { Select } from '../ui/field'
import { IconButton } from '../ui/icon-button'
import { Notice } from '../ui/notice'
import { PanelHeader } from '../ui/panel-header'
import { ViewRenderer } from './view-renderer'
import type { HandleResolver } from './views/table.view'

class ViewBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    return this.state.error ? (
      <Notice tone="danger" role="alert" title="View unavailable">{this.state.error.message}</Notice>
    ) : (
      this.props.children
    )
  }
}

const viewTitle = (view: PushedView) => (typeof view.spec.props.title === 'string' ? view.spec.props.title : view.spec.kind)

export function WorkingSurface({
  sessionId,
  views,
  selectedId,
  onSelect,
  drafts,
  jobs,
  resolveHandle,
  readOnly,
  className,
}: {
  sessionId?: string
  views: PushedView[]
  selectedId?: string
  onSelect: (id: string | undefined) => void
  drafts?: Record<string, DraftState>
  jobs?: Record<string, JobState>
  resolveHandle?: HandleResolver
  readOnly?: boolean
  className?: string
}) {
  const position = viewPosition(views, selectedId)
  const active = views[position]
  const atHead = position === views.length - 1
  const content = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (selectedId) content.current?.focus({ preventScroll: true })
  }, [selectedId, active?.id])

  const select = (index: number) => onSelect(selectionAt(views, index))

  return (
    <aside id="working-surface" aria-label="Working surface" className={cn('@container flex min-h-0 min-w-0 flex-1 flex-col bg-subtle', className)}>
      <PanelHeader title="Working surface" subtitle={plural(views.length, 'view', 'views')} actions={<Table2 aria-hidden className="size-icon" />} />
      {active ? (
        <>
          <nav aria-label="View navigation" className="flex shrink-0 items-center gap-1 border-b border-subtle px-2 py-2 @medium:px-4">
            <IconButton label="Previous view" icon={ChevronLeft} disabled={position <= 0} onClick={() => select(position - 1)} />
            <div className="flex min-w-0 flex-1 flex-col gap-0.5 px-1">
              <label htmlFor="view-history" className="sr-only">View history</label>
              <Select
                id="view-history"
                value={active.id}
                className="h-control-sm text-sm"
                onChange={(event) => select(views.findIndex((view) => view.id === event.target.value))}
              >
                {views.map((view, index) => <option key={view.id} value={view.id}>{index + 1}. {viewTitle(view)}</option>)}
              </Select>
              <span data-testid="view-position" className="font-mono text-xs text-muted">
                View {position + 1} of {views.length}
              </span>
            </div>
            <IconButton label="Next view" icon={ChevronRight} disabled={atHead} onClick={() => select(position + 1)} />
            <IconButton
              label="Latest view"
              icon={ArrowRightToLine}
              disabled={atHead && selectedId === undefined}
              onClick={() => select(views.length - 1)}
            />
          </nav>
          <div
            ref={content}
            tabIndex={-1}
            key={active.id}
            data-testid="active-view"
            data-view-id={active.id}
            className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-6 -outline-offset-2 animate-fade @medium:px-6"
          >
            <ViewBoundary>
              <ViewRenderer
                spec={active.spec}
                viewId={active.id}
                sessionId={sessionId}
                drafts={drafts}
                jobs={jobs}
                onConfirmed={() => onSelect(undefined)}
                resolveHandle={resolveHandle}
                readOnly={readOnly}
              />
            </ViewBoundary>
          </div>
        </>
      ) : selectedId ? (
        <div ref={content} tabIndex={-1} className="px-4 py-6 -outline-offset-2 @medium:px-6">
          <Notice
            tone="danger"
            role="alert"
            title="View unavailable"
            action={<Button size="sm" icon={ArrowRightToLine} onClick={() => onSelect(undefined)}>Latest view</Button>}
          >
            This view is not available in this session.
          </Notice>
        </div>
      ) : (
        <EmptyState
          icon={Table2}
          title="No views yet"
          description="Tables, charts and analysis drafts the agent publishes appear here."
          className="flex-1"
        />
      )}
    </aside>
  )
}

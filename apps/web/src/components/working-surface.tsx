import {
  ArrowRightToLine,
  ChevronLeft,
  ChevronRight,
  Table2,
} from 'lucide-react'
import { Component } from 'react'
import type { ReactNode } from 'react'
import { request } from '../lib/api'
import { selectionAt, viewPosition } from '../lib/views'
import type { PushedView, TableData } from '../lib/views'
import { IconButton } from './ui/icon-button'
import { ViewRenderer } from './view-renderer'

class ViewBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    return this.state.error ? (
      <div className="surface-error" role="alert">
        <h3>View unavailable</h3>
        <p>{this.state.error.message}</p>
      </div>
    ) : (
      this.props.children
    )
  }
}

export function WorkingSurface({
  sessionId,
  views,
  selectedId,
  onSelect,
}: {
  sessionId?: string
  views: PushedView[]
  selectedId?: string
  onSelect: (id: string | undefined) => void
}) {
  const position = viewPosition(views, selectedId)
  const active = views[position]
  const atHead = position === views.length - 1

  function select(index: number) {
    onSelect(selectionAt(views, index))
  }

  return (
    <aside
      className="working-panel"
      id="working-surface"
      aria-label="Working surface"
    >
      <header className="panel-heading surface-heading">
        <div>
          <h2>Working surface</h2>
          <span className="session-subtitle">
            {views.length} {views.length === 1 ? 'view' : 'views'}
          </span>
        </div>
        <Table2 size={17} aria-hidden="true" />
      </header>
      {active ? (
        <>
          <nav className="view-navigation" aria-label="View navigation">
            <IconButton
              label="Previous view"
              disabled={position <= 0}
              onClick={() => select(position - 1)}
            >
              <ChevronLeft />
            </IconButton>
            <div className="view-history">
              <label htmlFor="view-history" className="sr-only">
                View history
              </label>
              <select
                id="view-history"
                value={active.id}
                onChange={(event) =>
                  select(
                    views.findIndex((view) => view.id === event.target.value),
                  )
                }
              >
                {views.map((view, index) => (
                  <option key={view.id} value={view.id}>
                    {index + 1}.{' '}
                    {typeof view.spec.props.title === 'string'
                      ? view.spec.props.title
                      : view.spec.kind}
                  </option>
                ))}
              </select>
              <span data-testid="view-position">
                View {position + 1} of {views.length}
              </span>
            </div>
            <IconButton
              label="Next view"
              disabled={atHead}
              onClick={() => select(position + 1)}
            >
              <ChevronRight />
            </IconButton>
            <IconButton
              label="Latest view"
              disabled={atHead}
              onClick={() => select(views.length - 1)}
            >
              <ArrowRightToLine />
            </IconButton>
          </nav>
          <div
            className="surface-content"
            key={active.id}
            data-testid="active-view"
            data-view-id={active.id}
          >
            <ViewBoundary>
              <ViewRenderer
                spec={active.spec}
                resolveHandle={sessionId ? (handle, signal) => request<TableData>(
                  `/sessions/${sessionId}/handles/${encodeURIComponent(handle)}`, { signal },
                ) : undefined}
              />
            </ViewBoundary>
          </div>
        </>
      ) : (
        <div className="empty-surface">
          <Table2 size={28} strokeWidth={1.3} aria-hidden="true" />
          <span>No views yet</span>
        </div>
      )}
    </aside>
  )
}

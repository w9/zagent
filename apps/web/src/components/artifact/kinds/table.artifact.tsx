import { Check, Maximize2, RefreshCw, X } from 'lucide-react'
import { useEffect, useEffectEvent, useState } from 'react'
import { plural } from '../../../lib/format'
import { cn } from '../../../lib/utils'
import { validateArtifactSpec } from '../../../lib/artifacts'
import type { ArtifactSpec, TableCell, TableColumn, TableData, TableProps, TableSpec } from '../../../lib/artifacts'
import { Button } from '../../ui/button'
import { Notice } from '../../ui/notice'
import { Spinner } from '../../ui/spinner'
import { ArtifactMeta } from '../artifact-meta'
import type { ArtifactDisplay, ArtifactRendererProps } from '../artifact-renderer'

export type HandleResolver = (handle: string, signal: AbortSignal) => Promise<TableData>

/** Rows a table card shows in the conversation; the maximized table shows them all. */
export const PREVIEW_ROWS = 5

const headerClassNames: Record<TableColumn['type'], string> = {
  string: 'text-left',
  number: 'text-right',
  boolean: 'text-left',
}
const cellClassNames: Record<TableColumn['type'], string> = {
  string: 'wrap-anywhere',
  number: 'text-right font-mono tabular-nums whitespace-nowrap',
  boolean: 'whitespace-nowrap',
}

function Cell({ value }: { value: TableCell }) {
  if (value === null) return <span className="text-muted">n/a</span>
  if (typeof value === 'boolean') {
    return (
      <span className="inline-flex items-center gap-1">
        {value ? <Check aria-hidden className="size-icon-sm text-success" /> : <X aria-hidden className="size-icon-sm text-muted" />}
        {value ? 'Yes' : 'No'}
      </span>
    )
  }
  return String(value)
}

function TableContent({
  props,
  display,
  data,
  pending = false,
  error,
  retry,
  onMaximize,
}: {
  props: TableProps
  display: ArtifactDisplay
  data?: TableData
  pending?: boolean
  error?: string
  retry?: () => void
  onMaximize?: () => void
}) {
  const inline = display === 'inline'
  const rows = inline ? (data?.rows ?? []).slice(0, PREVIEW_ROWS) : (data?.rows ?? [])
  const count = data?.row_count ?? props.row_count
  return (
    <section aria-label={props.title} className="flex min-w-0 flex-col">
      {!inline && <ArtifactMeta>{plural(count, 'row', 'rows')}</ArtifactMeta>}
      <div
        role="region"
        aria-label={`${props.title} data`}
        tabIndex={0}
        data-testid="table-scroll"
        className="overflow-x-auto rounded-md border border-subtle bg-surface"
      >
        <table className="w-full min-w-96 border-collapse text-sm">
          <caption className="sr-only">{props.title}</caption>
          <thead>
            <tr>
              {props.columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={cn('border-b border-subtle bg-subtle px-3 py-2 text-xs font-medium whitespace-nowrap text-muted', headerClassNames[column.type])}
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pending || error || rows.length === 0 ? (
              <tr>
                <td colSpan={props.columns.length} className="px-3 py-10 text-center text-muted">
                  {pending ? (
                    <span role="status" className="inline-flex items-center gap-2"><Spinner />Loading data…</span>
                  ) : error ? (
                    <Notice
                      tone="danger"
                      role="alert"
                      className="mx-auto w-fit max-w-full text-left"
                      action={retry && <Button size="sm" icon={RefreshCw} onClick={retry}>Retry</Button>}
                    >
                      {error}
                    </Notice>
                  ) : (
                    'No records'
                  )}
                </td>
              </tr>
            ) : (
              rows.map((row, rowIndex) => (
                <tr key={rowIndex} className="transition-colors hover:bg-hover [&:last-child>td]:border-b-0">
                  {props.columns.map((column, columnIndex) => (
                    <td
                      key={column.key}
                      className={cn(
                        'max-w-64 border-b border-subtle px-3 py-2 align-top text-default',
                        cellClassNames[column.type],
                        columnIndex === 0 && 'font-mono text-xs whitespace-nowrap',
                      )}
                    >
                      <Cell value={row[columnIndex]} />
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {!pending && !error && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-muted">
          <span>
            {rows.length < count
              ? `${rows.length} of ${count.toLocaleString('en-US')} rows shown`
              : `${plural(rows.length, 'row', 'rows')} shown`}
          </span>
          {inline && onMaximize && rows.length < (data?.rows.length ?? 0) ? (
            <Button size="sm" variant="ghost" icon={Maximize2} onClick={onMaximize}>Show all rows</Button>
          ) : (
            <span>{props.handle ? 'Query result' : 'Inline snapshot'}</span>
          )}
        </div>
      )}
    </section>
  )
}

function HandleTable({ spec, resolveHandle, display, onMaximize }: {
  spec: TableSpec; resolveHandle: HandleResolver; display: ArtifactDisplay; onMaximize?: () => void
}) {
  const [state, setState] = useState<{ data?: TableData; error?: string }>({})
  const [attempt, setAttempt] = useState(0)
  const props = spec.props
  const handle = props.handle!
  const resolve = useEffectEvent(resolveHandle)
  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      try {
        const source = await resolve(handle, controller.signal)
        const data = {
          ...source,
          rows: source.columns
            ? source.rows.map((row) => props.columns.map((column) => {
                const index = source.columns!.findIndex((item) => item.key === column.key)
                if (index < 0) throw new Error('Artifact schema error: missing query column')
                return row[index]
              }))
            : source.rows,
        }
        const inline: ArtifactSpec = {
          kind: 'table',
          version: 1,
          props: { title: props.title, columns: props.columns, rows: data.rows, row_count: data.row_count },
        }
        validateArtifactSpec(inline)
        if (!controller.signal.aborted) setState({ data })
      } catch (reason) {
        if (!controller.signal.aborted) setState({ error: reason instanceof Error ? reason.message : 'Data unavailable' })
      }
    }
    void load()
    return () => controller.abort()
  }, [handle, props.title, props.columns, attempt])
  return (
    <TableContent
      props={props}
      display={display}
      onMaximize={onMaximize}
      data={state.data}
      error={state.error}
      pending={!state.data && !state.error}
      retry={() => {
        setState({})
        setAttempt((value) => value + 1)
      }}
    />
  )
}

function TableArtifact({ spec, resolveHandle, display, onMaximize }: ArtifactRendererProps) {
  const table = spec as TableSpec
  if (table.props.rows) {
    return (
      <TableContent
        props={table.props}
        display={display}
        onMaximize={onMaximize}
        data={{ rows: table.props.rows, row_count: table.props.row_count }}
      />
    )
  }
  if (!resolveHandle) return <TableContent props={table.props} display={display} error="Data source unavailable." />
  return <HandleTable key={table.props.handle} spec={table} resolveHandle={resolveHandle} display={display} onMaximize={onMaximize} />
}

TableArtifact.kind = 'table'
TableArtifact.version = 1

export default TableArtifact

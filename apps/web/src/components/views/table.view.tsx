import { Check, RefreshCw, X } from 'lucide-react'
import { useEffect, useEffectEvent, useState } from 'react'
import { Button } from '../ui/button'
import { validateViewSpec } from '../../lib/views'
import type {
  TableData,
  TableProps,
  TableSpec,
  ViewSpec,
} from '../../lib/views'
import type { ViewRendererProps } from '../view-renderer'

export type HandleResolver = (
  handle: string,
  signal: AbortSignal,
) => Promise<TableData>

function TableContent({
  props,
  data,
  pending = false,
  error,
  retry,
}: {
  props: TableProps
  data?: TableData
  pending?: boolean
  error?: string
  retry?: () => void
}) {
  const rows = data?.rows ?? []
  const count = data?.row_count ?? props.row_count
  return (
    <section className="table-view" aria-label={props.title}>
      <div className="table-view-heading">
        <span className="view-kind">Table</span>
        <h3>{props.title}</h3>
        <span className="table-count">
          {count.toLocaleString('en-US')} {count === 1 ? 'row' : 'rows'}
        </span>
      </div>
      <div
        className="data-table-scroll"
        tabIndex={0}
        role="region"
        aria-label={`${props.title} data`}
      >
        <table className="data-table">
          <caption className="sr-only">{props.title}</caption>
          <thead>
            <tr>
              {props.columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={`cell-${column.type}`}
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pending || error || rows.length === 0 ? (
              <tr>
                <td colSpan={props.columns.length} className="table-state">
                  {pending ? (
                    <span role="status">Loading data...</span>
                  ) : error ? (
                    <div role="alert">
                      <span>{error}</span>
                      {retry && (
                        <Button variant="ghost" onClick={retry}>
                          <RefreshCw />
                          Retry
                        </Button>
                      )}
                    </div>
                  ) : (
                    'No records'
                  )}
                </td>
              </tr>
            ) : (
              rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {props.columns.map((column, columnIndex) => {
                    const cell = row[columnIndex]
                    return (
                      <td key={column.key} className={`cell-${column.type}`}>
                        {cell === null ? (
                          <span className="null-cell">n/a</span>
                        ) : typeof cell === 'boolean' ? (
                          <span className="boolean-cell">
                            {cell ? (
                              <Check size={13} aria-hidden="true" />
                            ) : (
                              <X size={13} aria-hidden="true" />
                            )}
                            {cell ? 'Yes' : 'No'}
                          </span>
                        ) : (
                          String(cell)
                        )}
                      </td>
                    )
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {!pending && !error && (
        <div className="table-view-footer">
          <span>
            {rows.length < count
              ? `${rows.length} of ${count.toLocaleString('en-US')} rows shown`
              : `${rows.length} ${rows.length === 1 ? 'row' : 'rows'} shown`}
          </span>
          <span>{props.handle ? 'Query result' : 'Inline snapshot'}</span>
        </div>
      )}
    </section>
  )
}

function HandleTable({
  spec,
  resolveHandle,
}: {
  spec: TableSpec
  resolveHandle: HandleResolver
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
                if (index < 0) throw new Error('View schema error: missing query column')
                return row[index]
              }))
            : source.rows,
        }
        const inline: ViewSpec = {
          kind: 'table',
          version: 1,
          props: {
            title: props.title,
            columns: props.columns,
            rows: data.rows,
            row_count: data.row_count,
          },
        }
        validateViewSpec(inline)
        if (!controller.signal.aborted) setState({ data })
      } catch (reason) {
        if (!controller.signal.aborted)
          setState({
            error:
              reason instanceof Error ? reason.message : 'Data unavailable',
          })
      }
    }
    void load()
    return () => controller.abort()
  }, [handle, props.title, props.columns, attempt])
  return (
    <TableContent
      props={props}
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

function TableView({ spec, resolveHandle }: ViewRendererProps) {
  const table = spec as TableSpec
  if (table.props.rows)
    return (
      <TableContent
        props={table.props}
        data={{ rows: table.props.rows, row_count: table.props.row_count }}
      />
    )
  if (!resolveHandle)
    return <TableContent props={table.props} error="Data source unavailable." />
  return (
    <HandleTable
      key={table.props.handle}
      spec={table}
      resolveHandle={resolveHandle}
    />
  )
}

TableView.kind = 'table'
TableView.version = 1

export default TableView

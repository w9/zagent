import { RefreshCw } from 'lucide-react'
import { useEffect, useEffectEvent, useRef, useState } from 'react'
import type { VisualizationSpec } from 'vega-embed'
import { validateViewSpec } from '../../lib/views'
import type { ChartSpec } from '../../lib/views'
import type { ViewRendererProps } from '../view-renderer'
import { Button } from '../ui/button'

function ChartView({ spec, resolveHandle }: ViewRendererProps) {
  const props = (spec as ChartSpec).props
  const target = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<{ count?: number; error?: string }>({})
  const [attempt, setAttempt] = useState(0)
  const resolve = useEffectEvent((signal: AbortSignal) => {
    if (!resolveHandle) throw new Error('Data source unavailable.')
    return resolveHandle(props.handle, signal)
  })

  useEffect(() => {
    const controller = new AbortController()
    const element = target.current!
    let chart: Awaited<ReturnType<typeof import('vega-embed').default>> | undefined
    let observer: ResizeObserver | undefined
    element.replaceChildren()

    async function load() {
      try {
        const data = await resolve(controller.signal)
        if (!data.columns) throw new Error('Query column metadata is missing')
        validateViewSpec({
          kind: 'table', version: 1,
          props: {
            title: props.title, columns: data.columns,
            rows: data.rows, row_count: data.row_count,
          },
        })
        if (Object.values(props.encoding).some((channel) =>
          !data.columns!.some((column) => column.key === channel.field),
        )) throw new Error('Chart field is missing from the query schema')
        if (controller.signal.aborted) return
        if (data.rows.length) {
          const { default: embed } = await import('vega-embed')
          if (controller.signal.aborted) return
          const values = data.rows.map((row) => Object.fromEntries(
            data.columns!.map((column, index) => [column.key, row[index]]),
          ))
          chart = await embed(element, {
            $schema: 'https://vega.github.io/schema/vega-lite/v6.json',
            width: 'container', height: 280,
            autosize: { type: 'fit', contains: 'padding' },
            background: 'transparent',
            data: { values }, mark: props.mark, encoding: props.encoding,
            config: {
              font: 'DM Sans Variable',
              view: { stroke: null },
              axis: { labelLimit: 90, labelColor: '#62715a', titleColor: '#344d3c' },
              range: { category: ['#5b8772', '#bc694a', '#6f8299', '#a89458'] },
              bar: { color: '#5b8772' },
            },
          } as VisualizationSpec, {
            actions: false, renderer: 'svg', tooltip: false,
            loader: {
              load: async () => { throw new Error('External chart data is disabled') },
              sanitize: async () => { throw new Error('External chart URLs are disabled') },
              http: async () => { throw new Error('External chart HTTP is disabled') },
              file: async () => { throw new Error('External chart files are disabled') },
            },
          })
          if (controller.signal.aborted) {
            chart.finalize()
            return
          }
          if (typeof ResizeObserver !== 'undefined') {
            observer = new ResizeObserver(() => { void chart?.view.resize().runAsync() })
            observer.observe(element)
          }
        }
        setState({ count: data.row_count })
      } catch (error) {
        if (!controller.signal.aborted) setState({
          error: error instanceof Error ? error.message : 'Chart unavailable',
        })
      }
    }
    void load()
    return () => {
      controller.abort()
      observer?.disconnect()
      chart?.finalize()
    }
  }, [props, attempt])

  return (
    <section className="chart-view" aria-label={props.title}>
      <div className="table-view-heading">
        <span className="view-kind">Chart</span>
        <h3>{props.title}</h3>
        {state.count !== undefined && <span className="table-count">
          {state.count} {state.count === 1 ? 'row' : 'rows'}
        </span>}
      </div>
      {state.error ? <div className="surface-error" role="alert">
        <p>{state.error}</p>
        <Button variant="ghost" onClick={() => {
          setState({})
          setAttempt((value) => value + 1)
        }}><RefreshCw />Retry</Button>
      </div> : state.count === undefined ? <p role="status">Loading data...</p>
        : state.count === 0 ? <p>No records</p> : null}
      <div className="chart-canvas" ref={target} aria-label={`${props.title} plot`} />
    </section>
  )
}

ChartView.kind = 'chart'
ChartView.version = 1

export default ChartView
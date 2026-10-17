import { RefreshCw } from 'lucide-react'
import { useEffect, useEffectEvent, useRef, useState } from 'react'
import type { VisualizationSpec } from 'vega-embed'
import { plural } from '../../../lib/format'
import { useTheme } from '../../../lib/theme'
import { validateArtifactSpec } from '../../../lib/artifacts'
import type { ChartSpec } from '../../../lib/artifacts'
import { Button } from '../../ui/button'
import { Notice } from '../../ui/notice'
import { Spinner } from '../../ui/spinner'
import { ArtifactMeta } from '../artifact-meta'
import type { ArtifactRendererProps } from '../artifact-renderer'

/** Vega config from the current theme's tokens (DESIGN.md section 7). */
function chartConfig() {
  const style = getComputedStyle(document.documentElement)
  const token = (name: string) => style.getPropertyValue(name).trim() || undefined
  const pixels = (name: string) => Number.parseFloat(token(name) ?? '') || undefined
  const axis = {
    labelColor: token('--text-color-muted'),
    titleColor: token('--text-color-default'),
    gridColor: token('--border-color-subtle'),
    domainColor: token('--border-color-default'),
    tickColor: token('--border-color-default'),
    labelFontSize: pixels('--text-xs'),
    titleFontSize: pixels('--text-sm'),
    labelLimit: 90,
  }
  const series = [1, 2, 3, 4, 5, 6].map((index) => token(`--chart-${index}`))
  return {
    font: token('--font-sans'),
    view: { stroke: null },
    axis,
    legend: { labelColor: axis.labelColor, titleColor: axis.titleColor, labelFontSize: axis.labelFontSize },
    range: { category: series },
    mark: { color: series[0] },
  }
}

function ChartArtifact({ spec, resolveHandle, display }: ArtifactRendererProps) {
  const props = (spec as ChartSpec).props
  const target = useRef<HTMLDivElement>(null)
  const theme = useTheme()
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
        validateArtifactSpec({
          kind: 'table', version: 1,
          props: { title: props.title, columns: data.columns, rows: data.rows, row_count: data.row_count },
        })
        if (Object.values(props.encoding).some((channel) => !data.columns!.some((column) => column.key === channel.field)))
          throw new Error('Chart field is missing from the query schema')
        if (controller.signal.aborted) return
        if (data.rows.length) {
          const { default: embed } = await import('vega-embed')
          if (controller.signal.aborted) return
          const values = data.rows.map((row) => Object.fromEntries(data.columns!.map((column, index) => [column.key, row[index]])))
          chart = await embed(element, {
            $schema: 'https://vega.github.io/schema/vega-lite/v6.json',
            width: 'container', height: 'container',
            autosize: { type: 'fit', contains: 'padding' },
            background: 'transparent',
            data: { values }, mark: props.mark, encoding: props.encoding,
            config: chartConfig(),
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
        if (!controller.signal.aborted) setState({ error: error instanceof Error ? error.message : 'Chart unavailable' })
      }
    }
    void load()
    return () => {
      controller.abort()
      observer?.disconnect()
      chart?.finalize()
    }
  }, [props, attempt, theme])

  return (
    <section aria-label={props.title} className="flex min-w-0 flex-col">
      {display === 'maximized' && state.count !== undefined && <ArtifactMeta>{plural(state.count, 'row', 'rows')}</ArtifactMeta>}
      {state.error ? (
        <Notice
          tone="danger"
          role="alert"
          action={<Button size="sm" icon={RefreshCw} onClick={() => { setState({}); setAttempt((value) => value + 1) }}>Retry</Button>}
        >
          {state.error}
        </Notice>
      ) : state.count === undefined ? (
        <p role="status" className="inline-flex items-center gap-2 text-sm text-muted"><Spinner />Loading data…</p>
      ) : state.count === 0 ? (
        <p className="text-sm text-muted">No records</p>
      ) : null}
      <div
        ref={target}
        data-testid="chart-canvas"
        aria-label={`${props.title} plot`}
        className={state.error || state.count === 0 ? 'hidden' : 'h-chart w-full min-w-0 overflow-hidden'}
      />
    </section>
  )
}

ChartArtifact.kind = 'chart'
ChartArtifact.version = 1

export default ChartArtifact

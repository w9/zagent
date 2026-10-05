import { AppBridge, PostMessageTransport } from '@modelcontextprotocol/ext-apps/app-bridge'
import type { McpUiHostContext, McpUiStyles } from '@modelcontextprotocol/ext-apps/app-bridge'
import { useEffect, useEffectEvent, useRef, useState } from 'react'
import { request } from '../../lib/api'
import { useTheme } from '../../lib/theme'
import type { Theme } from '../../lib/theme'
import { Notice } from '../ui/notice'
import { Spinner } from '../ui/spinner'
import type { ViewRendererProps } from './view-renderer'

type JobsPayload = Record<string, unknown>

// DESIGN.md section 6: MCP Apps style variables and the tokens that fill them.
const mcpVariables: Record<string, string> = {
  '--color-background-primary': '--background-color-surface',
  '--color-background-secondary': '--background-color-subtle',
  '--color-background-tertiary': '--background-color-muted',
  '--color-background-inverse': '--background-color-inverse',
  '--color-background-info': '--background-color-info-subtle',
  '--color-background-danger': '--background-color-danger-subtle',
  '--color-background-success': '--background-color-success-subtle',
  '--color-background-warning': '--background-color-warning-subtle',
  '--color-text-primary': '--text-color-default',
  '--color-text-secondary': '--text-color-muted',
  '--color-text-tertiary': '--text-color-muted',
  '--color-text-inverse': '--text-color-inverse',
  '--color-text-disabled': '--text-color-muted',
  '--color-text-info': '--text-color-info',
  '--color-text-danger': '--text-color-danger',
  '--color-text-success': '--text-color-success',
  '--color-text-warning': '--text-color-warning',
  '--color-border-primary': '--border-color-default',
  '--color-border-secondary': '--border-color-subtle',
  '--color-border-tertiary': '--border-color-subtle',
  '--color-border-info': '--border-color-info',
  '--color-border-danger': '--border-color-danger',
  '--color-border-success': '--border-color-success',
  '--color-border-warning': '--border-color-warning',
  '--color-ring-primary': '--outline-color-focus',
  '--font-sans': '--font-sans',
  '--font-mono': '--font-mono',
  '--font-weight-normal': '--font-weight-normal',
  '--font-weight-medium': '--font-weight-medium',
  '--font-weight-semibold': '--font-weight-semibold',
  '--font-text-xs-size': '--text-xs',
  '--font-text-xs-line-height': '--text-xs--line-height',
  '--font-text-sm-size': '--text-sm',
  '--font-text-sm-line-height': '--text-sm--line-height',
  '--font-text-md-size': '--text-base',
  '--font-text-md-line-height': '--text-base--line-height',
  '--font-text-lg-size': '--text-md',
  '--font-text-lg-line-height': '--text-md--line-height',
  '--font-heading-sm-size': '--text-base',
  '--font-heading-sm-line-height': '--text-base--line-height',
  '--font-heading-md-size': '--text-lg',
  '--font-heading-md-line-height': '--text-lg--line-height',
  '--font-heading-lg-size': '--text-xl',
  '--font-heading-lg-line-height': '--text-xl--line-height',
  '--border-radius-xs': '--radius-sm',
  '--border-radius-sm': '--radius-sm',
  '--border-radius-md': '--radius-md',
  '--border-radius-lg': '--radius-lg',
  '--border-radius-full': '--radius-full',
  '--shadow-sm': '--shadow-sm',
  '--shadow-md': '--shadow-md',
  '--shadow-lg': '--shadow-lg',
}

function hostContext(theme: Theme): McpUiHostContext {
  const style = getComputedStyle(document.documentElement)
  const variables = Object.fromEntries(
    Object.entries(mcpVariables).map(([name, token]) => [name, style.getPropertyValue(token).trim() || undefined]),
  )
  return { theme, styles: { variables: variables as McpUiStyles } }
}

function sandboxedDocument(html: string): string {
  const document = new DOMParser().parseFromString(html, 'text/html')
  const policy = document.createElement('meta')
  policy.httpEquiv = 'Content-Security-Policy'
  policy.content = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src data:; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'"
  document.head.prepend(policy)
  return '<!doctype html>' + document.documentElement.outerHTML
}

/** Runs an MCP App's HTML in a sandboxed frame, feeding it job data and the host theme. */
export function McpAppFrame({
  title,
  html,
  data,
  readData,
}: {
  title: string
  html: string
  data: JobsPayload
  readData: () => Promise<JobsPayload>
}) {
  const frame = useRef<HTMLIFrameElement>(null)
  const bridge = useRef<AppBridge | null>(null)
  const latest = useRef(data)
  const initialized = useRef(false)
  const theme = useTheme()
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const read = useEffectEvent(readData)
  const context = useEffectEvent(() => hostContext(theme))

  useEffect(() => {
    const target = frame.current?.contentWindow
    if (!target) return
    let closed = false
    const failed = (reason: unknown) => {
      if (!closed) setError(reason instanceof Error ? reason.message : 'Job view unavailable')
    }
    const host = new AppBridge(null, { name: 'Zagent', version: '1.0.0' }, { serverTools: {} }, { hostContext: context() })
    bridge.current = host
    host.oncalltool = async ({ name, arguments: input }) => {
      if (name !== 'read_jobs' || Object.keys(input ?? {}).length) {
        return { isError: true, content: [{ type: 'text', text: 'This view permits bound job reads only.' }] }
      }
      return { content: [], structuredContent: await read() }
    }
    host.oninitialized = async () => {
      await host.sendToolInput({ arguments: {} })
      initialized.current = true
      await host.sendToolResult({ content: [], structuredContent: latest.current })
      if (!closed) setReady(true)
    }
    host.connect(new PostMessageTransport(target, target)).then(() => {
      if (!closed && frame.current) frame.current.srcdoc = sandboxedDocument(html)
    }, failed)
    return () => {
      closed = true
      initialized.current = false
      bridge.current = null
      void host.close()
    }
  }, [html])

  useEffect(() => {
    latest.current = data
    if (initialized.current) void bridge.current?.sendToolResult({ content: [], structuredContent: data }).catch(() => undefined)
  }, [data])

  useEffect(() => {
    bridge.current?.setHostContext(hostContext(theme))
  }, [theme])

  return (
    <div className="relative flex min-h-96 flex-1 flex-col">
      {error && <Notice tone="danger" role="alert" className="mb-3">{error}</Notice>}
      {!ready && !error && (
        <p role="status" className="absolute top-0 left-0 inline-flex items-center gap-2 text-sm text-muted">
          <Spinner />Loading live job view…
        </p>
      )}
      <iframe
        ref={frame}
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
        title={title}
        data-testid="mcp-job-frame"
        className="block min-h-96 w-full flex-1 border-0 bg-transparent"
      />
    </div>
  )
}

export function McpAppView({ sessionId, viewId, spec }: ViewRendererProps) {
  const [html, setHtml] = useState<string | null>(null)
  const [data, setData] = useState<JobsPayload>({ jobs: [] })
  const [error, setError] = useState<string | null>(null)
  const path = sessionId && viewId ? `/sessions/${sessionId}/views/${viewId}` : null

  useEffect(() => {
    if (!path) return
    const controller = new AbortController()
    request<{ html: string }>(`${path}/app`, { signal: controller.signal }).then(
      (resource) => setHtml(resource.html),
      (reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Job view unavailable') },
    )
    const feed = new EventSource(`/api${path}/updates`)
    feed.addEventListener('jobs', (event) => setData(JSON.parse((event as MessageEvent).data)))
    return () => { controller.abort(); feed.close() }
  }, [path])

  if (!path) return <Notice tone="danger" role="alert">Job view unavailable in this session.</Notice>
  if (error) return <Notice tone="danger" role="alert">{error}</Notice>
  if (!html) return <p role="status" className="inline-flex items-center gap-2 text-sm text-muted"><Spinner />Loading live job view…</p>
  return (
    <McpAppFrame
      title={String(spec.props.title ?? 'Analysis jobs')}
      html={html}
      data={data}
      readData={() => request<JobsPayload>(`${path}/data`)}
    />
  )
}

import { AppBridge, PostMessageTransport } from '@modelcontextprotocol/ext-apps/app-bridge'
import type { McpUiDisplayMode, McpUiHostContext, McpUiStyles } from '@modelcontextprotocol/ext-apps/app-bridge'
import { useEffect, useEffectEvent, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { request } from '../../lib/api'
import { useTheme } from '../../lib/theme'
import type { Theme } from '../../lib/theme'
import { Notice } from '../ui/notice'
import { Spinner } from '../ui/spinner'
import type { ArtifactRendererProps } from './artifact-renderer'

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

/** Display modes the host offers MCP Apps: a card in the conversation, or the maximized panel. */
const displayModes: McpUiDisplayMode[] = ['inline', 'fullscreen']

function hostContext(theme: Theme, displayMode: McpUiDisplayMode): McpUiHostContext {
  const style = getComputedStyle(document.documentElement)
  const variables = Object.fromEntries(
    Object.entries(mcpVariables).map(([name, token]) => [name, style.getPropertyValue(token).trim() || undefined]),
  )
  return { theme, displayMode, availableDisplayModes: displayModes, styles: { variables: variables as McpUiStyles } }
}

function sandboxedDocument(html: string): string {
  const document = new DOMParser().parseFromString(html, 'text/html')
  const policy = document.createElement('meta')
  policy.httpEquiv = 'Content-Security-Policy'
  policy.content = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src data:; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'"
  document.head.prepend(policy)
  return '<!doctype html>' + document.documentElement.outerHTML
}

/** Runs an MCP App's HTML in a sandboxed frame, feeding it job data, the host theme and its display mode. */
export function McpAppFrame({
  title,
  html,
  data,
  readData,
  displayMode = 'fullscreen',
  onRequestDisplayMode,
  initialHeight,
  onHeight,
}: {
  title: string
  html: string
  data: JobsPayload
  readData: () => Promise<JobsPayload>
  displayMode?: McpUiDisplayMode
  /** Called when the app asks for another display mode; the host changes it by maximizing or minimizing. */
  onRequestDisplayMode?: (mode: McpUiDisplayMode) => void
  /** Inline only: the height to start at, and a report of each height the app asks for. */
  initialHeight?: number
  onHeight?: (height: number) => void
}) {
  const frame = useRef<HTMLIFrameElement>(null)
  const bridge = useRef<AppBridge | null>(null)
  const latest = useRef(data)
  const initialized = useRef(false)
  const theme = useTheme()
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [height, setHeight] = useState(initialHeight)
  const read = useEffectEvent(readData)
  const context = useEffectEvent(() => hostContext(theme, displayMode))
  const reportHeight = useEffectEvent((next: number) => onHeight?.(next))
  const requestMode = useEffectEvent((mode: McpUiDisplayMode) => {
    if (mode !== displayMode && displayModes.includes(mode)) onRequestDisplayMode?.(mode)
    return onRequestDisplayMode && displayModes.includes(mode) ? mode : displayMode
  })

  useEffect(() => {
    const target = frame.current?.contentWindow
    if (!target) return
    let closed = false
    const failed = (reason: unknown) => {
      if (!closed) setError(reason instanceof Error ? reason.message : 'Live jobs unavailable')
    }
    const host = new AppBridge(null, { name: 'Zagent', version: '1.0.0' }, { serverTools: {} }, { hostContext: context() })
    bridge.current = host
    host.oncalltool = async ({ name, arguments: input }) => {
      if (name !== 'read_jobs' || Object.keys(input ?? {}).length) {
        return { isError: true, content: [{ type: 'text', text: 'This artifact permits bound job reads only.' }] }
      }
      return { content: [], structuredContent: await read() }
    }
    host.onrequestdisplaymode = async ({ mode }) => ({ mode: requestMode(mode) })
    host.onsizechange = ({ height: next }) => {
      if (closed || next === undefined) return
      setHeight(next)
      reportHeight(next)
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
    bridge.current?.setHostContext(hostContext(theme, displayMode))
  }, [theme, displayMode])

  const inline = displayMode === 'inline'
  return (
    <div className={inline ? 'relative flex flex-col' : 'relative flex min-h-96 flex-1 flex-col'}>
      {error && <Notice tone="danger" role="alert" className="mb-3">{error}</Notice>}
      {!ready && !error && (
        <p role="status" className="absolute top-0 left-0 inline-flex items-center gap-2 text-sm text-muted">
          <Spinner />Loading live jobs…
        </p>
      )}
      <iframe
        ref={frame}
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
        title={title}
        data-testid="mcp-job-frame"
        data-display-mode={displayMode}
        style={inline && height !== undefined ? { height } : undefined}
        className={inline ? 'block h-24 max-h-96 w-full border-0 bg-transparent' : 'block min-h-96 w-full flex-1 border-0 bg-transparent'}
      />
    </div>
  )
}

function scrollParent(element: HTMLElement): HTMLElement | null {
  for (let parent = element.parentElement; parent; parent = parent.parentElement) {
    if (/auto|scroll/.test(getComputedStyle(parent).overflowY)) return parent
  }
  return null
}

/** Whether an element is in its scroll area or within one screen of it, so off-screen cards can let go of their feeds. */
function useNearViewport(target: RefObject<HTMLElement | null>, enabled: boolean): boolean {
  const observable = enabled && typeof IntersectionObserver !== 'undefined'
  const [near, setNear] = useState(false)
  useEffect(() => {
    const element = target.current
    if (!observable || !element) return
    const observer = new IntersectionObserver(([entry]) => setNear(entry.isIntersecting), {
      root: scrollParent(element),
      rootMargin: '100%',
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [target, observable])
  return !observable || near
}

// The last height each inline app asked for, so a card that reconnects keeps its place in the transcript.
const inlineHeights = new Map<string, number>()

// App HTML is static per resource and large, so cards share one download per resource.
const resources = new Map<string, Promise<string>>()
function loadResource(key: string, path: string): Promise<string> {
  let resource = resources.get(key)
  if (!resource) {
    resource = request<{ html: string }>(`${path}/app`).then((body) => body.html)
    resource.catch(() => resources.delete(key))
    resources.set(key, resource)
  }
  return resource
}

const pollInterval = 2000
const finished = new Set(['completed', 'failed'])

/** Whether every job in a payload has finished, so polling can stop. */
function settled(payload: JobsPayload): boolean {
  const jobs = payload.jobs
  return Array.isArray(jobs) && jobs.length > 0 && jobs.every((job) => finished.has((job as { status?: string }).status ?? ''))
}

function LiveMcpApp({ path, resource, spec, display, onMaximize, onMinimize }: ArtifactRendererProps & { path: string; resource: string }) {
  const [html, setHtml] = useState<string | null>(null)
  const [data, setData] = useState<JobsPayload>({ jobs: [] })
  const [error, setError] = useState<string | null>(null)
  const inline = display === 'inline'

  useEffect(() => {
    let active = true
    loadResource(resource, path).then(
      (body) => { if (active) setHtml(body) },
      (reason) => { if (active) setError(reason instanceof Error ? reason.message : 'Live jobs unavailable') },
    )
    return () => { active = false }
  }, [path, resource])

  // Browsers allow six HTTP/1.1 connections per host, and each event stream holds one. The
  // maximized artifact follows the server's stream; cards poll, so a conversation full of job
  // cards, or a second tab, cannot starve the session's own stream.
  useEffect(() => {
    if (!html) return
    if (!inline) {
      const feed = new EventSource(`/api${path}/updates`)
      feed.addEventListener('jobs', (event) => setData(JSON.parse((event as MessageEvent).data)))
      return () => feed.close()
    }
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        const next = await request<JobsPayload>(`${path}/data`)
        if (!active) return
        setData(next)
        if (settled(next)) return
      } catch {
        if (!active) return
      }
      timer = setTimeout(() => void poll(), pollInterval)
    }
    void poll()
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [html, inline, path])

  if (error) return <Notice tone="danger" role="alert">{error}</Notice>
  if (!html) return <p role="status" className="inline-flex items-center gap-2 text-sm text-muted"><Spinner />Loading live jobs…</p>
  return (
    <McpAppFrame
      title={String(spec.props.title ?? 'Analysis jobs')}
      html={html}
      data={data}
      readData={() => request<JobsPayload>(`${path}/data`)}
      displayMode={display === 'inline' ? 'inline' : 'fullscreen'}
      onRequestDisplayMode={(mode) => (mode === 'fullscreen' ? onMaximize?.() : onMinimize?.())}
      initialHeight={inlineHeights.get(path)}
      onHeight={(height) => inlineHeights.set(path, height)}
    />
  )
}

/** An MCP App artifact. Inline, it connects only near the viewport, so a long conversation holds few feeds. */
export function McpAppArtifact(props: ArtifactRendererProps) {
  const { sessionId, artifactId, spec, display } = props
  const slot = useRef<HTMLDivElement>(null)
  const near = useNearViewport(slot, display === 'inline')
  const path = sessionId && artifactId ? `/sessions/${sessionId}/artifacts/${artifactId}` : null
  const resource = String(spec.props.resource_uri ?? spec.kind)

  if (!path) return <Notice tone="danger" role="alert">Live jobs unavailable in this session.</Notice>
  const inline = display === 'inline'
  const reserved = inline && !near ? inlineHeights.get(path) : undefined
  return (
    <div
      ref={slot}
      data-testid="mcp-app-slot"
      style={reserved !== undefined ? { minHeight: reserved } : undefined}
      className={inline ? 'flex min-h-24 flex-col' : 'flex min-h-0 flex-1 flex-col'}
    >
      {near && <LiveMcpApp {...props} path={path} resource={resource} />}
    </div>
  )
}

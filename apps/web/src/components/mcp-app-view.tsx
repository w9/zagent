import { AppBridge, PostMessageTransport } from '@modelcontextprotocol/ext-apps/app-bridge'
import { useEffect, useRef, useState } from 'react'
import { request } from '../lib/api'
import type { ViewRendererProps } from './view-renderer'

function sandboxedDocument(html: string): string {
  const document = new DOMParser().parseFromString(html, 'text/html')
  const policy = document.createElement('meta')
  policy.httpEquiv = 'Content-Security-Policy'
  policy.content = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src data:; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'"
  document.head.prepend(policy)
  return '<!doctype html>' + document.documentElement.outerHTML
}

export function McpAppView({ sessionId, viewId, spec }: ViewRendererProps) {
  const frame = useRef<HTMLIFrameElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (!sessionId || !viewId) return
    const controller = new AbortController()
    const path = `/sessions/${sessionId}/views/${viewId}`
    let bridge: AppBridge | undefined
    let feed: EventSource | undefined
    let initialized = false
    let latest: Record<string, unknown> = { jobs: [] }
    const failed = (reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Job view unavailable')
    }
    async function connect() {
      const resource = await request<{ html: string }>(`${path}/app`, { signal: controller.signal })
      if (controller.signal.aborted || !frame.current?.contentWindow) return
      const host = new AppBridge(null, { name: 'Zagent', version: '1.0.0' }, { serverTools: {} })
      bridge = host
      host.oncalltool = async ({ name, arguments: arguments_ }) => {
        if (name !== 'read_jobs' || Object.keys(arguments_ ?? {}).length) {
          return { isError: true, content: [{ type: 'text', text: 'This view permits bound job reads only.' }] }
        }
        return { content: [], structuredContent: await request<Record<string, unknown>>(`${path}/data`) }
      }
      host.oninitialized = async () => {
        await host.sendToolInput({ arguments: {} })
        initialized = true
        await host.sendToolResult({ content: [], structuredContent: latest })
        if (!controller.signal.aborted) setReady(true)
      }
      await host.connect(new PostMessageTransport(frame.current.contentWindow, frame.current.contentWindow))
      if (controller.signal.aborted) { await host.close(); return }
      feed = new EventSource(`/api${path}/updates`)
      feed.addEventListener('jobs', (event) => {
        latest = JSON.parse((event as MessageEvent).data)
        if (initialized) void host.sendToolResult({ content: [], structuredContent: latest }).catch(failed)
      })
      frame.current.srcdoc = sandboxedDocument(resource.html)
    }
    void connect().catch(failed)
    return () => { controller.abort(); feed?.close(); void bridge?.close() }
  }, [sessionId, viewId])
  if (!sessionId || !viewId) return <p className="surface-error" role="alert">Job view unavailable in this session.</p>
  return <div className="mcp-app-surface">
    {error && <p className="surface-error" role="alert">{error}</p>}
    {!ready && !error && <p className="mcp-app-loading" role="status">Loading live job view...</p>}
    <iframe ref={frame} sandbox="allow-scripts" referrerPolicy="no-referrer"
      title={String(spec.props.title ?? 'Analysis jobs')} className="mcp-app-frame" data-testid="mcp-job-frame" />
  </div>
}
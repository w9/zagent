import { ArrowRightLeft, ChevronRight, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { request } from '../../lib/api'
import type { XrayData } from '../../lib/api'
import { plural } from '../../lib/format'
import { Button } from '../ui/button'
import { Notice } from '../ui/notice'
import { PanelHeader } from '../ui/panel-header'
import { Spinner } from '../ui/spinner'
import { Tabs } from '../ui/tabs'
import { PrivacyText, TranscriptText } from '../chat/transcript-text'

const preClassName = 'font-mono text-xs leading-relaxed whitespace-pre-wrap wrap-anywhere text-default'
const detailsClassName = 'border-t border-subtle py-3 first:border-t-0 first:pt-0'

function Summary({ meta, children }: { meta?: ReactNode; children: ReactNode }) {
  return (
    <summary className="flex min-h-control-sm cursor-pointer list-none items-center gap-2 rounded-sm text-sm font-medium text-strong [&::-webkit-details-marker]:hidden">
      <ChevronRight aria-hidden className="size-icon-sm shrink-0 text-muted transition-transform [details[open]>summary>&]:rotate-90" />
      <span className="min-w-0 flex-1 wrap-anywhere">{children}</span>
      {meta && <span className="font-mono text-xs font-normal text-muted">{meta}</span>}
    </summary>
  )
}

function Message({ label, children }: { label: string; children: ReactNode }) {
  return (
    <article data-testid="xray-message" className="flex min-w-0 flex-col gap-2">
      <h4 className="font-mono text-xs text-muted wrap-anywhere">{label}</h4>
      {children}
    </article>
  )
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted">{children}</p>
}

/** What the user saw beside what the model saw, with privacy values linked across both. */
export function XrayContent({ data }: { data: XrayData }) {
  const [selected, setSelected] = useState<string | null>(null)
  const [pane, setPane] = useState<'display' | 'model'>('display')
  const highlight = (text: string, model = false) => (
    <PrivacyText text={text} bindings={data.bindings} model={model} selected={selected} onSelect={setSelected} />
  )
  const paneClassName = (name: 'display' | 'model') =>
    pane === name ? 'min-h-0 overflow-y-auto px-4 py-6 @medium:px-6' : 'hidden min-h-0 overflow-y-auto px-4 py-6 @medium:px-6 @wide:block'

  return (
    <>
      <PanelHeader
        title="X-ray"
        subtitle={plural(data.requests.length, 'model request', 'model requests')}
        actions={<ArrowRightLeft aria-hidden className="size-icon" />}
      />
      <Tabs
        label="X-ray panes"
        className="@wide:hidden"
        value={pane}
        onChange={setPane}
        items={[
          { value: 'display', label: 'Display', controls: 'xray-display' },
          { value: 'model', label: 'Model', controls: 'xray-model' },
        ]}
      />
      <div className="grid min-h-0 flex-1 grid-cols-1 @wide:grid-cols-2">
        <section id="xray-display" aria-label="Displayed conversation" className={paneClassName('display')}>
          <h3 className="mb-6 text-sm font-semibold text-strong">Display</h3>
          <div className="flex flex-col gap-6">
            {data.display.messages.map((message) => {
              const source = data.model.messages.find((item) => item.id === message.id)
              return (
                <Message key={message.id} label={message.role === 'user' ? 'You' : 'Zagent'}>
                  <TranscriptText
                    role={source ? message.role : 'user'}
                    size="sm"
                    text={source?.text ?? message.text}
                    streaming={message.status === 'streaming'}
                    bindings={data.bindings}
                    selected={selected}
                    onSelect={setSelected}
                  />
                </Message>
              )
            })}
            {data.display.refusals?.map((item) => (
              <Message key={item.id} label="Refused"><p className="text-sm wrap-anywhere">{item.message}</p></Message>
            ))}
            {data.executions.length > 0 && (
              <details open className={detailsClassName}>
                <Summary>Tool executions</Summary>
                <div className="mt-3 flex flex-col gap-4">
                  {data.executions.map((execution, index) => (
                    <Message key={index} label={execution.tool}>
                      <pre className={preClassName}>{highlight(JSON.stringify(execution.arguments, null, 2))}</pre>
                    </Message>
                  ))}
                </div>
              </details>
            )}
            {!data.display.messages.length && <Empty>No messages</Empty>}
          </div>
        </section>
        <section id="xray-model" aria-label="Model-visible requests" className={`${paneClassName('model')} bg-subtle @wide:border-l @wide:border-subtle`}>
          <h3 className="mb-6 text-sm font-semibold text-strong">Model</h3>
          {data.requests.map((entry, index) => (
            <details key={entry.request_id} open={index === data.requests.length - 1} className={detailsClassName}>
              <Summary meta={entry.audit.mode}>
                {index + 1}. {entry.audit.purpose === 'scope_guard' ? 'Scope guard' : 'Agent'}
              </Summary>
              <div className="mt-3 flex flex-col gap-4">
                <div className="flex flex-col gap-1 font-mono text-xs text-muted wrap-anywhere">
                  <span>{entry.request.model}</span>
                  <code title="Request hash">{entry.audit.request_hash}</code>
                </div>
                {entry.request.messages.map((message, messageIndex) =>
                  message.role === 'system' ? (
                    <details key={messageIndex} className={detailsClassName}>
                      <Summary>System prompt</Summary>
                      <pre className={`${preClassName} mt-3`}>{highlight(message.content ?? '', true)}</pre>
                    </details>
                  ) : (
                    <Message key={messageIndex} label={`${message.role}${message.tool_call_id ? ` / ${message.tool_call_id}` : ''}`}>
                      {message.content && <pre className={preClassName}>{highlight(message.content, true)}</pre>}
                      {message.tool_calls && <pre className={preClassName}>{highlight(JSON.stringify(message.tool_calls, null, 2), true)}</pre>}
                    </Message>
                  ),
                )}
                {entry.request.tools && (
                  <details className={detailsClassName}>
                    <Summary>Tool schemas</Summary>
                    <pre className={`${preClassName} mt-3`}>{JSON.stringify(entry.request.tools, null, 2)}</pre>
                  </details>
                )}
              </div>
            </details>
          ))}
          {!data.requests.length && <Empty>No model requests recorded</Empty>}
        </section>
      </div>
    </>
  )
}

export function XrayPanel({ sessionId, seq }: { sessionId: string; seq: number }) {
  const [data, setData] = useState<XrayData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    request<XrayData>(`/sessions/${sessionId}/xray`, { signal: controller.signal }).then(
      (result) => { if (!controller.signal.aborted) { setData(result); setError(null) } },
      (reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'X-ray unavailable') },
    )
    return () => controller.abort()
  }, [sessionId, seq, attempt])
  return (
    <section aria-label="X-ray inspection" className="@container flex min-h-0 flex-1 flex-col bg-surface">
      {error ? (
        <div className="p-6">
          <Notice tone="danger" role="alert" action={<Button size="sm" icon={RefreshCw} onClick={() => setAttempt((value) => value + 1)}>Retry</Button>}>
            {error}
          </Notice>
        </div>
      ) : data ? (
        <XrayContent data={data} />
      ) : (
        <p role="status" className="inline-flex items-center gap-2 p-6 text-sm text-muted"><Spinner />Loading X-ray…</p>
      )}
    </section>
  )
}

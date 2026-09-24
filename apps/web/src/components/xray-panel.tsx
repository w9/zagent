import { ArrowRightLeft, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { request } from '../lib/api'
import type { XrayData } from '../lib/api'
import { Button } from './ui/button'
import { PrivacyText, TranscriptText } from './transcript-text'

export function XrayContent({ data }: { data: XrayData }) {
  const [selected, setSelected] = useState<string | null>(null)
  const [mobilePane, setMobilePane] = useState<'display' | 'model'>('display')
  const highlight = (text: string, model = false) => <PrivacyText
    text={text} bindings={data.bindings} model={model} selected={selected} onSelect={setSelected}
  />

  return <>
    <header className="panel-heading xray-heading">
      <div><h2>X-ray</h2><span className="session-subtitle">{data.requests.length} model requests</span></div>
      <ArrowRightLeft size={17} aria-hidden="true" />
    </header>
    <div className="xray-tabs" role="tablist" aria-label="X-ray panes">
      {(['display', 'model'] as const).map((pane) => <button
        key={pane} type="button" role="tab" aria-selected={mobilePane === pane}
        aria-controls={`xray-${pane}`} onClick={() => setMobilePane(pane)}
      >{pane === 'display' ? 'Display' : 'Model'}</button>)}
    </div>
    <div className="xray-panes" data-mobile-pane={mobilePane}>
      <section className="xray-pane xray-display" id="xray-display" aria-label="Displayed conversation">
        <h3>Display</h3>
        {data.display.messages.map((message) => {
          const source = data.model.messages.find((item) => item.id === message.id)
          return <article className="xray-message" key={message.id}>
          <h4>{message.role === 'user' ? 'You' : 'Zagent'}</h4>
          <TranscriptText role={source ? message.role : 'user'}
            text={source?.text ?? message.text}
            streaming={message.status === 'streaming'} bindings={data.bindings}
            selected={selected} onSelect={setSelected} />
        </article>})}
        {data.display.refusals?.map((item) => <article className="xray-message" key={item.id}>
          <h4>Refused</h4><p>{item.message}</p>
        </article>)}
        {data.executions.length > 0 && <details className="xray-executions" open>
          <summary>Tool executions</summary>
          {data.executions.map((execution, index) => <div className="xray-execution" key={index}>
            <h4>{execution.tool}</h4><pre>{highlight(JSON.stringify(execution.arguments, null, 2))}</pre>
          </div>)}
        </details>}
        {!data.display.messages.length && <p className="xray-empty">No messages</p>}
      </section>
      <section className="xray-pane xray-model" id="xray-model" aria-label="Model-visible requests">
        <h3>Model</h3>
        {data.requests.map((entry, index) => <details
          className="xray-request" key={entry.request_id} open={index === data.requests.length - 1}
        >
          <summary>{index + 1}. {entry.audit.purpose === 'scope_guard' ? 'Scope guard' : 'Agent'}
            <span>{entry.audit.mode}</span></summary>
          <div className="xray-request-meta"><span>{entry.request.model}</span>
            <code title="Request hash">{entry.audit.request_hash}</code></div>
          {entry.request.messages.map((message, messageIndex) => message.role === 'system'
            ? <details className="xray-system" key={messageIndex}><summary>System prompt</summary>
              <pre>{highlight(message.content ?? '', true)}</pre></details>
            : <article className="xray-message" key={messageIndex}>
              <h4>{message.role}{message.tool_call_id ? ` / ${message.tool_call_id}` : ''}</h4>
              {message.content && <pre>{highlight(message.content, true)}</pre>}
              {message.tool_calls && <pre>{highlight(JSON.stringify(message.tool_calls, null, 2), true)}</pre>}
            </article>)}
          {entry.request.tools && <details className="xray-system"><summary>Tool schemas</summary>
            <pre>{JSON.stringify(entry.request.tools, null, 2)}</pre></details>}
        </details>)}
        {!data.requests.length && <p className="xray-empty">No model requests recorded</p>}
      </section>
    </div>
  </>
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
  return <section className="xray-workspace" aria-label="X-ray inspection">
    {error ? <div className="surface-error" role="alert"><p>{error}</p>
      <Button variant="ghost" onClick={() => setAttempt((value) => value + 1)}><RefreshCw />Retry</Button>
    </div> : data ? <XrayContent data={data} /> : <p className="xray-empty" role="status">Loading X-ray...</p>}
  </section>
}
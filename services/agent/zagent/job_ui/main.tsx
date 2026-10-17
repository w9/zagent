import { App, applyDocumentTheme, applyHostStyleVariables } from '@modelcontextprotocol/ext-apps'
import type { McpUiDisplayMode } from '@modelcontextprotocol/ext-apps'
import { Activity, Clock3, Pause, Play, ScrollText, TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import font from '@fontsource-variable/dm-sans/files/dm-sans-latin-wght-normal.woff2'

type LogLine = { seq: number; attempt: number; record: { body: string; severityText: string } }
type Job = {
  job_id: string; app_id: string; title: string; status: string; progress: number
  detail: string; attempt: number; log_seq: number; started_at: string | null
  finished_at: string | null; parameters: Record<string, string | number | boolean>
  logs: LogLine[]; attempts: { attempt: number; status: string; exit_code: number | null }[]
}
type Payload = { jobs: Job[]; error?: string }
// Inline (a card in the conversation) shows a compact summary; fullscreen (maximized) adds parameters, history and logs.
const protocol = new App({ name: 'Zagent analysis jobs', version: '1.0.0' }, { availableDisplayModes: ['inline', 'fullscreen'] }, { autoResize: true })
// Styled only with MCP Apps host variables (docs/DESIGN.md section 6). Fallbacks are the light theme.
const style = document.createElement('style')
style.textContent = `
@font-face{font-family:'DM Sans Variable';src:url(${font}) format('woff2');font-weight:100 900}
:root{
--bg:var(--color-background-primary,#ffffff);--bg-subtle:var(--color-background-secondary,#f9fcfa);--bg-muted:var(--color-background-tertiary,#edf1ef);
--fg:var(--color-text-primary,#343d39);--fg-muted:var(--color-text-secondary,#626e68);
--line:var(--color-border-primary,#dae2de);--line-subtle:var(--color-border-secondary,#e4eae7);--accent:var(--color-ring-primary,#28745a);
--danger:var(--color-text-danger,#943932);--danger-bg:var(--color-background-danger,#fdf2f0);--danger-line:var(--color-border-danger,#f5a69d);
--warning:var(--color-text-warning,#694b0d);--warning-bg:var(--color-background-warning,#fff6e7);--warning-line:var(--color-border-warning,#efc379);
--success:var(--color-text-success,#1c5e48);--success-bg:var(--color-background-success,#eaf9f2);--success-line:var(--color-border-success,#91d1b7);
--radius-sm:var(--border-radius-sm,4px);--radius-md:var(--border-radius-md,6px);
--xs:var(--font-text-xs-size,11px)/var(--font-text-xs-line-height,16px);--sm:var(--font-text-sm-size,12px)/var(--font-text-sm-line-height,18px);
--md:var(--font-text-md-size,13px)/var(--font-text-md-line-height,20px);--heading:var(--font-heading-md-size,16px)/var(--font-heading-md-line-height,24px);
--sans:var(--font-sans,'DM Sans Variable',sans-serif);--mono:var(--font-mono,ui-monospace,monospace);
font:var(--md) var(--sans);letter-spacing:0;color:var(--fg);background:var(--bg-subtle);color-scheme:light}
:root[data-theme=dark]{color-scheme:dark}
*{box-sizing:border-box}body{margin:0}button,select{font:inherit;color:inherit}button{cursor:pointer}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
main{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));align-items:start}
:root[data-display=inline]{background:var(--bg)}
main.compact{display:flex;flex-direction:column;align-items:stretch;gap:12px}
.compact .job{padding:0;border:0;border-radius:0;background:transparent}.compact .job+.job{border-top:1px solid var(--line-subtle);padding-top:12px}
.compact h1{font:600 var(--md) var(--sans);margin:2px 0 0}.compact .progress{margin:8px 0}
.compact .facts{align-items:center}.compact .show-log{margin-left:auto;display:flex;align-items:center;gap:6px;height:28px;padding:0 8px;border:1px solid var(--line);border-radius:var(--radius-md);background:var(--bg);font:500 var(--sm) var(--sans)}
.job{min-width:0;background:var(--bg);border:1px solid var(--line-subtle);border-radius:var(--radius-md);padding:16px}
.heading{display:flex;gap:12px;justify-content:space-between;align-items:start}
h1{font:600 var(--heading) var(--sans);margin:4px 0 8px;color:var(--fg);overflow-wrap:anywhere}
.identity{font:var(--xs) var(--mono);color:var(--fg-muted);display:flex;align-items:center;gap:6px;overflow-wrap:anywhere}
.state{text-transform:capitalize;font:500 var(--xs) var(--sans);white-space:nowrap;padding:2px 6px;border:1px solid var(--line);border-radius:var(--radius-sm);color:var(--fg);background:var(--bg-muted)}
.state.running{color:var(--accent);border-color:var(--accent);background:var(--bg)}
.state.failed{color:var(--danger);background:var(--danger-bg);border-color:var(--danger-line)}
.state.completed{color:var(--success);background:var(--success-bg);border-color:var(--success-line)}
.state.retrying{color:var(--warning);background:var(--warning-bg);border-color:var(--warning-line)}
.progress{display:flex;gap:12px;align-items:center;margin:12px 0}progress{width:100%;height:6px;accent-color:var(--accent)}
.percent{font:var(--sm) var(--mono);font-variant-numeric:tabular-nums;min-width:4ch;text-align:right}
.facts{display:flex;flex-wrap:wrap;gap:12px;color:var(--fg-muted);font:var(--sm) var(--sans)}.facts span{display:flex;align-items:center;gap:6px}
.detail{overflow-wrap:anywhere;min-height:3em;margin:0 0 12px}
.params{display:flex;flex-wrap:wrap;gap:4px 16px;padding:12px 0;border-top:1px solid var(--line-subtle);font:var(--sm) var(--sans);color:var(--fg-muted)}.params b{font-weight:500;color:var(--fg)}
.history{border-top:1px solid var(--line-subtle);padding:12px 0;font:var(--sm) var(--sans)}.history summary{cursor:pointer;color:var(--fg)}.history p{margin:4px 0;color:var(--fg-muted)}
.log-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;border-top:1px solid var(--line-subtle);padding:12px 0 8px}.log-heading h2{font:600 var(--md) var(--sans);margin:0;white-space:nowrap}
.log-tools{display:flex;gap:8px;align-items:center;min-width:0}
.log-tools select{max-width:160px;min-width:0;height:28px;background:var(--bg);border:1px solid var(--line);border-radius:var(--radius-sm);padding:0 4px;font:var(--sm) var(--sans)}
.log-tools button{width:28px;height:28px;display:grid;place-items:center;border:1px solid var(--line);border-radius:var(--radius-md);background:var(--bg);color:var(--fg)}
.logs{height:240px;overflow:auto;overscroll-behavior:contain;background:var(--bg-subtle);border:1px solid var(--line-subtle);border-radius:var(--radius-sm);padding:8px}
.line{display:grid;grid-template-columns:3ch 1fr;gap:12px;font:var(--xs) var(--mono);padding:2px 0;overflow-wrap:anywhere}.line-number{color:var(--fg-muted)}
.ERROR{color:var(--danger)}.WARN{color:var(--warning)}
.empty,.error{padding:24px;color:var(--fg-muted)}.error{color:var(--danger);display:flex;gap:8px}.tail-note{font:var(--xs) var(--sans);color:var(--fg-muted);margin-top:8px}
@media(pointer:coarse){.log-tools select{height:36px}.log-tools button{width:36px;height:36px}.compact .show-log{height:36px}}
@media(max-width:360px){.job{padding:12px}.log-tools select{max-width:128px}}
`
document.head.append(style)

function displayMode(): McpUiDisplayMode {
  return protocol.getHostContext()?.displayMode ?? 'fullscreen'
}

function applyHostContext() {
  const context = protocol.getHostContext()
  if (context?.theme) applyDocumentTheme(context.theme)
  if (context?.styles?.variables) applyHostStyleVariables(context.styles.variables)
  document.documentElement.dataset.display = displayMode()
}

function canShowFullscreen() {
  return protocol.getHostContext()?.availableDisplayModes?.includes('fullscreen') ?? false
}

function JobSummary({ job, clock }: { job: Job; clock: number }) {
  const end = job.finished_at ? Date.parse(job.finished_at) : clock
  const elapsed = job.started_at ? Math.max(0, Math.floor((end - Date.parse(job.started_at)) / 1000)) : 0
  return <section className="job" aria-label={`Job ${job.job_id}`} data-job-id={job.job_id}>
    <div className="heading"><div><span className="identity"><Activity size={13} />{job.job_id}</span><h1>{job.title}</h1></div><span className={`state ${job.status}`} role="status">{job.status}</span></div>
    <div className="progress"><progress aria-label="Job progress" value={job.progress} max={1} /><span className="percent">{Math.round(job.progress * 100)}%</span></div>
    <div className="facts">
      <span><Clock3 size={13} />{Math.floor(elapsed / 60)}m {elapsed % 60}s</span><span>Attempt {job.attempt}</span>
      {canShowFullscreen() && <button className="show-log" onClick={() => void protocol.requestDisplayMode({ mode: 'fullscreen' })}><ScrollText size={13} />Show log</button>}
    </div>
  </section>
}

function JobCard({ job, clock }: { job: Job; clock: number }) {
  const [follow, setFollow] = useState(true)
  const [severity, setSeverity] = useState('all')
  const tail = useRef<HTMLDivElement>(null)
  useEffect(() => { if (follow && tail.current) tail.current.scrollTop = tail.current.scrollHeight }, [job.log_seq, follow])
  const end = job.finished_at ? Date.parse(job.finished_at) : clock
  const elapsed = job.started_at ? Math.max(0, Math.floor((end - Date.parse(job.started_at)) / 1000)) : 0
  const lines = job.logs.filter((line) => severity === 'all' || ['ERROR', 'WARN'].includes(line.record.severityText))
  return <section className="job" aria-label={`Job ${job.job_id}`} data-job-id={job.job_id}>
    <div className="heading"><div><span className="identity"><Activity size={13} />{job.job_id}</span><h1>{job.title}</h1></div><span className={`state ${job.status}`} role="status">{job.status}</span></div>
    <div className="facts"><span><Clock3 size={13} />{Math.floor(elapsed / 60)}m {elapsed % 60}s</span><span>Attempt {job.attempt}</span></div>
    <div className="progress"><progress aria-label="Job progress" value={job.progress} max={1} /><span className="percent">{Math.round(job.progress * 100)}%</span></div>
    <p className="detail">{job.detail}</p>
    <div className="params">{Object.entries(job.parameters).map(([key, value]) => <span key={key}>{key}: <b>{String(value)}</b></span>)}</div>
    {job.attempts.length > 0 && <details className="history"><summary>Attempt history ({job.attempts.length})</summary>{job.attempts.map((item) => <p key={item.attempt}>Attempt {item.attempt}: {item.status}{item.exit_code !== null ? ` / exit ${item.exit_code}` : ''}</p>)}</details>}
    <div className="log-heading"><h2>Execution log</h2><div className="log-tools"><select aria-label="Log level" value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="all">All messages</option><option value="warnings">Warnings and errors</option></select><button aria-label={follow ? 'Pause log following' : 'Follow log'} title={follow ? 'Pause log following' : 'Follow log'} onClick={() => setFollow(!follow)}>{follow ? <Pause size={13} /> : <Play size={13} />}</button></div></div>
    <div className="logs" ref={tail} role="log" aria-label={`Execution log for ${job.job_id}`} aria-live="off">{lines.length ? lines.map((line) => <div className={`line ${line.record.severityText}`} key={line.seq}><span className="line-number">{line.seq}</span><span>{line.record.body}</span></div>) : <span className="tail-note">No matching log entries</span>}</div>
    <div className="tail-note">{job.logs.length} of {job.log_seq} log entries</div>
  </section>
}

function JobsApp() {
  const [data, setData] = useState<Payload | null>(null)
  const [clock, setClock] = useState(Date.now())
  const [mode, setMode] = useState<McpUiDisplayMode>('fullscreen')
  useEffect(() => {
    const context = () => { applyHostContext(); setMode(displayMode()) }
    protocol.onhostcontextchanged = context
    protocol.ontoolresult = (result) => setData(result.structuredContent as Payload)
    protocol.connect().then(context, () => setData({ jobs: [], error: 'Host connection unavailable' }))
    const timer = window.setInterval(() => setClock(Date.now()), 1000)
    return () => { window.clearInterval(timer); void protocol.close() }
  }, [])
  if (!data) return <p className="empty" role="status">Connecting to job state...</p>
  if (data.error) return <p className="error" role="alert"><TriangleAlert size={16} />{data.error}</p>
  if (!data.jobs.length) return <main aria-label="Live analysis jobs"><p className="empty">No jobs to show.</p></main>
  if (mode === 'inline') return <main className="compact" aria-label="Live analysis jobs">{data.jobs.map((job) => <JobSummary key={job.job_id} job={job} clock={clock} />)}</main>
  return <main className={data.jobs.length === 1 ? 'single' : 'grid'} aria-label="Live analysis jobs">{data.jobs.map((job) => <JobCard key={job.job_id} job={job} clock={clock} />)}</main>
}

createRoot(document.getElementById('root')!).render(<JobsApp />)
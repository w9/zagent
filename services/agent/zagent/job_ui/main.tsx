import { App } from '@modelcontextprotocol/ext-apps'
import { Activity, Clock3, Pause, Play, TriangleAlert } from 'lucide-react'
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
const protocol = new App({ name: 'Zagent analysis jobs', version: '1.0.0' }, {}, { autoResize: false })
const style = document.createElement('style')
style.textContent = `
@font-face{font-family:Workbench;src:url(${font}) format('woff2');font-weight:100 900}
:root{font:14px Workbench,sans-serif;letter-spacing:0;color:#253036;background:#fafbfa;color-scheme:light}
*{box-sizing:border-box}body{margin:0}button,select{font:inherit}button{cursor:pointer}
main{padding:16px;display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));align-items:start}
.job{min-width:0;background:white;border:1px solid #dce2df;border-radius:6px;padding:16px}
main.single .job{border:0;padding:0;background:transparent}.heading{display:flex;gap:12px;justify-content:space-between;align-items:start}
h1{font-size:18px;line-height:1.3;margin:4px 0 10px;font-weight:600;overflow-wrap:anywhere}
.identity{font-size:12px;color:#67746f;display:flex;align-items:center;gap:6px}.state{text-transform:capitalize;font-size:12px;white-space:nowrap;padding:4px 7px;border:1px solid #cad5d0;border-radius:4px;color:#31594c;background:#f0f6f3}
.state.failed{color:#973f38;background:#fdf1ef;border-color:#edccc6}.state.completed{color:#217152;background:#edf9f2}.state.retrying{color:#8c641e;background:#fff8e6}
.progress{display:flex;gap:12px;align-items:center;margin:14px 0}progress{width:100%;height:8px;accent-color:#258279}.percent{font-variant-numeric:tabular-nums;min-width:4ch;text-align:right;font-size:12px}
.facts{display:flex;flex-wrap:wrap;gap:12px;color:#66756f;font-size:12px}.facts span{display:flex;align-items:center;gap:5px}
.detail{font-size:13px;line-height:1.6;overflow-wrap:anywhere;min-height:3em}.params{display:flex;flex-wrap:wrap;gap:6px 16px;padding:12px 0;border-top:1px solid #e2e7e4;font-size:12px;color:#55645d}.params b{font-weight:500;color:#233f34}
.history{border-top:1px solid #e2e7e4;padding:10px 0;font-size:12px}.history p{margin:5px 0;color:#58685f}
.log-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;border-top:1px solid #dce2df;padding:12px 0 8px}.log-heading h2{font-size:13px;font-weight:600;margin:0;white-space:nowrap}
.log-tools{display:flex;gap:8px;align-items:center;min-width:0}.log-tools select{max-width:160px;min-width:0;background:white;border:1px solid #dce2df;border-radius:4px;padding:4px;font-size:11px}.log-tools button{width:28px;height:28px;display:grid;place-items:center;border:1px solid #dce2df;border-radius:4px;background:white;color:#436056}
.logs{height:240px;overflow:auto;overscroll-behavior:contain;background:#f2f5f3;border:1px solid #dce2df;border-radius:4px;padding:8px}
.line{display:grid;grid-template-columns:3ch 1fr;gap:10px;font:11px/1.65 monospace;padding:3px 0;overflow-wrap:anywhere}.line-number{color:#86938a}.ERROR{color:#a13c32}.WARN{color:#8d651d}.empty,.error{padding:24px;color:#66756f}.error{color:#973f38;display:flex;gap:8px}.tail-note{font-size:11px;color:#718278;margin-top:8px}
@media(max-width:360px){main{padding:10px}.job{padding:10px}.log-tools select{max-width:128px}h1{font-size:16px}.logs{height:230px}}
`
document.head.append(style)

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
  useEffect(() => {
    protocol.ontoolresult = (result) => setData(result.structuredContent as Payload)
    protocol.connect().catch(() => setData({ jobs: [], error: 'Host connection unavailable' }))
    const timer = window.setInterval(() => setClock(Date.now()), 1000)
    return () => { window.clearInterval(timer); void protocol.close() }
  }, [])
  if (!data) return <p className="empty" role="status">Connecting to job state...</p>
  if (data.error) return <p className="error" role="alert"><TriangleAlert size={16} />{data.error}</p>
  return <main className={data.jobs.length === 1 ? 'single' : 'grid'} aria-label="Live analysis jobs">{data.jobs.length ? data.jobs.map((job) => <JobCard key={job.job_id} job={job} clock={clock} />) : <p className="empty">No jobs match this view.</p>}</main>
}

createRoot(document.getElementById('root')!).render(<JobsApp />)
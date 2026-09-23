import { AlertTriangle, Check, Save, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ApiError, request } from '../../lib/api'
import type { DraftState, JobState } from '../../lib/events'
import { Button } from '../ui/button'
import type { ViewRendererProps } from '../view-renderer'

export type CatalogApp = {
  id: string; title: string; layout: string[]
  parameters: { properties: Record<string, {
    type: 'string' | 'number' | 'integer' | 'boolean'; title: string
    minimum?: number; maximum?: number; enum?: string[]; default?: string | number | boolean
  }> }
}

export function DraftEditor({ draft, catalog, sessionId, onConfirmed }: {
  draft: DraftState; catalog: CatalogApp[]; sessionId: string; onConfirmed?: () => void
}) {
  const [saved, setSaved] = useState<DraftState | null>(null)
  const current = saved && (saved.version >= draft.version || saved.status === 'submitted') ? saved : draft
  const [changes, setChanges] = useState<Record<string, string | number | boolean>>({})
  const [baseHash, setBaseHash] = useState<string | null>(null)
  const [selection, setSelection] = useState<string | null>(null)
  const [appChoice, setAppChoice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [conflict, setConflict] = useState<{ current: DraftState; changes: { field: string; before: unknown; after: unknown }[] } | null>(null)
  const selectedApp = appChoice ?? current.app_id
  const application = catalog.find((item) => item.id === selectedApp)
  const dirty = baseHash !== null
  const submitted = current.status === 'submitted'
  const path = `/sessions/${sessionId}/drafts/${current.draft_id}`

  function touch() { if (!baseHash) setBaseHash(current.content_hash) }

  function failed(reason: unknown) {
    if (reason instanceof ApiError && reason.body.current) {
      const next = reason.body.current as DraftState
      if (reason.status === 409) setConflict({ current: next, changes: (reason.body.changes ?? []) as { field: string; before: unknown; after: unknown }[] })
      else setSaved(next)
    }
    setError(reason instanceof Error ? reason.message : 'Draft operation failed')
  }

  async function save() {
    setBusy(true); setError(null)
    try {
      const result = await request<DraftState>(path, { method: 'PATCH', body: JSON.stringify({
        content_hash: baseHash ?? current.content_hash, parameters: changes,
        ...(selection !== null ? { specimen_handle: selection } : {}),
        ...(appChoice !== null ? { app_id: appChoice } : {}),
      }) })
      setSaved(result); setChanges({}); setSelection(null); setAppChoice(null); setBaseHash(null)
    } catch (reason) { failed(reason) }
    finally { setBusy(false) }
  }

  async function confirm() {
    setBusy(true); setError(null)
    try {
      const job = await request<JobState>(`${path}/confirm`, { method: 'POST', body: JSON.stringify({ content_hash: current.content_hash }) })
      setSaved({ ...current, status: 'submitted', job_id: job.job_id })
      onConfirmed?.()
    } catch (reason) { failed(reason) }
    finally { setBusy(false) }
  }

  return <section className="draft-view" aria-label="Analysis draft">
    <div className="table-view-heading"><span className="view-kind">Analysis draft</span>
      <h3>{application?.title ?? current.app_id}</h3>
      <span className="table-count">Version {current.version} / {submitted ? 'Submitted' : 'Draft'}</span>
    </div>
    {conflict && <div className="draft-conflict" role="alert">
      <h4><AlertTriangle size={15} />Draft changed</h4>
      {conflict.changes.map((change) => <p key={change.field}>
        <strong>{change.field}</strong>: {String(change.before ?? 'unset')} to {String(change.after ?? 'unset')}
      </p>)}
      <Button variant="ghost" onClick={() => {
        setSaved(conflict.current); setChanges({}); setSelection(null); setAppChoice(null); setBaseHash(null); setConflict(null); setError(null)
      }}><RefreshCw />Review current draft</Button>
    </div>}
    {error && !conflict && <p className="surface-error" role="alert">{error}</p>}
    <form onSubmit={(event) => { event.preventDefault(); void save() }}>
      <fieldset disabled={busy || submitted || Boolean(conflict)} className="draft-fields">
        <label>Application<select value={selectedApp} onChange={(event) => {
          touch(); setAppChoice(event.target.value)
          const chosen = catalog.find((item) => item.id === event.target.value)!
          setChanges(Object.fromEntries(Object.entries(chosen.parameters.properties).map(([key, field]) => [key, field.default ?? ''])))
        }}>{catalog.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
        <label>Specimen query<input value={selection ?? current.specimen_handle ?? ''} placeholder="query-0001"
          pattern="query-[0-9]{4,}" required onChange={(event) => { touch(); setSelection(event.target.value) }} /></label>
        {application?.layout.map((key) => {
          const field = application.parameters.properties[key]
          const value = changes[key] ?? current.parameters[key] ?? field.default ?? ''
          const change = (next: string | number | boolean) => { touch(); setChanges((previous) => ({ ...previous, [key]: next })) }
          return field.type === 'boolean'
            ? <label className="draft-checkbox" key={key}><input type="checkbox" checked={value === true} onChange={(event) => change(event.target.checked)} />{field.title}</label>
            : <label key={key}>{field.title}{field.enum
              ? <select value={String(value)} onChange={(event) => change(event.target.value)}>{field.enum.map((item) => <option key={item}>{item}</option>)}</select>
              : <input type={field.type === 'string' ? 'text' : 'number'} value={String(value)} required
                  min={field.minimum} max={field.maximum} step={field.type === 'integer' ? 1 : 'any'}
                  onChange={(event) => change(field.type === 'string' || event.target.value === '' ? event.target.value : Number(event.target.value))} />}</label>
        })}
      </fieldset>
      {current.validation.length > 0 && <ul className="draft-validation" aria-label="Draft validation">
        {current.validation.map((issue, index) => <li key={`${issue.code}:${index}`} data-code={issue.code}><AlertTriangle size={14} />{issue.message}</li>)}
      </ul>}
      {!submitted && <div className="draft-actions">
        <Button type="submit" variant="ghost" disabled={!dirty || busy || Boolean(conflict)}><Save />Save changes</Button>
        <Button type="button" onClick={() => void confirm()} disabled={dirty || busy || Boolean(conflict) || current.validation.length > 0}>
          <Check />Confirm submission
        </Button>
      </div>}
      {submitted && <p className="draft-submitted" role="status"><Check size={16} />Submitted / {current.job_id}</p>}
    </form>
  </section>
}

function DraftFormView({ spec, sessionId, drafts, onConfirmed }: ViewRendererProps) {
  const [catalog, setCatalog] = useState<CatalogApp[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const draft = drafts?.[String(spec.props.draft_id)]
  useEffect(() => {
    const controller = new AbortController()
    request<CatalogApp[]>('/catalog', { signal: controller.signal }).then(setCatalog, (reason) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Catalog unavailable')
    })
    return () => controller.abort()
  }, [])
  if (!sessionId || !draft) return <div className="surface-error" role="alert">Draft unavailable in this session.</div>
  if (error) return <div className="surface-error" role="alert">{error}</div>
  if (!catalog) return <p role="status">Loading application catalog...</p>
  return <DraftEditor draft={draft} catalog={catalog} sessionId={sessionId} onConfirmed={onConfirmed} />
}

DraftFormView.kind = 'draft_form'
DraftFormView.version = 1
export default DraftFormView
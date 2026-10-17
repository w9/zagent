import { Check, CircleCheck, Maximize2, RefreshCw, Save, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ApiError, request } from '../../../lib/api'
import { plural } from '../../../lib/format'
import type { DraftState, JobState } from '../../../lib/events'
import { Badge } from '../../ui/badge'
import { Button } from '../../ui/button'
import { Checkbox, Field, Input, Select } from '../../ui/field'
import { Notice } from '../../ui/notice'
import { Spinner } from '../../ui/spinner'
import { ArtifactMeta } from '../artifact-meta'
import type { ArtifactRendererProps } from '../artifact-renderer'

export type CatalogApp = {
  id: string; title: string; layout: string[]
  parameters: { properties: Record<string, {
    type: 'string' | 'number' | 'integer' | 'boolean'; title: string
    minimum?: number; maximum?: number; enum?: string[]; default?: string | number | boolean
  }> }
}

/** The confirm response: the submitted job and the job card its confirmation published. */
export type ConfirmedJob = JobState & { artifact_id: string | null }

type Change = { field: string; before: unknown; after: unknown }

/** Parameters a draft card lists before "Open draft"; the editor shows them all. */
const PREVIEW_FIELDS = 4

function DraftStatus({ draft }: { draft: DraftState }) {
  const submitted = draft.status === 'submitted'
  return (
    <>
      <span>Version {draft.version}</span>
      <Badge tone={submitted ? 'success' : 'neutral'}>{submitted ? 'Submitted' : 'Draft'}</Badge>
    </>
  )
}

/** A draft as its card in the conversation shows it: application, status and the main fields. */
export function DraftPreview({ draft, catalog, onMaximize, readOnly = false }: {
  draft: DraftState; catalog: CatalogApp[]; onMaximize?: () => void; readOnly?: boolean
}) {
  const application = catalog.find((item) => item.id === draft.app_id)
  const fields = (application?.layout ?? Object.keys(draft.parameters)).filter((key) => key in draft.parameters)
  const shown = fields.slice(0, PREVIEW_FIELDS)
  const submitted = draft.status === 'submitted'
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
        <span className="font-medium text-default wrap-anywhere">{application?.title ?? draft.app_id}</span>
        <DraftStatus draft={draft} />
      </div>
      <dl className="grid min-w-0 grid-cols-1 gap-x-4 gap-y-1 text-sm @medium:grid-cols-2">
        <div className="flex min-w-0 gap-2">
          <dt className="shrink-0 text-muted">Specimen query</dt>
          <dd className="min-w-0 font-mono text-default wrap-anywhere">{draft.specimen_handle ?? 'Not set'}</dd>
        </div>
        {shown.map((key) => (
          <div key={key} className="flex min-w-0 gap-2">
            <dt className="shrink-0 text-muted">{application?.parameters.properties[key]?.title ?? key}</dt>
            <dd className="min-w-0 text-default wrap-anywhere">{String(draft.parameters[key])}</dd>
          </div>
        ))}
      </dl>
      {fields.length > shown.length && (
        <p className="text-xs text-muted">{plural(fields.length - shown.length, 'more parameter', 'more parameters')}</p>
      )}
      {draft.validation.length > 0 && !submitted && (
        <p className="inline-flex items-center gap-1.5 text-sm text-warning">
          <TriangleAlert aria-hidden className="size-icon-sm shrink-0" />
          {plural(draft.validation.length, 'issue', 'issues')} to resolve before confirming
        </p>
      )}
      {submitted ? (
        <p role="status" className="inline-flex items-center gap-2 text-sm text-success">
          <CircleCheck aria-hidden className="size-icon" />Submitted / {draft.job_id}
        </p>
      ) : (
        onMaximize && (
          <div>
            <Button size="sm" icon={Maximize2} onClick={onMaximize}>{readOnly ? 'Open draft' : 'Review and confirm'}</Button>
          </div>
        )
      )}
    </div>
  )
}

export function DraftEditor({ draft, catalog, sessionId, onConfirmed, readOnly = false }: {
  draft: DraftState; catalog: CatalogApp[]; sessionId: string; onConfirmed?: (job: ConfirmedJob) => void; readOnly?: boolean
}) {
  const [saved, setSaved] = useState<DraftState | null>(null)
  const current = saved && (saved.version >= draft.version || saved.status === 'submitted') ? saved : draft
  const [changes, setChanges] = useState<Record<string, string | number | boolean>>({})
  const [baseHash, setBaseHash] = useState<string | null>(null)
  const [selection, setSelection] = useState<string | null>(null)
  const [appChoice, setAppChoice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [conflict, setConflict] = useState<{ current: DraftState; changes: Change[] } | null>(null)
  const selectedApp = appChoice ?? current.app_id
  const application = catalog.find((item) => item.id === selectedApp)
  const dirty = baseHash !== null
  const submitted = current.status === 'submitted'
  const path = `/sessions/${sessionId}/drafts/${current.draft_id}`

  function touch() { if (!baseHash) setBaseHash(current.content_hash) }

  function reset(next: DraftState) {
    setSaved(next); setChanges({}); setSelection(null); setAppChoice(null); setBaseHash(null)
  }

  function failed(reason: unknown) {
    if (reason instanceof ApiError && reason.body.current) {
      const next = reason.body.current as DraftState
      if (reason.status === 409) setConflict({ current: next, changes: (reason.body.changes ?? []) as Change[] })
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
      reset(result)
    } catch (reason) { failed(reason) }
    finally { setBusy(false) }
  }

  async function confirm() {
    setBusy(true); setError(null)
    try {
      const job = await request<ConfirmedJob>(`${path}/confirm`, { method: 'POST', body: JSON.stringify({ content_hash: current.content_hash }) })
      setSaved({ ...current, status: 'submitted', job_id: job.job_id })
      onConfirmed?.(job)
    } catch (reason) { failed(reason) }
    finally { setBusy(false) }
  }

  return (
    <section aria-label="Analysis draft" className="flex min-w-0 flex-col">
      <ArtifactMeta><DraftStatus draft={current} /></ArtifactMeta>
      {conflict && (
        <Notice
          tone="warning"
          role="alert"
          title="Draft changed"
          className="mb-6"
          action={<Button size="sm" icon={RefreshCw} onClick={() => { reset(conflict.current); setConflict(null); setError(null) }}>Review current draft</Button>}
        >
          {conflict.changes.map((change) => (
            <p key={change.field}>
              <strong className="font-medium">{change.field}</strong>: {String(change.before ?? 'unset')} to {String(change.after ?? 'unset')}
            </p>
          ))}
        </Notice>
      )}
      {error && !conflict && <Notice tone="danger" role="alert" className="mb-6">{error}</Notice>}
      <form onSubmit={(event) => { event.preventDefault(); void save() }} className="flex flex-col gap-6">
        <fieldset disabled={busy || submitted || readOnly || Boolean(conflict)} className="grid min-w-0 grid-cols-1 gap-4 @medium:grid-cols-2">
          <Field label="Application">
            <Select value={selectedApp} onChange={(event) => {
              touch(); setAppChoice(event.target.value)
              const chosen = catalog.find((item) => item.id === event.target.value)!
              setChanges(Object.fromEntries(Object.entries(chosen.parameters.properties).map(([key, field]) => [key, field.default ?? ''])))
            }}>
              {catalog.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
            </Select>
          </Field>
          <Field label="Specimen query">
            <Input value={selection ?? current.specimen_handle ?? ''} placeholder="query-0001" pattern="query-[0-9]{4,}" required
              className="font-mono" onChange={(event) => { touch(); setSelection(event.target.value) }} />
          </Field>
          {application?.layout.map((key) => {
            const field = application.parameters.properties[key]
            const value = changes[key] ?? current.parameters[key] ?? field.default ?? ''
            const change = (next: string | number | boolean) => { touch(); setChanges((previous) => ({ ...previous, [key]: next })) }
            if (field.type === 'boolean') {
              return <Checkbox key={key} label={field.title} checked={value === true} onChange={(event) => change(event.target.checked)} className="self-end" />
            }
            return (
              <Field key={key} label={field.title}>
                {field.enum ? (
                  <Select value={String(value)} onChange={(event) => change(event.target.value)}>
                    {field.enum.map((item) => <option key={item}>{item}</option>)}
                  </Select>
                ) : (
                  <Input
                    type={field.type === 'string' ? 'text' : 'number'} value={String(value)} required
                    min={field.minimum} max={field.maximum} step={field.type === 'integer' ? 1 : 'any'}
                    onChange={(event) => change(field.type === 'string' || event.target.value === '' ? event.target.value : Number(event.target.value))}
                  />
                )}
              </Field>
            )
          })}
        </fieldset>
        {current.validation.length > 0 && (
          <Notice tone="warning" title="Resolve before confirming">
            <ul aria-label="Draft validation" className="flex flex-col gap-1">
              {current.validation.map((issue, index) => <li key={`${issue.code}:${index}`} data-code={issue.code}>{issue.message}</li>)}
            </ul>
          </Notice>
        )}
        {submitted ? (
          <p role="status" className="inline-flex items-center gap-2 text-sm text-success">
            <CircleCheck aria-hidden className="size-icon" />Submitted / {current.job_id}
          </p>
        ) : readOnly ? (
          <p className="text-sm text-muted">Read-only in an archived session.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button type="submit" icon={Save} disabled={!dirty || busy || Boolean(conflict)}>Save changes</Button>
            <Button variant="primary" icon={Check} onClick={() => void confirm()}
              disabled={dirty || busy || Boolean(conflict) || current.validation.length > 0}>
              Confirm submission
            </Button>
          </div>
        )}
      </form>
    </section>
  )
}

// Every draft card and the panel share one catalog request; a failure is retried on next use.
let catalogRequest: Promise<CatalogApp[]> | undefined
function loadCatalog() {
  catalogRequest ??= request<CatalogApp[]>('/catalog').catch((reason: unknown) => {
    catalogRequest = undefined
    throw reason
  })
  return catalogRequest
}

function DraftFormArtifact({ spec, display, sessionId, drafts, onConfirmed, onMaximize, readOnly }: ArtifactRendererProps) {
  const [catalog, setCatalog] = useState<CatalogApp[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const draft = drafts?.[String(spec.props.draft_id)]
  useEffect(() => {
    let active = true
    loadCatalog().then(
      (apps) => { if (active) setCatalog(apps) },
      (reason) => { if (active) setError(reason instanceof Error ? reason.message : 'Catalog unavailable') },
    )
    return () => { active = false }
  }, [])
  if (!sessionId || !draft) return <Notice tone="danger" role="alert">Draft unavailable in this session.</Notice>
  if (error) return <Notice tone="danger" role="alert">{error}</Notice>
  if (!catalog) return <p role="status" className="inline-flex items-center gap-2 text-sm text-muted"><Spinner />Loading application catalog…</p>
  if (display === 'inline') return <DraftPreview draft={draft} catalog={catalog} onMaximize={onMaximize} readOnly={readOnly} />
  return <DraftEditor draft={draft} catalog={catalog} sessionId={sessionId} onConfirmed={onConfirmed} readOnly={readOnly} />
}

DraftFormArtifact.kind = 'draft_form'
DraftFormArtifact.version = 1

export default DraftFormArtifact

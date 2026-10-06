import { ChevronRight, CircleCheck, CircleX } from 'lucide-react'
import { useId, useState } from 'react'
import { toolView } from '../../lib/events'
import type { StepState } from '../../lib/events'
import { IconButton } from '../ui/icon-button'
import { Spinner } from '../ui/spinner'
import type { ViewLink } from './transcript-text'

function formatArguments(argumentsJson: string) {
  try {
    return JSON.stringify(JSON.parse(argumentsJson), null, 2)
  } catch {
    return argumentsJson
  }
}

type Tool = NonNullable<StepState['tools']>[number]

const plural = (count: unknown, one: string, many: string) =>
  typeof count === 'number' ? `${count} ${count === 1 ? one : many}` : many

const TOOL_LABELS: Record<string, { pending: string; failed: string; done: (result: Record<string, any>) => string }> = {
  find_patients: {
    pending: 'Looking up patients',
    failed: 'Patient lookup failed',
    done: (r) => `Found ${plural(r.count, 'patient', 'patients')}`,
  },
  find_specimens: {
    pending: 'Searching specimens',
    failed: 'Specimen search failed',
    done: (r) => `Found ${plural(r.count, 'specimen', 'specimens')}`,
  },
  find_libraries: {
    pending: 'Searching libraries',
    failed: 'Library search failed',
    done: (r) => `Found ${plural(r.count, 'library', 'libraries')}`,
  },
  push_view: { pending: 'Publishing view', failed: 'View rejected', done: () => 'Published' },
  update_draft: {
    pending: 'Updating draft',
    failed: 'Draft update failed',
    done: (r) => (r.draft?.version === 1 ? 'Created draft' : 'Updated draft'),
  },
  show_jobs: { pending: 'Loading jobs', failed: 'Job view failed', done: () => 'Showed' },
  get_job: {
    pending: 'Checking job',
    failed: 'Job lookup failed',
    done: (r) => (r.status ? `Checked job (${r.status})` : 'Checked job'),
  },
  search_knowledge: {
    pending: 'Searching knowledge base',
    failed: 'Knowledge search failed',
    done: (r) => `Searched knowledge base (${plural(r.matches?.length, 'match', 'matches')})`,
  },
  get_document: {
    pending: 'Checking document',
    failed: 'Document lookup failed',
    done: (r) => (r.document ? `Checked ${r.document}` : 'Checked document'),
  },
  read_document: {
    pending: 'Reading document',
    failed: 'Document read failed',
    done: (r) => (r.document ? `Read ${r.document} L${r.start_line}–${r.end_line}` : 'Read document'),
  },
  lookup_term: {
    pending: 'Looking up term',
    failed: 'Term lookup failed',
    done: (r) => (r.term ? `Looked up ${r.term}` : 'Looked up term'),
  },
  query_reference: {
    pending: 'Querying reference table',
    failed: 'Reference query failed',
    done: (r) => `Queried ${r.table ?? 'reference table'} (${plural(r.rows?.length, 'row', 'rows')})`,
  },
  submit_job: { pending: 'Submitting job', failed: 'Submission failed', done: () => 'Submitted job' },
}

function toolLabel({ name, result }: Tool) {
  const label = TOOL_LABELS[name]
  if (!label) return result ? (result.error ? `${name} failed` : `Ran ${name}`) : `Running ${name}`
  if (!result) return label.pending
  return result.error ? label.failed : label.done(result)
}

function StepSummary({ step, viewLink }: { step: StepState; viewLink?: ViewLink }) {
  if (!/^Agent step \d+$/.test(step.title)) return step.title
  const tools = step.tools ?? []
  if (tools.length)
    return tools.map((tool, index) => {
      const label = toolLabel(tool)
      const view = toolView(tool)
      return (
        <span key={tool.call_id}>
          {index ? `, ${label[0].toLowerCase()}${label.slice(1)}` : label}
          {view && <> “{viewLink ? viewLink(view.id, view.title) : view.title}”</>}
        </span>
      )
    })
  if (step.status === 'running') return 'Thinking'
  if (step.status === 'failed') return 'Step failed'
  return step.detail === 'Request declined' ? 'Declined request' : 'Wrote response'
}

const preClassName = 'max-h-64 overflow-auto font-mono text-xs leading-normal whitespace-pre-wrap wrap-anywhere text-default'

/**
 * One agent step: a summary line that expands to its tool calls. A disclosure button rather than
 * <summary>, because the summary can contain view links (no nested controls, A11Y-01).
 */
export function StepMarker({ step, viewLink, defaultOpen = false }: { step: StepState; viewLink?: ViewLink; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  const detailsId = useId()
  return (
    <div data-testid="step-marker" data-status={step.status} data-open={open} className="text-sm text-muted">
      <div
        className="flex cursor-pointer items-start gap-2 py-1 transition-colors hover:text-default"
        onClick={(event) => {
          if (!(event.target as Element).closest('a, button')) setOpen(!open)
        }}
      >
        <IconButton
          size="sm"
          label="Step details"
          icon={ChevronRight}
          aria-expanded={open}
          aria-controls={detailsId}
          onClick={() => setOpen(!open)}
          className="-my-1.5 -ml-1.5 [&_svg]:transition-transform aria-expanded:[&_svg]:rotate-90"
        />
        {step.status === 'running' ? (
          <Spinner className="mt-0.5 size-icon-sm text-accent" />
        ) : step.status === 'failed' ? (
          <CircleX aria-hidden className="mt-0.5 size-icon-sm shrink-0 text-danger" />
        ) : (
          <CircleCheck aria-hidden className="mt-0.5 size-icon-sm shrink-0" />
        )}
        <span data-testid="step-title" className="min-w-0 flex-1 wrap-anywhere">
          {step.status === 'running' ? (
            <span className="shimmer"><StepSummary step={step} viewLink={viewLink} /></span>
          ) : (
            <StepSummary step={step} viewLink={viewLink} />
          )}
        </span>
        <span className={step.status === 'failed' ? 'shrink-0 text-xs text-danger' : 'shrink-0 text-xs'}>
          {step.status === 'running' ? 'In progress' : step.status === 'failed' ? 'Failed' : 'Complete'}
        </span>
      </div>
      <div id={detailsId} hidden={!open} className="mt-2 mb-1 ml-3 flex flex-col gap-4 border-l border-subtle pl-4">
        {step.detail && <p className="whitespace-pre-wrap wrap-anywhere">{step.detail}</p>}
        {step.tools?.map((tool) => (
          <section key={tool.call_id} className="flex min-w-0 flex-col gap-1.5">
            <h4 className="font-mono text-xs font-medium text-strong wrap-anywhere">{tool.name}</h4>
            <span className="text-xs">Arguments</span>
            <pre className={preClassName}>{formatArguments(tool.arguments)}</pre>
            <span className="text-xs">Result</span>
            <pre className={preClassName}>{tool.result ? JSON.stringify(tool.result, null, 2) : 'Pending…'}</pre>
          </section>
        ))}
      </div>
    </div>
  )
}

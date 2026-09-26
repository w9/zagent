import { ChevronRight, CircleCheck, CircleX, LoaderCircle } from 'lucide-react'
import type { StepState } from '../lib/events'

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

const TOOL_LABELS: Record<string, {
  pending: string
  failed: string
  done: (result: Record<string, any>) => string
}> = {
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
  push_view: {
    pending: 'Publishing view',
    failed: 'View rejected',
    done: (r) => (r.title ? `Published “${r.title}”` : 'Published view'),
  },
  update_draft: {
    pending: 'Updating draft',
    failed: 'Draft update failed',
    done: (r) => (r.draft?.version === 1 ? 'Created draft' : 'Updated draft'),
  },
  show_jobs: {
    pending: 'Loading jobs',
    failed: 'Job view failed',
    done: (r) => (r.kind === 'job_card' ? 'Showed job' : `Showed ${plural(r.count, 'job', 'jobs')}`),
  },
  get_job: {
    pending: 'Checking job',
    failed: 'Job lookup failed',
    done: (r) => (r.status ? `Checked job (${r.status})` : 'Checked job'),
  },
  search_knowledge: {
    pending: 'Searching SOPs',
    failed: 'SOP search failed',
    done: (r) => `Searched SOPs (${plural(r.matches?.length, 'match', 'matches')})`,
  },
  read_document: {
    pending: 'Reading document',
    failed: 'Document read failed',
    done: (r) => (r.document ? `Read ${r.document} L${r.start_line}–${r.end_line}` : 'Read document'),
  },
  submit_job: {
    pending: 'Submitting job',
    failed: 'Submission failed',
    done: () => 'Submitted job',
  },
}

function toolLabel({ name, result }: Tool) {
  const label = TOOL_LABELS[name]
  if (!label) return result ? (result.error ? `${name} failed` : `Ran ${name}`) : `Running ${name}`
  if (!result) return label.pending
  return result.error ? label.failed : label.done(result)
}

export function stepSummary(step: StepState) {
  if (!/^Agent step \d+$/.test(step.title)) return step.title
  const labels = (step.tools ?? []).map(toolLabel)
  if (labels.length)
    return labels.map((label, index) => (index ? label[0].toLowerCase() + label.slice(1) : label)).join(', ')
  if (step.status === 'running') return 'Thinking'
  if (step.status === 'failed') return 'Step failed'
  return step.detail === 'Request declined' ? 'Declined request' : 'Wrote response'
}

export function StepMarker({ step }: { step: StepState }) {
  return (
    <details className={`step-marker ${step.status}`} data-testid="step-marker">
      <summary>
        <ChevronRight className="step-chevron" size={13} aria-hidden="true" />
        {step.status === 'running' ? (
          <LoaderCircle className="spin" size={14} aria-hidden="true" />
        ) : step.status === 'failed' ? (
          <CircleX size={14} aria-hidden="true" />
        ) : (
          <CircleCheck size={14} aria-hidden="true" />
        )}
        <span className="step-title">{stepSummary(step)}</span>
        <span className="step-status">
          {step.status === 'running'
            ? 'In progress'
            : step.status === 'failed'
              ? 'Failed'
              : 'Complete'}
        </span>
      </summary>
      {step.detail && <p>{step.detail}</p>}
      {step.tools?.map((tool) => (
        <div className="step-tool" key={tool.call_id}>
          <h4>{tool.name}</h4>
          <span className="tool-detail-label">Arguments</span>
          <pre>{formatArguments(tool.arguments)}</pre>
          <span className="tool-detail-label">Result</span>
          <pre>{tool.result ? JSON.stringify(tool.result, null, 2) : 'Pending...'}</pre>
        </div>
      ))}
    </details>
  )
}

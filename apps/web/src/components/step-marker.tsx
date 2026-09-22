import { ChevronRight, CircleCheck, CircleX, LoaderCircle } from 'lucide-react'
import type { StepState } from '../lib/events'

function formatArguments(argumentsJson: string) {
  try {
    return JSON.stringify(JSON.parse(argumentsJson), null, 2)
  } catch {
    return argumentsJson
  }
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
        <span className="step-title">{step.title}</span>
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

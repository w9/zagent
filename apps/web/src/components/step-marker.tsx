import { ChevronRight, CircleCheck, CircleX, LoaderCircle } from 'lucide-react'
import type { StepState } from '../lib/events'

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
    </details>
  )
}

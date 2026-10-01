import { cn } from '../../lib/utils'
import { StatusDot } from '../ui/status-dot'

export type Connection = 'connecting' | 'live' | 'reconnecting'
export type TurnStatusLabel = 'Connecting' | 'Reconnecting' | 'Responding' | 'Failed' | 'Complete' | 'Ready'

// DOMAIN-03: responding is accent and live; connecting is warning; failed is danger.
const tones = {
  Connecting: 'warning',
  Reconnecting: 'warning',
  Responding: 'accent',
  Failed: 'danger',
  Complete: 'neutral',
  Ready: 'neutral',
} as const
const labelClassNames = {
  Connecting: 'text-warning',
  Reconnecting: 'text-warning',
  Responding: 'text-accent',
  Failed: 'text-danger',
  Complete: 'text-muted',
  Ready: 'text-muted',
}

export function TurnStatus({ status }: { status: TurnStatusLabel }) {
  return (
    <span
      role="status"
      aria-label="Conversation turn status"
      data-testid="conversation-turn-status"
      className={cn('inline-flex items-center gap-1.5 text-xs whitespace-nowrap', labelClassNames[status])}
    >
      <StatusDot tone={tones[status]} live={status === 'Responding' || status.endsWith('ecting')} />
      {status}
    </span>
  )
}

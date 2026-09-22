import { CircleMinus } from 'lucide-react'
import type { RefusalCode, RefusedState } from '../lib/events'

const labels: Record<RefusalCode, string> = {
  out_of_domain: 'Outside workbench scope',
  unsupported_capability: 'Capability unavailable',
  requires_human_authority: 'Human authorization required',
  unsafe_request: 'Request not permitted',
}

export function RefusalChip({ refusal }: { refusal: RefusedState }) {
  return (
    <div className="refusal-message" data-testid="refusal" data-reason={refusal.code}>
      <span className="refusal-chip" role="status">
        <CircleMinus size={14} aria-hidden="true" />
        {labels[refusal.code]}
      </span>
      <p className="message-text">{refusal.message}</p>
    </div>
  )
}
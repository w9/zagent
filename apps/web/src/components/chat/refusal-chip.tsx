import { CircleMinus } from 'lucide-react'
import type { RefusalCode, RefusedState } from '../../lib/events'
import { Badge } from '../ui/badge'

const labels: Record<RefusalCode, string> = {
  out_of_domain: 'Outside workbench scope',
  unsupported_capability: 'Capability unavailable',
  requires_human_authority: 'Human authorization required',
  unsafe_request: 'Request not permitted',
}

/** A declined request. Info, never danger: refusing is correct behavior (DOMAIN-02). */
export function RefusalChip({ refusal }: { refusal: RefusedState }) {
  return (
    <div data-testid="refusal" data-reason={refusal.code} className="flex min-w-0 flex-col items-start gap-2">
      <Badge tone="info" icon={CircleMinus} role="status">{labels[refusal.code]}</Badge>
      <p className="text-md whitespace-pre-wrap wrap-anywhere">{refusal.message}</p>
    </div>
  )
}

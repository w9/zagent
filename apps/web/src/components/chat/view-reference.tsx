import { Link } from '@tanstack/react-router'
import { Activity, ArrowUpRight, ChartColumn, FileText, Table2 } from 'lucide-react'
import type { PushedView } from '../../lib/views'

const kindIcons: Record<string, typeof Table2> = {
  table: Table2,
  chart: ChartColumn,
  draft_form: FileText,
  job_card: Activity,
}

/** A host-owned link from the transcript to a published view on the working surface. */
export function ViewReference({ sessionId, view }: { sessionId: string; view: PushedView }) {
  const Icon = kindIcons[view.spec.kind] ?? Table2
  return (
    <Link
      data-testid="view-reference"
      data-view-id={view.id}
      to="/sessions/$sessionId"
      params={{ sessionId }}
      search={{ view: view.id, panel: 'surface' }}
      className="inline-flex max-w-full items-center gap-2 rounded-md border border-default bg-surface px-3 py-2 text-sm text-default transition-colors hover:border-strong hover:bg-hover"
    >
      <Icon aria-hidden className="size-icon shrink-0 text-muted" />
      <span className="min-w-0 wrap-anywhere">{String(view.spec.props.title ?? view.spec.kind)}</span>
      <ArrowUpRight aria-hidden className="size-icon-sm shrink-0 text-muted" />
    </Link>
  )
}

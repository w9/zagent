import { cva } from 'class-variance-authority'
import { ArrowUpRight, FileText, TriangleAlert } from 'lucide-react'
import type { PrivacyBinding } from '../../lib/api'
import { citationLabel, lineLabel, sourceName } from '../../lib/citations'
import type { Citation, CitedRead } from '../../lib/citations'
import { Tooltip } from '../ui/tooltip'
import { PrivacyText } from './transcript-text'

const PREVIEW_LINES = 8

const chipVariants = cva(
  'inline rounded-sm border px-1 py-0.5 text-left font-mono text-xs box-decoration-clone wrap-anywhere transition-colors [&_svg]:mr-1 [&_svg]:inline [&_svg]:size-icon-sm [&_svg]:align-text-bottom',
  {
    variants: {
      verified: {
        true: 'border-default bg-surface text-default hover:border-strong hover:bg-hover',
        false: 'border-warning bg-warning-subtle text-warning hover:border-strong',
      },
    },
  },
)

function Preview({ citation, read, bindings }: { citation: Citation; read?: CitedRead; bindings: PrivacyBinding[] }) {
  if (!read) {
    return (
      <div className="flex flex-col gap-2">
        <p className="flex items-start gap-1.5 font-medium text-warning">
          <TriangleAlert aria-hidden className="mt-0.5 size-icon-sm shrink-0" />
          Not in what the assistant read
        </p>
        <p className="text-muted">
          No document read in this conversation covers <span className="font-mono text-xs wrap-anywhere">{`${citation.document}@${citation.version}`}</span>{' '}
          {citation.start === citation.end ? `line ${citation.start}` : `lines ${citation.start}\u2013${citation.end}`}. Open the source to check the citation.
        </p>
      </div>
    )
  }
  const cited = read.lines.filter((line) => line.number >= citation.start && line.number <= citation.end)
  const hidden = cited.length - PREVIEW_LINES
  return (
    <div className="flex flex-col gap-2">
      <div>
        <p className="font-medium text-strong wrap-anywhere">{read.title}</p>
        <p className="font-mono text-xs text-muted">
          {[sourceName(read.source), `version ${read.version}`, read.status].filter(Boolean).join(' · ')}
        </p>
      </div>
      <ol aria-label="Cited lines" className="flex flex-col gap-1">
        {cited.slice(0, PREVIEW_LINES).map((line) => (
          <li key={line.number} className="flex gap-2">
            <span className="w-6 shrink-0 text-right font-mono text-xs text-muted tabular-nums">{line.number}</span>
            <span className="min-w-0 wrap-anywhere"><PrivacyText text={line.text} bindings={bindings} /></span>
          </li>
        ))}
      </ol>
      {hidden > 0 && <p className="text-xs text-muted">{hidden} more cited lines on the intranet</p>}
      <p className="flex items-center gap-1 text-xs text-muted">
        <ArrowUpRight aria-hidden className="size-icon-sm shrink-0" />
        Opens the source in a new tab
      </p>
    </div>
  )
}

/** An inline citation that previews what the assistant read and opens the source on the intranet. */
export function CitationChip({
  citation,
  read,
  bindings = [],
  open,
  onOpen,
}: {
  citation: Citation
  read?: CitedRead
  bindings?: PrivacyBinding[]
  open?: boolean
  onOpen: (citation: Citation, read?: CitedRead) => void
}) {
  const Icon = read ? FileText : TriangleAlert
  return (
    <Tooltip variant="preview" open={open} content={<Preview citation={citation} read={read} bindings={bindings} />}>
      <button
        type="button"
        data-testid="citation-chip"
        data-document={citation.document}
        data-lines={`${citation.start}-${citation.end}`}
        data-verified={Boolean(read)}
        className={chipVariants({ verified: Boolean(read) })}
        onClick={() => onOpen(citation, read)}
      >
        <Icon aria-hidden />
        {citationLabel(citation, read)} · {lineLabel(citation)}
        {!read && <span className="sr-only">, unverified</span>}
      </button>
    </Tooltip>
  )
}

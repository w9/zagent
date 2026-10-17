import { Maximize2, Minimize2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { artifactTitle } from '../../lib/artifacts'
import type { PublishedArtifact } from '../../lib/artifacts'
import { cn } from '../../lib/utils'
import { Eyebrow } from '../ui/eyebrow'
import { IconButton } from '../ui/icon-button'
import { ArtifactBoundary } from './artifact-boundary'
import { artifactKind } from './artifact-kind'

/**
 * An artifact in the conversation. Inline it shows its content; while maximized it is a placeholder,
 * so live state is never rendered twice.
 */
export function ArtifactCard({
  artifact,
  maximized = false,
  onMaximize,
  onMinimize,
  children,
  className,
}: {
  artifact: PublishedArtifact
  maximized?: boolean
  onMaximize: () => void
  onMinimize: () => void
  /** The inline rendering; not mounted while maximized. */
  children: ReactNode
  className?: string
}) {
  const { label, icon: Icon } = artifactKind(artifact.spec.kind)
  const title = artifactTitle(artifact)
  return (
    <article
      aria-label={title}
      data-testid="artifact-card"
      data-artifact-id={artifact.id}
      data-kind={artifact.spec.kind}
      data-state={maximized ? 'maximized' : 'inline'}
      className={cn(
        '@container flex min-w-0 flex-col rounded-md border bg-surface',
        maximized ? 'border-accent' : 'border-default',
        className,
      )}
    >
      <header className={cn('flex min-w-0 items-center gap-3 px-3 py-2', !maximized && 'border-b border-subtle')}>
        <Icon aria-hidden className="size-icon shrink-0 text-muted" />
        <div className="flex min-w-0 flex-1 flex-col">
          <Eyebrow>{label}</Eyebrow>
          <h3 className="text-sm font-medium text-strong wrap-anywhere">{title}</h3>
        </div>
        {maximized && <span className="hidden shrink-0 text-xs text-muted @narrow:inline">Shown in panel</span>}
        {maximized ? (
          <IconButton label="Minimize" icon={Minimize2} data-action="minimize" onClick={onMinimize} />
        ) : (
          <IconButton label="Maximize" icon={Maximize2} data-action="maximize" onClick={onMaximize} />
        )}
      </header>
      {!maximized && (
        <div className="flex min-w-0 flex-col p-3">
          <ArtifactBoundary>{children}</ArtifactBoundary>
        </div>
      )}
    </article>
  )
}

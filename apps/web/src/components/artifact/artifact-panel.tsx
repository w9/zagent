import { Minimize2 } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { artifactTitle } from '../../lib/artifacts'
import type { PublishedArtifact } from '../../lib/artifacts'
import { cn } from '../../lib/utils'
import { Button } from '../ui/button'
import { IconButton } from '../ui/icon-button'
import { Notice } from '../ui/notice'
import { PanelHeader } from '../ui/panel-header'
import { Spinner } from '../ui/spinner'
import { ArtifactBoundary } from './artifact-boundary'
import { artifactKind } from './artifact-kind'

/** The right panel, holding the one maximized artifact. It exists only while something is maximized. */
export function ArtifactPanel({
  artifact,
  loading = false,
  onMinimize,
  children,
  className,
}: {
  /** The maximized artifact, or undefined when the requested one is not in this session. */
  artifact?: PublishedArtifact
  /** The session is still loading, so a missing artifact may yet arrive. */
  loading?: boolean
  onMinimize: () => void
  /** The maximized rendering of `artifact`. */
  children?: ReactNode
  className?: string
}) {
  const content = useRef<HTMLDivElement>(null)
  useEffect(() => {
    content.current?.focus({ preventScroll: true })
  }, [artifact?.id])

  const kind = artifact && artifactKind(artifact.spec.kind)
  return (
    <aside
      aria-label="Maximized artifact"
      className={cn('@container flex min-h-0 min-w-0 flex-1 flex-col bg-subtle', className)}
    >
      <PanelHeader
        title={artifact ? artifactTitle(artifact) : 'Artifact'}
        subtitle={kind?.label}
        actions={<IconButton label="Minimize" icon={Minimize2} onClick={onMinimize} />}
      />
      {artifact ? (
        <div
          ref={content}
          tabIndex={-1}
          key={artifact.id}
          data-testid="maximized-artifact"
          data-artifact-id={artifact.id}
          data-kind={artifact.spec.kind}
          className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-6 -outline-offset-2 animate-fade @medium:px-6"
        >
          <ArtifactBoundary>{children}</ArtifactBoundary>
        </div>
      ) : loading ? (
        <div role="status" className="flex flex-1 items-center justify-center gap-2 text-sm text-muted">
          <Spinner />
          Opening artifact…
        </div>
      ) : (
        <div ref={content} tabIndex={-1} className="px-4 py-6 -outline-offset-2 @medium:px-6">
          <Notice
            tone="danger"
            role="alert"
            title="Artifact unavailable"
            action={<Button size="sm" icon={Minimize2} onClick={onMinimize}>Minimize</Button>}
          >
            This artifact is not available in this session.
          </Notice>
        </div>
      )}
    </aside>
  )
}

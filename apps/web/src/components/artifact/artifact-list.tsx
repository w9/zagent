import { ChevronUp, Layers } from 'lucide-react'
import { useState } from 'react'
import { artifactTitle } from '../../lib/artifacts'
import type { PublishedArtifact } from '../../lib/artifacts'
import { plural } from '../../lib/format'
import { Button } from '../ui/button'
import { IconButton } from '../ui/icon-button'
import { Menu, MenuItem } from '../ui/menu'
import { artifactKind } from './artifact-kind'

const collapsedKey = 'zagent.artifact-list'

function loadCollapsed(): boolean {
  try {
    return localStorage.getItem(collapsedKey) === 'collapsed'
  } catch {
    return false
  }
}

function saveCollapsed(collapsed: boolean) {
  try {
    if (collapsed) localStorage.setItem(collapsedKey, 'collapsed')
    else localStorage.removeItem(collapsedKey)
  } catch {
    // Remembering the list's state is a convenience.
  }
}

/**
 * An index of the session's artifacts, for the conversation header's actions. From `@xwide` it is
 * a small card floating under the header's right corner, which the user can collapse into a
 * button; in narrower conversations it is a button that opens a menu, so it never covers the
 * transcript. Choosing an artifact maximizes it. The conversation panel must be `relative`.
 */
export function ArtifactList({
  artifacts,
  onSelect,
  defaultCollapsed,
}: {
  artifacts: PublishedArtifact[]
  onSelect: (id: string) => void
  /** Starts collapsed or expanded; without it, the user's last choice. */
  defaultCollapsed?: boolean
}) {
  const [collapsed, setCollapsed] = useState(() => defaultCollapsed ?? loadCollapsed())
  const count = plural(artifacts.length, 'artifact', 'artifacts')
  const collapse = (next: boolean) => {
    setCollapsed(next)
    saveCollapsed(next)
  }

  return (
    <>
      <Menu
        modal={false}
        className="max-w-preview"
        trigger={<Button size="sm" icon={Layers} className="@xwide:hidden">{count}</Button>}
      >
        {artifacts.map((artifact) => {
          const title = artifactTitle(artifact)
          return (
            <MenuItem key={artifact.id} icon={artifactKind(artifact.spec.kind).icon} onSelect={() => onSelect(artifact.id)}>
              <span title={title} className="min-w-0 truncate">{title}</span>
            </MenuItem>
          )
        })}
      </Menu>
      {collapsed ? (
        <Button size="sm" icon={Layers} aria-expanded={false} className="hidden @xwide:inline-flex" onClick={() => collapse(false)}>
          {count}
        </Button>
      ) : (
        <nav
          aria-label="Artifacts"
          data-testid="artifact-list"
          className="absolute top-16 right-4 z-10 hidden w-48 flex-col rounded-lg border border-default bg-surface shadow-md animate-fade @medium:right-6 @xwide:flex"
        >
          <div className="flex items-center justify-between gap-2 border-b border-subtle py-1 pr-1 pl-3">
            <span className="font-mono text-xs text-muted">{count}</span>
            <IconButton size="sm" label="Collapse artifact list" icon={ChevronUp} onClick={() => collapse(true)} />
          </div>
          <ul className="flex max-h-64 flex-col overflow-y-auto overscroll-contain p-1">
            {artifacts.map((artifact) => {
              const { icon: Icon } = artifactKind(artifact.spec.kind)
              const title = artifactTitle(artifact)
              return (
                <li key={artifact.id}>
                  <button
                    type="button"
                    title={title}
                    data-artifact-id={artifact.id}
                    onClick={() => onSelect(artifact.id)}
                    className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm text-default transition-colors -outline-offset-2 hover:bg-hover"
                  >
                    <Icon aria-hidden className="mt-0.5 size-icon-sm shrink-0 text-muted" />
                    <span className="line-clamp-2 min-w-0 wrap-anywhere">{title}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </nav>
      )}
    </>
  )
}

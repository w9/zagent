import type { ReactNode } from 'react'

/** Counts and status at the top of a maximized artifact; its title and kind are in the panel header. */
export function ArtifactMeta({ children }: { children: ReactNode }) {
  return <div className="mb-4 flex flex-wrap items-center gap-2 text-sm text-muted">{children}</div>
}

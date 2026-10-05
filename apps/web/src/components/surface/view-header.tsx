import type { ReactNode } from 'react'
import { Eyebrow } from '../ui/eyebrow'

/** Kind, title and counts at the top of every view on the working surface. */
export function ViewHeader({ kind, title, meta }: { kind: string; title: string; meta?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-1">
      <Eyebrow>{kind}</Eyebrow>
      <h3 className="text-xl font-medium text-strong wrap-anywhere">{title}</h3>
      {meta && <div className="flex flex-wrap items-center gap-2 text-sm text-muted">{meta}</div>}
    </header>
  )
}

import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'
import { Eyebrow } from './eyebrow'

/** What an empty area holds and what to do next (CONTENT-03). `display` uses the serif headline. */
export function EmptyState({
  icon: Icon,
  eyebrow,
  title,
  description,
  action,
  display = false,
  className,
}: {
  icon: LucideIcon
  eyebrow?: ReactNode
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
  display?: boolean
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 px-6 py-12 text-center', className)}>
      <span className="mb-1 grid size-12 place-items-center rounded-full bg-muted text-muted">
        <Icon aria-hidden className="size-icon-lg" />
      </span>
      {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
      <h3 className={display ? 'max-w-prose font-serif text-2xl text-strong' : 'text-base font-medium text-strong'}>
        {title}
      </h3>
      {description && <p className="max-w-prose text-sm text-muted">{description}</p>}
      {action}
    </div>
  )
}

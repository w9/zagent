import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

/** The h-bar header at the top of a panel. The panel must be an `@container`. */
export function PanelHeader({
  title,
  subtitle,
  subtitleTestId,
  actions,
  className,
}: {
  title: string
  subtitle?: string
  subtitleTestId?: string
  actions?: ReactNode
  className?: string
}) {
  return (
    <header className={cn('flex h-bar shrink-0 items-center justify-between gap-3 border-b border-subtle px-4 @medium:px-6', className)}>
      <div className="min-w-0">
        <h2 className="text-base font-semibold text-strong">{title}</h2>
        {subtitle && (
          <p data-testid={subtitleTestId} title={subtitle} className="truncate font-mono text-xs text-muted">
            {subtitle}
          </p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-3 text-muted">{actions}</div>}
    </header>
  )
}

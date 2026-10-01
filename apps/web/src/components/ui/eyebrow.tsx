import { cn } from '../../lib/utils'
import type { ReactNode } from 'react'

/** Small uppercase mono label above a title. */
export function Eyebrow({ className, children }: { className?: string; children: ReactNode }) {
  return <span className={cn('font-mono text-xs tracking-caps text-muted uppercase wrap-anywhere', className)}>{children}</span>
}

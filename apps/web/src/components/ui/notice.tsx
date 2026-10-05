import { cva } from 'class-variance-authority'
import { CircleAlert, CircleCheck, Info, TriangleAlert } from 'lucide-react'
import type { ComponentProps, ReactNode } from 'react'
import { cn } from '../../lib/utils'

type NoticeTone = 'danger' | 'warning' | 'info' | 'success'

const noticeVariants = cva('flex items-start gap-2 rounded-md border px-3 py-2 text-sm', {
  variants: {
    tone: {
      danger: 'border-danger bg-danger-subtle',
      warning: 'border-warning bg-warning-subtle',
      info: 'border-info bg-info-subtle',
      success: 'border-success bg-success-subtle',
    },
  },
})
const toneClassNames = {
  danger: 'text-danger',
  warning: 'text-warning',
  info: 'text-info',
  success: 'text-success',
}
const icons = { danger: CircleAlert, warning: TriangleAlert, info: Info, success: CircleCheck }

/** An inline message about the surrounding content. Callers choose the role (alert or status). */
export function Notice({
  tone,
  title,
  action,
  className,
  children,
  ...props
}: Omit<ComponentProps<'div'>, 'title'> & { tone: NoticeTone; title?: ReactNode; action?: ReactNode }) {
  const Icon = icons[tone]
  return (
    <div className={cn(noticeVariants({ tone }), className)} {...props}>
      <Icon aria-hidden className={cn('mt-0.5 size-icon shrink-0', toneClassNames[tone])} />
      <div className="flex min-w-0 flex-1 flex-col items-start gap-1 text-default wrap-anywhere">
        {title && <p className={cn('font-medium', toneClassNames[tone])}>{title}</p>}
        {children}
        {action && <div className="mt-1">{action}</div>}
      </div>
    </div>
  )
}

import { cva } from 'class-variance-authority'
import type { VariantProps } from 'class-variance-authority'
import type { LucideIcon } from 'lucide-react'
import type { ComponentProps } from 'react'
import { cn } from '../../lib/utils'

const badgeVariants = cva(
  'inline-flex max-w-full items-center gap-1 rounded-sm border px-1.5 py-0.5 text-xs font-medium [&_svg]:size-icon-sm [&_svg]:shrink-0',
  {
    variants: {
      tone: {
        neutral: 'border-default bg-muted text-default',
        accent: 'border-accent bg-accent-subtle text-accent',
        danger: 'border-danger bg-danger-subtle text-danger',
        warning: 'border-warning bg-warning-subtle text-warning',
        info: 'border-info bg-info-subtle text-info',
        success: 'border-success bg-success-subtle text-success',
      },
    },
    defaultVariants: { tone: 'neutral' },
  },
)

export type Tone = NonNullable<VariantProps<typeof badgeVariants>['tone']>

export function Badge({
  tone,
  icon: Icon,
  className,
  children,
  ...props
}: ComponentProps<'span'> & VariantProps<typeof badgeVariants> & { icon?: LucideIcon }) {
  return (
    <span className={cn(badgeVariants({ tone }), className)} {...props}>
      {Icon && <Icon aria-hidden />}
      <span className="min-w-0 wrap-anywhere">{children}</span>
    </span>
  )
}

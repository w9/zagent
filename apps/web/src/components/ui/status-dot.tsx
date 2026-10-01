import { cva } from 'class-variance-authority'
import type { VariantProps } from 'class-variance-authority'
import { cn } from '../../lib/utils'

const dotVariants = cva('inline-block size-1.5 shrink-0 rounded-full bg-current', {
  variants: {
    tone: {
      neutral: 'text-muted',
      accent: 'text-accent',
      danger: 'text-danger',
      warning: 'text-warning',
      info: 'text-info',
      success: 'text-success',
    },
    live: { true: 'animate-pulse', false: '' },
  },
  defaultVariants: { tone: 'neutral', live: false },
})

/** A small status indicator. Always pair it with text (COLOR-04). */
export function StatusDot({ tone, live, className }: VariantProps<typeof dotVariants> & { className?: string }) {
  return <span aria-hidden className={cn(dotVariants({ tone, live }), className)} />
}

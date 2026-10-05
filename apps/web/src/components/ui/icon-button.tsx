import { cva } from 'class-variance-authority'
import type { VariantProps } from 'class-variance-authority'
import type { LucideIcon } from 'lucide-react'
import type { ComponentProps } from 'react'
import { cn } from '../../lib/utils'
import { Tooltip } from './tooltip'

const iconButtonVariants = cva(
  'inline-flex shrink-0 items-center justify-center rounded-md transition-colors disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        ghost:
          'text-muted hover:bg-hover hover:text-default active:bg-muted aria-pressed:bg-selected aria-pressed:text-accent aria-checked:bg-selected aria-checked:text-strong',
        secondary: 'border border-default bg-surface text-default hover:border-strong hover:bg-hover active:bg-muted',
        primary: 'bg-accent text-on-accent hover:bg-accent-hover active:bg-accent-hover',
      },
      size: {
        sm: 'size-control-sm [&_svg]:size-icon-sm',
        md: 'size-control [&_svg]:size-icon',
      },
    },
    defaultVariants: { variant: 'ghost', size: 'md' },
  },
)

/** A button with only an icon. The label is its accessible name and its tooltip (A11Y-03). */
export function IconButton({
  label,
  icon: Icon,
  variant,
  size,
  tooltipSide,
  type = 'button',
  className,
  ...props
}: Omit<ComponentProps<'button'>, 'children'> &
  VariantProps<typeof iconButtonVariants> & {
    label: string
    icon: LucideIcon
    tooltipSide?: 'top' | 'right' | 'bottom' | 'left'
  }) {
  return (
    <Tooltip content={label} side={tooltipSide}>
      <button type={type} aria-label={label} className={cn(iconButtonVariants({ variant, size }), className)} {...props}>
        <Icon aria-hidden />
      </button>
    </Tooltip>
  )
}

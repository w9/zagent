import { cva } from 'class-variance-authority'
import type { VariantProps } from 'class-variance-authority'
import type { LucideIcon } from 'lucide-react'
import type { ComponentProps } from 'react'
import { cn } from '../../lib/utils'
import { Spinner } from './spinner'

const buttonVariants = cva(
  'inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap transition-colors disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-icon',
  {
    variants: {
      variant: {
        primary: 'bg-accent text-on-accent hover:bg-accent-hover active:bg-accent-hover',
        secondary: 'border border-default bg-surface text-default hover:border-strong hover:bg-hover active:bg-muted',
        ghost: 'text-muted hover:bg-hover hover:text-default active:bg-muted',
        danger: 'border border-danger bg-surface text-danger hover:bg-danger-subtle active:bg-danger-subtle',
      },
      size: {
        sm: 'h-control-sm px-2 text-sm [&_svg]:size-icon-sm',
        md: 'h-control px-3 text-base',
        lg: 'h-control-lg px-4 text-base',
      },
    },
    defaultVariants: { variant: 'secondary', size: 'md' },
  },
)

export type ButtonProps = ComponentProps<'button'> &
  VariantProps<typeof buttonVariants> & { icon?: LucideIcon; loading?: boolean }

export function Button({
  variant,
  size,
  icon: Icon,
  loading = false,
  disabled,
  type = 'button',
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    >
      {loading ? <Spinner /> : Icon && <Icon aria-hidden />}
      {children}
    </button>
  )
}

import * as RadixMenu from '@radix-ui/react-dropdown-menu'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

/** A list of actions that opens from a trigger button. */
export function Menu({
  trigger,
  open,
  onOpenChange,
  onCloseAutoFocus,
  modal = true,
  className,
  children,
}: {
  trigger: ReactNode
  open?: boolean
  onOpenChange?: (open: boolean) => void
  onCloseAutoFocus?: (event: Event) => void
  modal?: boolean
  /** Layout classes for the list, such as a maximum width. */
  className?: string
  children: ReactNode
}) {
  return (
    <RadixMenu.Root open={open} onOpenChange={onOpenChange} modal={modal}>
      <RadixMenu.Trigger asChild>{trigger}</RadixMenu.Trigger>
      <RadixMenu.Portal>
        <RadixMenu.Content
          align="end"
          sideOffset={4}
          collisionPadding={8}
          onCloseAutoFocus={onCloseAutoFocus}
          className={cn('z-50 flex min-w-48 flex-col rounded-lg border border-subtle bg-surface p-1 shadow-md animate-fade', className)}
        >
          {children}
        </RadixMenu.Content>
      </RadixMenu.Portal>
    </RadixMenu.Root>
  )
}

export function MenuItem({
  icon: Icon,
  disabled,
  onSelect,
  children,
}: {
  icon?: LucideIcon
  disabled?: boolean
  onSelect: () => void
  children: ReactNode
}) {
  return (
    <RadixMenu.Item
      disabled={disabled}
      onSelect={onSelect}
      className="flex h-control cursor-pointer items-center gap-2 rounded-md px-2 text-sm text-default transition-colors -outline-offset-2 data-disabled:pointer-events-none data-disabled:opacity-50 data-highlighted:bg-hover [&_svg]:size-icon-sm [&_svg]:text-muted"
    >
      {Icon && <Icon aria-hidden />}
      {children}
    </RadixMenu.Item>
  )
}

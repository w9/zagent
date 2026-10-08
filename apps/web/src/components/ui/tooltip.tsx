import * as RadixTooltip from '@radix-ui/react-tooltip'
import { cva } from 'class-variance-authority'
import type { ReactNode } from 'react'

const tooltipVariants = cva('z-50 shadow-md animate-fade', {
  variants: {
    variant: {
      label: 'max-w-64 rounded-sm bg-inverse px-2 py-1 text-xs text-inverse',
      preview: 'max-w-preview rounded-lg border border-default bg-surface p-3 text-sm text-default',
    },
  },
  defaultVariants: { variant: 'label' },
})

export function Tooltip({
  content,
  side = 'top',
  open,
  variant,
  children,
}: {
  content: ReactNode
  side?: 'top' | 'right' | 'bottom' | 'left'
  open?: boolean
  variant?: 'label' | 'preview'
  children: ReactNode
}) {
  return (
    <RadixTooltip.Provider delayDuration={300}>
      <RadixTooltip.Root open={open}>
        <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
        <RadixTooltip.Portal>
          <RadixTooltip.Content
            side={side}
            sideOffset={4}
            collisionPadding={8}
            className={tooltipVariants({ variant })}
          >
            {content}
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  )
}

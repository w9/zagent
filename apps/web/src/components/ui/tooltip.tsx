import * as RadixTooltip from '@radix-ui/react-tooltip'
import type { ReactNode } from 'react'

export function Tooltip({
  content,
  side = 'top',
  open,
  children,
}: {
  content: ReactNode
  side?: 'top' | 'right' | 'bottom' | 'left'
  open?: boolean
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
            className="z-50 max-w-64 rounded-sm bg-inverse px-2 py-1 text-xs text-inverse shadow-md animate-fade"
          >
            {content}
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  )
}

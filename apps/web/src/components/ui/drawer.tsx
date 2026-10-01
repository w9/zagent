import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { IconButton } from './icon-button'

/** A panel that slides over the page from the left, for navigation on narrow screens. */
export function Drawer({
  title,
  open,
  onOpenChange,
  trigger,
  children,
}: {
  title: string
  open: boolean
  onOpenChange: (open: boolean) => void
  trigger?: ReactNode
  children: ReactNode
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger && <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>}
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-30 bg-overlay animate-fade" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed inset-y-0 left-0 z-40 flex w-drawer max-w-full flex-col bg-subtle shadow-lg animate-fade"
        >
          <div className="flex h-bar shrink-0 items-center justify-between gap-2 border-b border-subtle pr-2 pl-4">
            <Dialog.Title className="text-base font-semibold text-strong">{title}</Dialog.Title>
            <Dialog.Close asChild>
              <IconButton label={`Close ${title.toLowerCase()}`} icon={X} />
            </Dialog.Close>
          </div>
          <div className="flex min-h-0 flex-1 flex-col">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

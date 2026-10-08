import * as RadixDialog from '@radix-ui/react-dialog'
import type { ReactNode } from 'react'

/** A modal question with its answers as buttons; the first button gets focus. */
export function Dialog({
  open,
  onOpenChange,
  title,
  children,
  actions,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  children: ReactNode
  actions: ReactNode
}) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        {/* Same level as drawers so a dialog opened from the session drawer dims it too. */}
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-overlay animate-fade" />
        <RadixDialog.Content
          role="alertdialog"
          className="fixed inset-4 z-40 m-auto flex h-fit max-w-96 flex-col gap-4 rounded-lg bg-surface p-6 shadow-lg animate-fade"
        >
          <RadixDialog.Title className="text-lg font-semibold text-strong wrap-anywhere">{title}</RadixDialog.Title>
          <RadixDialog.Description asChild>
            <div className="flex flex-col gap-2 text-sm text-default">{children}</div>
          </RadixDialog.Description>
          <div className="flex flex-wrap justify-end gap-2">{actions}</div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  )
}

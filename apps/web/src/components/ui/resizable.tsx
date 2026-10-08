import { Group, Panel, Separator } from 'react-resizable-panels'
import type { ComponentProps } from 'react'
import { cn } from '../../lib/utils'

/** Panels resized by dragging a handle or with arrow keys on it (react-resizable-panels). */
export const ResizablePanelGroup = Group
export const ResizablePanel = Panel

/** A one-pixel divider that turns accent while hovered or dragged. */
export function ResizableHandle({ className, ...props }: ComponentProps<typeof Separator>) {
  return (
    <Separator
      className={cn(
        'border-subtle transition-colors aria-[orientation=horizontal]:border-t aria-[orientation=vertical]:border-l data-[separator=active]:border-accent data-[separator=hover]:border-accent',
        className,
      )}
      {...props}
    />
  )
}

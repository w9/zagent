import { X } from 'lucide-react'
import { useEffect, useEffectEvent, useState } from 'react'
import type { ReactNode } from 'react'
import { IconButton } from './icon-button'

const dismissAfterMs = 8000

/** A brief confirmation at the bottom of the screen; it waits while pointed at or focused. */
export function Toast({ action, onDismiss, children }: { action?: ReactNode; onDismiss: () => void; children: ReactNode }) {
  const [paused, setPaused] = useState(false)
  const dismiss = useEffectEvent(onDismiss)
  useEffect(() => {
    if (paused) return
    const timer = setTimeout(() => dismiss(), dismissAfterMs)
    return () => clearTimeout(timer)
  }, [paused])
  return (
    <div
      role="status"
      onPointerEnter={() => setPaused(true)}
      onPointerLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      className="fixed inset-x-4 bottom-4 z-50 mx-auto flex w-fit max-w-96 items-center gap-2 rounded-lg border border-subtle bg-surface py-1.5 pr-1.5 pl-4 text-sm text-default shadow-md animate-enter"
    >
      <span className="min-w-0 flex-1 wrap-anywhere">{children}</span>
      {action}
      <IconButton size="sm" label="Dismiss" icon={X} onClick={onDismiss} />
    </div>
  )
}

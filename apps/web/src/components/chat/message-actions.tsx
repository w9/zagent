import { Check, Copy, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cn } from '../../lib/utils'
import { IconButton } from '../ui/icon-button'

/** Actions under an answer: copy its Markdown, and retry the latest conversation turn. */
export function MessageActions({
  text,
  onRetry,
  retryDisabled = false,
  className,
}: {
  /** The Markdown to copy; without it there is no Copy button. */
  text?: string
  /** Set only on the latest turn. */
  onRetry?: () => void
  retryDisabled?: boolean
  className?: string
}) {
  const [copy, setCopy] = useState<'copied' | 'failed' | null>(null)

  useEffect(() => {
    if (!copy) return
    const timer = setTimeout(() => setCopy(null), 2000)
    return () => clearTimeout(timer)
  }, [copy])

  return (
    // Relative, so the sr-only status stays inside the transcript's scroll area.
    <div role="group" aria-label="Message actions" className={cn('relative flex items-center gap-1', className)}>
      {text !== undefined && (
        <IconButton
          size="sm"
          label={copy === 'copied' ? 'Copied' : copy === 'failed' ? 'Copy failed' : 'Copy'}
          icon={copy === 'copied' ? Check : Copy}
          onClick={() => {
            // Rejects too when the clipboard is unavailable, as on insecure origins.
            Promise.resolve()
              .then(() => navigator.clipboard.writeText(text))
              .then(() => setCopy('copied'), () => setCopy('failed'))
          }}
        />
      )}
      {onRetry && <IconButton size="sm" label="Retry" icon={RefreshCw} disabled={retryDisabled} onClick={onRetry} />}
      <span role="status" className="sr-only">
        {copy === 'copied' ? 'Copied to clipboard' : copy === 'failed' ? 'Could not copy to clipboard' : ''}
      </span>
    </div>
  )
}

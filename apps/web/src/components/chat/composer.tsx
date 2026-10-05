import { ArrowUp } from 'lucide-react'
import { IconButton } from '../ui/icon-button'

/** The message box. Enter sends; Shift+Enter adds a line. */
export function Composer({
  value,
  onChange,
  onSubmit,
  disabled = false,
  canSend,
}: {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  disabled?: boolean
  canSend: boolean
}) {
  return (
    <form
      data-testid="composer"
      className="relative"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
    >
      <textarea
        aria-label="Message"
        placeholder="Message Zagent…"
        rows={3}
        maxLength={20000}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault()
            onSubmit()
          }
        }}
        className="block max-h-48 min-h-24 w-full resize-none rounded-lg border border-control bg-surface py-3 pr-12 pl-4 text-base text-default shadow-sm field-sizing-content disabled:cursor-not-allowed disabled:opacity-50 pointer-coarse:text-lg"
      />
      <IconButton
        type="submit"
        variant="primary"
        label="Send message"
        icon={ArrowUp}
        disabled={!canSend}
        className="absolute right-2 bottom-2"
      />
    </form>
  )
}

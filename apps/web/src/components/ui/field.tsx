import { createContext, useContext, useId } from 'react'
import type { ComponentProps, ReactNode } from 'react'
import { cn } from '../../lib/utils'

type FieldState = { id: string; messageId?: string; invalid: boolean }
const FieldContext = createContext<FieldState | null>(null)

const controlClassName =
  'w-full min-w-0 rounded-sm border border-control bg-surface px-2 text-base text-default disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-danger pointer-coarse:text-lg'

function useControl() {
  const field = useContext(FieldContext)
  return field
    ? { id: field.id, 'aria-describedby': field.messageId, 'aria-invalid': field.invalid || undefined }
    : {}
}

/** A labelled control with an optional hint or error below it. */
export function Field({
  label,
  hint,
  error,
  className,
  children,
}: {
  label: ReactNode
  hint?: ReactNode
  error?: ReactNode
  className?: string
  children: ReactNode
}) {
  const id = useId()
  const message = error ?? hint
  const messageId = message ? `${id}-message` : undefined
  return (
    <FieldContext value={{ id, messageId, invalid: Boolean(error) }}>
      <div className={cn('flex min-w-0 flex-col gap-1.5', className)}>
        <label htmlFor={id} className="text-sm text-default">{label}</label>
        {children}
        {message && (
          <p id={messageId} className={error ? 'text-xs text-danger' : 'text-xs text-muted'}>{message}</p>
        )}
      </div>
    </FieldContext>
  )
}

export function Input({ className, ...props }: ComponentProps<'input'>) {
  return <input {...useControl()} className={cn('h-control', controlClassName, className)} {...props} />
}

export function Select({ className, ...props }: ComponentProps<'select'>) {
  return <select {...useControl()} className={cn('h-control', controlClassName, className)} {...props} />
}

export function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return <textarea {...useControl()} className={cn('min-h-24 py-2', controlClassName, className)} {...props} />
}

export function Checkbox({ label, className, ...props }: Omit<ComponentProps<'input'>, 'type'> & { label: ReactNode }) {
  return (
    <label className={cn('inline-flex min-h-control items-center gap-2 text-sm text-default', className)}>
      <input type="checkbox" className="size-icon shrink-0 disabled:opacity-50" {...props} />
      {label}
    </label>
  )
}

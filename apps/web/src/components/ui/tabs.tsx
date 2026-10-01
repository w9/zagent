import type { LucideIcon } from 'lucide-react'
import { useRef } from 'react'
import { cn } from '../../lib/utils'

export type TabItem<Value extends string> = {
  value: Value
  label: string
  icon?: LucideIcon
  count?: number
  controls?: string
}

/** Underlined tabs with arrow-key navigation. */
export function Tabs<Value extends string>({
  label,
  items,
  value,
  onChange,
  className,
}: {
  label: string
  items: TabItem<Value>[]
  value: Value
  onChange: (value: Value) => void
  className?: string
}) {
  const tabs = useRef<(HTMLButtonElement | null)[]>([])
  function move(index: number) {
    const next = (index + items.length) % items.length
    tabs.current[next]?.focus()
    onChange(items[next].value)
  }
  return (
    <div role="tablist" aria-label={label} className={cn('flex shrink-0 gap-1 overflow-x-auto border-b border-subtle px-2', className)}>
      {items.map(({ value: itemValue, label: itemLabel, icon: Icon, count, controls }, index) => (
        <button
          key={itemValue}
          ref={(element) => { tabs.current[index] = element }}
          type="button"
          role="tab"
          aria-selected={itemValue === value}
          aria-controls={controls}
          tabIndex={itemValue === value ? 0 : -1}
          onClick={() => onChange(itemValue)}
          onKeyDown={(event) => {
            if (event.key === 'ArrowRight') move(index + 1)
            if (event.key === 'ArrowLeft') move(index - 1)
          }}
          className="inline-flex h-control shrink-0 items-center gap-1.5 border-b-2 border-transparent px-3 text-sm text-muted transition-colors hover:text-default aria-selected:border-accent aria-selected:text-strong [&_svg]:size-icon-sm"
        >
          {Icon && <Icon aria-hidden />}
          {itemLabel}
          {count !== undefined && <span className="font-mono text-xs text-muted">{count}</span>}
        </button>
      ))}
    </div>
  )
}

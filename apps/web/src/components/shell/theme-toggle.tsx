import { Monitor, Moon, Sun } from 'lucide-react'
import { setPreference, usePreference } from '../../lib/theme'
import type { ThemePreference } from '../../lib/theme'
import { IconButton } from '../ui/icon-button'

const options: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light theme', icon: Sun },
  { value: 'dark', label: 'Dark theme', icon: Moon },
  { value: 'system', label: 'Match system theme', icon: Monitor },
]

export function ThemeToggle() {
  const preference = usePreference()
  return (
    <div role="group" aria-label="Theme" className="inline-flex items-center gap-0.5 rounded-md border border-default p-0.5">
      {options.map(({ value, label, icon }) => (
        <IconButton
          key={value}
          size="sm"
          label={label}
          icon={icon}
          aria-pressed={preference === value}
          tooltipSide="bottom"
          onClick={() => setPreference(value)}
        />
      ))}
    </div>
  )
}

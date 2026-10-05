import { ScanEye } from 'lucide-react'
import type { ReactNode } from 'react'
import type { RuntimeHealth } from '../../lib/api'
import { Eyebrow } from '../ui/eyebrow'
import { IconButton } from '../ui/icon-button'
import { StatusDot } from '../ui/status-dot'
import { ThemeToggle } from './theme-toggle'
import { Wordmark } from './wordmark'

export function TopBar({
  menu,
  mode,
  xray,
}: {
  menu?: ReactNode
  mode?: RuntimeHealth['mode'] | null
  xray?: { active: boolean; onToggle: () => void }
}) {
  return (
    <header className="flex h-bar shrink-0 items-center gap-2 border-b border-subtle bg-surface px-2 tablet:gap-4 tablet:px-6">
      {menu && <div className="tablet:hidden">{menu}</div>}
      <Wordmark />
      <span className="hidden border-l border-subtle pl-4 text-sm text-muted tablet:block">Clinical genomics</span>
      <div className="ml-auto flex items-center gap-2 tablet:gap-3">
        {xray && (
          <IconButton label="X-ray" icon={ScanEye} aria-pressed={xray.active} tooltipSide="bottom" onClick={xray.onToggle} />
        )}
        <ThemeToggle />
        <span className="hidden items-center gap-1.5 text-xs text-muted desktop:inline-flex">
          <Eyebrow>Local</Eyebrow>
          <StatusDot tone="success" />
          {mode ? mode[0].toUpperCase() + mode.slice(1) : 'Agent'}
        </span>
      </div>
    </header>
  )
}

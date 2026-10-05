import { PanelLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import type { RuntimeHealth } from '../../lib/api'
import { Drawer } from '../ui/drawer'
import { IconButton } from '../ui/icon-button'
import { Notice } from '../ui/notice'
import { TopBar } from './top-bar'

/** The page frame from DESIGN.md section 4: top bar, sessions (persistent or a drawer), content. */
export function AppShell({
  mode,
  xray,
  error,
  sidebar,
  drawerOpen,
  onDrawerOpenChange,
  children,
}: {
  mode?: RuntimeHealth['mode'] | null
  xray?: { active: boolean; onToggle: () => void }
  error?: string | null
  sidebar: (inDrawer: boolean) => ReactNode
  drawerOpen: boolean
  onDrawerOpenChange: (open: boolean) => void
  children: ReactNode
}) {
  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-surface text-default">
      <TopBar
        mode={mode}
        xray={xray}
        menu={
          <Drawer
            title="Sessions"
            open={drawerOpen}
            onOpenChange={onDrawerOpenChange}
            trigger={<IconButton label="Open sessions" icon={PanelLeft} tooltipSide="bottom" />}
          >
            {sidebar(true)}
          </Drawer>
        }
      />
      {error && (
        <Notice tone="danger" role="alert" className="mx-2 my-2 tablet:mx-6">{error}</Notice>
      )}
      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-sidebar shrink-0 flex-col border-r border-subtle bg-subtle tablet:flex wide:w-sidebar-wide">
          {sidebar(false)}
        </aside>
        <main className="flex min-h-0 min-w-0 flex-1 flex-col">{children}</main>
      </div>
    </div>
  )
}

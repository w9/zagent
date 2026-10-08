import { PanelLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { usePanelRef } from 'react-resizable-panels'
import type { RuntimeHealth } from '../../lib/api'
import { Drawer } from '../ui/drawer'
import { IconButton } from '../ui/icon-button'
import { Notice } from '../ui/notice'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '../ui/resizable'
import { loadSize, saveSize, token, useBreakpoint } from './layout'
import { TopBar } from './top-bar'

const sidebarKey = 'zagent.sidebar-width'

/** The page frame from DESIGN.md section 4: top bar, sessions (resizable or a drawer), content. */
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
  const tablet = useBreakpoint('tablet')
  const wide = useBreakpoint('wide')
  const sidebarPanel = usePanelRef()
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
      {/* Panels are added and removed in place, so the main panel never remounts. */}
      <ResizablePanelGroup
        id="app-layout"
        className="min-h-0 flex-1"
        onLayoutChanged={(_, meta) => {
          if (!meta.isUserInteraction) return
          // Keyboard resizes report the layout before the panel re-renders, so measure a frame later.
          requestAnimationFrame(() => {
            const width = sidebarPanel.current?.getSize().inPixels
            if (width) saveSize(sidebarKey, Math.round(width))
          })
        }}
      >
        {tablet && (
          <ResizablePanel
            id="sidebar-panel"
            panelRef={sidebarPanel}
            defaultSize={loadSize(sidebarKey) ?? token(wide ? '--width-sidebar-wide' : '--width-sidebar')}
            minSize={token('--panel-sidebar-min')}
            maxSize={token('--panel-sidebar-max')}
            groupResizeBehavior="preserve-pixel-size"
            className="flex flex-col"
          >
            <aside className="flex min-h-0 flex-1 flex-col bg-subtle">{sidebar(false)}</aside>
          </ResizablePanel>
        )}
        {tablet && <ResizableHandle aria-label="Resize session list" disableDoubleClick />}
        <ResizablePanel id="main-panel" minSize={tablet ? token('--panel-min') : undefined} className="flex flex-col">
          <main className="flex min-h-0 min-w-0 flex-1 flex-col">{children}</main>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}

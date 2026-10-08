import { MessageSquare, Table2 } from 'lucide-react'
import { useLayoutEffect } from 'react'
import type { ReactNode } from 'react'
import { useGroupRef } from 'react-resizable-panels'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '../ui/resizable'
import { Tabs } from '../ui/tabs'
import { loadSize, saveSize, token, useBreakpoint } from './layout'

export type WorkspacePanel = 'chat' | 'surface'

const chatKey = 'zagent.chat-share'
const split = (chatShare: number) => ({ 'chat-panel': chatShare, 'surface-panel': 100 - chatShare })

/** Conversation and working surface: tabs below `desktop:`, resizable side by side from it (DESIGN.md section 4). */
export function SessionLayout({
  panel,
  onPanelChange,
  viewCount,
  chat,
  surface,
}: {
  panel: WorkspacePanel
  onPanelChange: (panel: WorkspacePanel) => void
  viewCount: number
  chat: ReactNode
  surface: ReactNode
}) {
  const desktop = useBreakpoint('desktop')
  const ultra = useBreakpoint('ultra')
  const group = useGroupRef()
  // Below desktop the selected tab fills the group; the other panel stays mounted, hidden.
  const defaultShare = ultra ? 100 / 3 : (100 * 5) / 12
  const share = desktop ? (loadSize(chatKey) ?? defaultShare) : panel === 'chat' ? 100 : 0

  useLayoutEffect(() => {
    group.current?.setLayout(split(share))
  }, [group, share])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Tabs
        label="Workspace panels"
        className="desktop:hidden"
        value={panel}
        onChange={onPanelChange}
        items={[
          { value: 'chat', label: 'Conversation', icon: MessageSquare, controls: 'conversation-panel' },
          { value: 'surface', label: 'Working surface', icon: Table2, count: viewCount, controls: 'working-surface' },
        ]}
      />
      <ResizablePanelGroup
        id="workspace-layout"
        groupRef={group}
        defaultLayout={split(share)}
        disabled={!desktop}
        className="min-h-0 flex-1"
        onLayoutChanged={(layout, meta) => {
          const chatShare = (meta.requestedLayout ?? layout)['chat-panel']
          if (meta.isUserInteraction && chatShare) saveSize(chatKey, chatShare)
        }}
      >
        <ResizablePanel
          id="chat-panel"
          minSize={desktop ? token('--panel-min') : undefined}
          className={panel === 'chat' ? 'flex flex-col' : 'hidden flex-col desktop:flex'}
        >
          {chat}
        </ResizablePanel>
        {desktop && <ResizableHandle aria-label="Resize conversation" />}
        <ResizablePanel
          id="surface-panel"
          minSize={desktop ? token('--panel-min') : undefined}
          className={panel === 'surface' ? 'flex flex-col' : 'hidden flex-col desktop:flex'}
        >
          {surface}
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}

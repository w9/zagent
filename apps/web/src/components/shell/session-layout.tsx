import { MessageSquare, Table2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Tabs } from '../ui/tabs'

export type WorkspacePanel = 'chat' | 'surface'

/** Conversation and working surface: tabs below `desktop:`, side by side from it (DESIGN.md section 4). */
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
  return (
    <div className="flex min-h-0 flex-1 flex-col desktop:grid desktop:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] ultra:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
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
      <div className={panel === 'chat' ? 'flex min-h-0 flex-1 flex-col' : 'hidden min-h-0 flex-col desktop:flex'}>
        {chat}
      </div>
      <div
        className={
          panel === 'surface'
            ? 'flex min-h-0 flex-1 flex-col desktop:border-l desktop:border-subtle'
            : 'hidden min-h-0 flex-col desktop:flex desktop:border-l desktop:border-subtle'
        }
      >
        {surface}
      </div>
    </div>
  )
}

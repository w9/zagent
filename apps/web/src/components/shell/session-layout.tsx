import { useLayoutEffect } from 'react'
import type { ReactNode } from 'react'
import { useGroupRef } from 'react-resizable-panels'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '../ui/resizable'
import { loadSize, saveSize, token, useBreakpoint } from './layout'

const chatKey = 'zagent.chat-share'
const split = (chatShare: number) => ({ 'chat-panel': chatShare, 'artifact-panel': 100 - chatShare })

/**
 * The conversation, and the maximized artifact when there is one (DESIGN.md section 4). From
 * `desktop:` the artifact sits beside the conversation and is resizable; below it, it takes over.
 * Both panels stay mounted, so opening and closing the artifact never remounts the conversation.
 */
export function SessionLayout({
  maximized,
  chat,
  artifact,
}: {
  maximized: boolean
  chat: ReactNode
  artifact: ReactNode
}) {
  const desktop = useBreakpoint('desktop')
  const ultra = useBreakpoint('ultra')
  const group = useGroupRef()
  const sideBySide = desktop && maximized
  const defaultShare = ultra ? 100 / 3 : (100 * 5) / 12
  const share = !maximized ? 100 : desktop ? (loadSize(chatKey) ?? defaultShare) : 0

  useLayoutEffect(() => {
    group.current?.setLayout(split(share))
  }, [group, share])

  return (
    <ResizablePanelGroup
      id="workspace-layout"
      groupRef={group}
      defaultLayout={split(share)}
      disabled={!sideBySide}
      className="min-h-0 flex-1"
      onLayoutChanged={(layout, meta) => {
        const chatShare = (meta.requestedLayout ?? layout)['chat-panel']
        if (sideBySide && meta.isUserInteraction && chatShare) saveSize(chatKey, chatShare)
      }}
    >
      <ResizablePanel
        id="chat-panel"
        minSize={sideBySide ? token('--panel-min') : undefined}
        className={maximized && !desktop ? 'hidden flex-col' : 'flex flex-col'}
      >
        {chat}
      </ResizablePanel>
      {sideBySide && <ResizableHandle aria-label="Resize conversation" />}
      <ResizablePanel
        id="artifact-panel"
        minSize={sideBySide ? token('--panel-min') : undefined}
        className={maximized ? 'flex flex-col' : 'hidden flex-col'}
      >
        {artifact}
      </ResizablePanel>
    </ResizablePanelGroup>
  )
}

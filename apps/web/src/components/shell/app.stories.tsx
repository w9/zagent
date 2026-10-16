import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'
import { ChatPanel } from '../chat/chat-panel'
import { bindings, conversation, empty, personas, resolveHandle, responding, sessions, xray } from '../fixtures'
import { WorkingSurface } from '../surface/working-surface'
import { XrayContent } from '../xray/xray-panel'
import type { Projection } from '../../lib/events'
import { AppShell } from './app-shell'
import { SessionLayout } from './session-layout'
import type { WorkspacePanel } from './session-layout'
import { SessionList } from './session-list'

function Workspace({
  state = conversation,
  panel = 'chat',
  showXray = false,
  drawer = false,
  archivedSession = false,
  error,
}: {
  state?: Projection
  panel?: WorkspacePanel
  showXray?: boolean
  drawer?: boolean
  archivedSession?: boolean
  error?: string
}) {
  const [drawerOpen, setDrawerOpen] = useState(drawer)
  const [current, setCurrent] = useState(panel)
  const [selected, setSelected] = useState<string>()
  const [persona, setPersona] = useState('analyst')
  const session = sessions.find((item) => item.id === state.session_id) ?? sessions[0]
  return (
    <AppShell
      mode="replay"
      error={error}
      xray={{ active: showXray, onToggle: () => {} }}
      drawerOpen={drawerOpen}
      onDrawerOpenChange={setDrawerOpen}
      sidebar={(inDrawer) => (
        <SessionList
          sessions={sessions}
          selectedId={session.id}
          showTitle={!inDrawer}
          personas={personas}
          persona={persona}
          onPersonaChange={setPersona}
          onCreate={() => {}}
          onRename={async () => {}}
          onArchive={() => {}}
          onUnarchive={() => {}}
        />
      )}
    >
      {showXray ? (
        <section aria-label="X-ray inspection" className="@container flex min-h-0 flex-1 flex-col bg-surface">
          <XrayContent data={xray} />
        </section>
      ) : (
        <SessionLayout
          panel={current}
          onPanelChange={setCurrent}
          viewCount={state.views.length}
          chat={
            <ChatPanel
              sessionId={session.id}
              name={session.title}
              persona={personas.find((item) => item.id === session.persona)}
              state={state}
              bindings={bindings}
              connection="live"
              onSend={async () => {}}
              onRetry={async () => {}}
              onUnarchive={archivedSession ? () => {} : undefined}
              onOpenCitation={() => {}}
            />
          }
          surface={
            <WorkingSurface sessionId={session.id} views={state.views} selectedId={selected} onSelect={setSelected} resolveHandle={resolveHandle} readOnly={archivedSession} />
          }
        />
      )}
    </AppShell>
  )
}

const meta = {
  title: 'Shell/App',
  component: Workspace,
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof Workspace>
export default meta
type Story = StoryObj<typeof meta>

export const Conversation: Story = {}
export const WorkingSurfaceTab: Story = { args: { panel: 'surface' } }
export const Responding: Story = { args: { state: responding } }
export const NewSession: Story = { args: { state: empty } }
export const Xray: Story = { args: { showXray: true } }
export const SessionsDrawer: Story = { args: { drawer: true } }
export const ServiceError: Story = { args: { error: 'Sessions unavailable: request failed (503).' } }
export const ArchivedSession: Story = { args: { archivedSession: true } }

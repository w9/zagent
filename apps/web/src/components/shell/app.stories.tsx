import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'
import { ChatPanel } from '../chat/chat-panel'
import { bindings, conversation, empty, personas, resolveHandle, responding, sessions, xray } from '../fixtures'
import { ArtifactPanel } from '../artifact/artifact-panel'
import { ArtifactRenderer } from '../artifact/artifact-renderer'
import { XrayContent } from '../xray/xray-panel'
import type { Projection } from '../../lib/events'
import { AppShell } from './app-shell'
import { SessionLayout } from './session-layout'
import { SessionList } from './session-list'

function Workspace({
  state = conversation,
  maximized,
  showXray = false,
  drawer = false,
  archivedSession = false,
  error,
}: {
  state?: Projection
  maximized?: string
  showXray?: boolean
  drawer?: boolean
  archivedSession?: boolean
  error?: string
}) {
  const [drawerOpen, setDrawerOpen] = useState(drawer)
  const [current, setCurrent] = useState(maximized)
  const artifact = state.artifacts.find((item) => item.id === current)
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
          maximized={current !== undefined}
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
              maximizedArtifact={current}
              onMaximize={setCurrent}
              onMinimize={() => setCurrent(undefined)}
              resolveHandle={resolveHandle}
            />
          }
          artifact={
            current !== undefined && (
              <ArtifactPanel artifact={artifact} onMinimize={() => setCurrent(undefined)}>
                {artifact && (
                  <ArtifactRenderer
                    spec={artifact.spec}
                    display="maximized"
                    artifactId={artifact.id}
                    sessionId={session.id}
                    resolveHandle={resolveHandle}
                    readOnly={archivedSession}
                  />
                )}
              </ArtifactPanel>
            )
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
export const Maximized: Story = { args: { maximized: 'view-0001' } }
export const MaximizedChart: Story = { args: { maximized: 'view-0002' } }
export const Responding: Story = { args: { state: responding } }
export const NewSession: Story = { args: { state: empty } }
export const Xray: Story = { args: { showXray: true } }
export const SessionsDrawer: Story = { args: { drawer: true } }
export const ServiceError: Story = { args: { error: 'Sessions unavailable: request failed (503).' } }
export const ArchivedSession: Story = { args: { archivedSession: true } }

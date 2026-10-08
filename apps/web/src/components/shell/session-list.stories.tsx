import type { Meta, StoryObj } from '@storybook/react-vite'
import { personas, sessions } from '../fixtures'
import { SessionList } from './session-list'

const meta = {
  title: 'Shell/Session list',
  component: SessionList,
  parameters: { layout: 'fullscreen' },
  args: {
    sessions,
    selectedId: 'session-1',
    personas,
    persona: 'analyst',
    onCreate: () => {},
    onRename: async () => {},
    onArchive: () => {},
    onUnarchive: () => {},
  },
  decorators: [(Story) => <div className="flex h-dvh w-sidebar flex-col border-r border-subtle bg-subtle"><Story /></div>],
} satisfies Meta<typeof SessionList>
export default meta
type Story = StoryObj<typeof meta>

const archived = sessions.slice(1, 3).map((session) => ({ ...session, archived_at: '2026-10-02T09:00:00Z' }))

export const Populated: Story = {}
export const Creating: Story = { args: { creating: true } }
export const Empty: Story = { args: { sessions: [] } }
export const Many: Story = {
  args: {
    sessions: Array.from({ length: 30 }, (_, index) => ({ ...sessions[index % sessions.length], id: `session-${index + 1}` })),
  },
}
export const RestrictedPersona: Story = { args: { persona: 'qa-officer' } }
export const WithoutPersonas: Story = { args: { personas: [] } }
export const Archived: Story = { args: { view: 'archived', archived, selectedId: 'session-2' } }
export const ArchivedLoading: Story = { args: { view: 'archived', archived: null } }
export const ArchivedEmpty: Story = { args: { view: 'archived', archived: [] } }

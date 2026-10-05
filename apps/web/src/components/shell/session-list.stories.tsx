import type { Meta, StoryObj } from '@storybook/react-vite'
import { sessions } from '../fixtures'
import { SessionList } from './session-list'

const meta = {
  title: 'Shell/Session list',
  component: SessionList,
  parameters: { layout: 'fullscreen' },
  args: { sessions, selectedId: 'session-1', onCreate: () => {}, onRename: async () => {} },
  decorators: [(Story) => <div className="flex h-dvh w-sidebar flex-col border-r border-subtle bg-subtle"><Story /></div>],
} satisfies Meta<typeof SessionList>
export default meta
type Story = StoryObj<typeof meta>

export const Populated: Story = {}
export const Creating: Story = { args: { creating: true } }
export const Empty: Story = { args: { sessions: [] } }
export const Many: Story = {
  args: {
    sessions: Array.from({ length: 30 }, (_, index) => ({ ...sessions[index % sessions.length], id: `session-${index + 1}` })),
  },
}

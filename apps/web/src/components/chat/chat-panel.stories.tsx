import type { Meta, StoryObj } from '@storybook/react-vite'
import { bindings, conversation, empty, failed, responding } from '../fixtures'
import { ChatPanel } from './chat-panel'

const meta = {
  title: 'Chat/Chat panel',
  component: ChatPanel,
  parameters: { layout: 'fullscreen' },
  args: {
    sessionId: 'session-1',
    name: 'Intake review for the northgate cohort',
    state: conversation,
    bindings,
    connection: 'live',
    onSend: async () => {},
  },
  decorators: [(Story) => <div className="flex h-dvh flex-col"><Story /></div>],
} satisfies Meta<typeof ChatPanel>
export default meta
type Story = StoryObj<typeof meta>

export const Conversation: Story = {}
export const Responding: Story = { args: { state: responding } }
export const Failed: Story = { args: { state: failed } }
export const Reconnecting: Story = { args: { connection: 'reconnecting', error: 'Connection lost. Reconnecting in 3s.' } }
export const NewConversation: Story = { args: { state: empty, name: 'New session' } }
export const Opening: Story = { args: { state: null, connection: 'connecting' } }

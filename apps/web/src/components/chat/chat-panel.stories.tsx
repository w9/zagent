import type { Meta, StoryObj } from '@storybook/react-vite'
import { bindings, cited, conversation, empty, failed, personas, refused, responding, unanswered } from '../fixtures'
import { ChatPanel } from './chat-panel'

const meta = {
  title: 'Chat/Chat panel',
  component: ChatPanel,
  parameters: { layout: 'fullscreen' },
  args: {
    sessionId: 'session-1',
    name: 'Intake review for the northgate cohort',
    persona: personas[2],
    state: conversation,
    bindings,
    connection: 'live',
    onSend: async () => {},
    onRetry: async () => {},
    onOpenCitation: () => {},
  },
  decorators: [(Story) => <div className="flex h-dvh flex-col"><Story /></div>],
} satisfies Meta<typeof ChatPanel>
export default meta
type Story = StoryObj<typeof meta>

export const Conversation: Story = {}
export const Responding: Story = { args: { state: responding, persona: personas[0] } }
export const Failed: Story = { args: { state: failed } }
export const RefusedLast: Story = { args: { state: refused } }
export const FailedBeforeAnswer: Story = { args: { state: unanswered } }
export const Reconnecting: Story = { args: { connection: 'reconnecting', error: 'Connection lost. Reconnecting in 3s.' } }
export const NewConversation: Story = { args: { state: empty, name: 'New session' } }
export const Opening: Story = { args: { state: null, connection: 'connecting' } }
export const WithoutPersona: Story = { args: { persona: undefined } }
export const Archived: Story = { args: { onUnarchive: () => {} } }
export const WithCitations: Story = { args: { state: cited, name: 'Tumor coverage and the last swap' } }

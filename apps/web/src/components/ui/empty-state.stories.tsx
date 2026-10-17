import type { Meta, StoryObj } from '@storybook/react-vite'
import { Dna, Plus, Table2 } from 'lucide-react'
import { Button } from './button'
import { EmptyState } from './empty-state'

const meta = { title: 'Primitives/Empty state', component: EmptyState } satisfies Meta<typeof EmptyState>
export default meta
type Story = StoryObj<typeof meta>

export const Display: Story = {
  args: {
    icon: Dna,
    display: true,
    eyebrow: 'Intake review',
    title: 'A new conversation',
    description: 'Ask about specimens, libraries, sequencing runs or analysis jobs.',
  },
}

export const Quiet: Story = {
  args: {
    icon: Table2,
    title: 'No artifacts yet',
    description: 'Tables, charts and analysis drafts the agent publishes appear in the conversation.',
  },
}

export const NarrowWithAction: Story = {
  args: { icon: Table2, title: '' },
  render: () => (
    <div className="w-64 border border-dashed border-default">
      <EmptyState
        icon={Dna}
        display
        eyebrow="Session for the northgate pediatric cohort intake review"
        title="A new conversation"
        description="Ask about specimens, libraries, sequencing runs or analysis jobs."
        action={<Button icon={Plus}>New session</Button>}
      />
    </div>
  ),
}

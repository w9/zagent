import type { Meta, StoryObj } from '@storybook/react-vite'
import { Hash, Table2 } from 'lucide-react'
import { PanelHeader } from './panel-header'
import { StatusDot } from './status-dot'

const meta = {
  title: 'Primitives/Panel header',
  component: PanelHeader,
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof PanelHeader>
export default meta
type Story = StoryObj<typeof meta>

export const WithStatus: Story = {
  args: { title: 'Conversation' },
  render: () => (
    <div className="@container border-b border-subtle">
      <PanelHeader
        title="Conversation"
        subtitle="Intake review for the northgate pediatric cohort, second pass with matched normals"
        actions={
          <>
            <span className="inline-flex items-center gap-1.5 text-xs"><StatusDot tone="accent" live />Responding</span>
            <span className="inline-flex items-center gap-0.5 font-mono text-xs"><Hash aria-hidden className="size-icon-sm" />0042</span>
          </>
        }
      />
    </div>
  ),
}

export const Plain: Story = {
  args: { title: 'Specimens received this week' },
  render: () => (
    <div className="@container bg-subtle">
      <PanelHeader title="Specimens received this week" subtitle="Table" actions={<Table2 aria-hidden className="size-icon" />} />
    </div>
  ),
}

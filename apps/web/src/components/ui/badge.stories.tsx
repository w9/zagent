import type { Meta, StoryObj } from '@storybook/react-vite'
import { CircleCheck, CircleMinus } from 'lucide-react'
import { Badge } from './badge'
import { StatusDot } from './status-dot'

const meta = { title: 'Primitives/Badge and status dot', component: Badge } satisfies Meta<typeof Badge>
export default meta
type Story = StoryObj<typeof meta>

const tones = ['neutral', 'accent', 'danger', 'warning', 'info', 'success'] as const

export const Badges: Story = {
  render: () => (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        {tones.map((tone) => <Badge key={tone} tone={tone}>{tone}</Badge>)}
      </div>
      <div className="flex flex-wrap gap-2">
        <Badge tone="info" icon={CircleMinus}>Outside workbench scope</Badge>
        <Badge tone="success" icon={CircleCheck}>Submitted</Badge>
      </div>
      <div className="w-48">
        <Badge tone="info" icon={CircleMinus}>Human authorization required for this unusually long reason</Badge>
      </div>
    </div>
  ),
}

export const StatusDots: Story = {
  render: () => (
    <div className="flex flex-col gap-2 text-xs text-muted">
      {tones.map((tone) => (
        <span key={tone} className="inline-flex items-center gap-1.5"><StatusDot tone={tone} />{tone}</span>
      ))}
      <span className="inline-flex items-center gap-1.5 text-accent"><StatusDot tone="accent" live />Responding</span>
    </div>
  ),
}

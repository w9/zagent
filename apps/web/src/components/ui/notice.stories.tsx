import type { Meta, StoryObj } from '@storybook/react-vite'
import { RefreshCw } from 'lucide-react'
import { Button } from './button'
import { Notice } from './notice'

const meta = { title: 'Primitives/Notice', component: Notice } satisfies Meta<typeof Notice>
export default meta
type Story = StoryObj<typeof meta>

export const Tones: Story = {
  args: { tone: 'danger' },
  render: () => (
    <div className="flex max-w-prose flex-col gap-3">
      <Notice tone="danger" role="alert">Query unavailable: the handle expired.</Notice>
      <Notice tone="warning" title="Draft changed">
        <p><strong>parameters.min_vaf</strong>: 0.05 to 0.03</p>
      </Notice>
      <Notice tone="info">Results are from the synthetic cohort only.</Notice>
      <Notice tone="success" title="Submitted">job-0001 is queued.</Notice>
    </div>
  ),
}

export const WithAction: Story = {
  args: { tone: 'danger' },
  render: () => (
    <div className="flex flex-col gap-3">
      <div className="max-w-prose">
        <Notice tone="danger" role="alert" action={<Button size="sm" icon={RefreshCw}>Retry</Button>}>
          X-ray unavailable: request failed (503).
        </Notice>
      </div>
      <div className="w-64">
        <Notice tone="warning" title="Draft changed" action={<Button size="sm" icon={RefreshCw}>Review current draft</Button>}>
          Another edit changed parameters.min_depth_for_the_tumour_specimen_selection from 20 to 30.
        </Notice>
      </div>
    </div>
  ),
}

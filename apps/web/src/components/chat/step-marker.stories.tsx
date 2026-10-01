import type { Meta, StoryObj } from '@storybook/react-vite'
import type { ReactNode } from 'react'
import { failed, responding, steps } from '../fixtures'
import { StepMarker } from './step-marker'

const meta = {
  title: 'Chat/Step marker',
  component: StepMarker,
  args: { step: steps[0] },
  decorators: [(Story) => <div className="max-w-prose"><Story /></div>],
} satisfies Meta<typeof StepMarker>
export default meta
type Story = StoryObj<typeof meta>

const viewLink = (_: string, children: ReactNode) => (
  <a href="#view" className="text-accent underline decoration-dotted underline-offset-2">{children}</a>
)

export const Complete: Story = {}
export const PublishedView: Story = { args: { step: steps[1], viewLink } }
export const Running: Story = { args: { step: responding.steps.at(-1)! } }
export const Failed: Story = { args: { step: failed.steps.at(-1)!, defaultOpen: true } }
export const Expanded: Story = { args: { step: steps[0], defaultOpen: true } }
export const Custom: Story = {
  args: { step: { id: 'custom', seq: 1, title: 'Review intake', detail: '14 specimens reviewed against the intake checklist.', status: 'complete' }, defaultOpen: true },
}

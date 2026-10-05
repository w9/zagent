import type { Meta, StoryObj } from '@storybook/react-vite'
import { xray } from '../fixtures'
import { XrayContent } from './xray-panel'

const meta = {
  title: 'X-ray/X-ray',
  component: XrayContent,
  parameters: { layout: 'fullscreen' },
  args: { data: xray },
  decorators: [(Story) => <section aria-label="X-ray inspection" className="@container flex h-dvh flex-col bg-surface"><Story /></section>],
} satisfies Meta<typeof XrayContent>
export default meta
type Story = StoryObj<typeof meta>

export const Requests: Story = {}
export const NothingRecorded: Story = {
  args: { data: { ...xray, display: { ...xray.display, messages: [], refusals: [] }, executions: [], requests: [] } },
}

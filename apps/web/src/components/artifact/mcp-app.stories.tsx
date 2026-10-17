import type { Meta, StoryObj } from '@storybook/react-vite'
import jobsHtml from '../../../../../services/agent/zagent/resources/jobs.html?raw'
import { jobs } from '../fixtures'
import { McpAppFrame } from './mcp-app'

const meta = {
  title: 'Artifact/MCP app frame',
  component: McpAppFrame,
  parameters: { layout: 'fullscreen' },
  args: { title: 'Analysis jobs', html: jobsHtml, data: jobs, readData: async () => jobs, displayMode: 'fullscreen' },
  decorators: [(Story) => <div className="flex h-dvh flex-col bg-subtle p-6"><Story /></div>],
} satisfies Meta<typeof McpAppFrame>
export default meta
type Story = StoryObj<typeof meta>

export const RunningJob: Story = {}
export const NoJobs: Story = { args: { data: { jobs: [] } } }
export const Inline: Story = {
  args: { displayMode: 'inline', onRequestDisplayMode: () => {} },
  decorators: [(Story) => <div className="@container max-w-prose"><Story /></div>],
}

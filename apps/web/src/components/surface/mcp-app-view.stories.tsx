import type { Meta, StoryObj } from '@storybook/react-vite'
import jobsHtml from '../../../../../services/agent/zagent/resources/jobs.html?raw'
import { jobs } from '../fixtures'
import { McpAppFrame } from './mcp-app-view'

const meta = {
  title: 'Surface/MCP app frame',
  component: McpAppFrame,
  parameters: { layout: 'fullscreen' },
  args: { title: 'Analysis jobs', html: jobsHtml, data: jobs, readData: async () => jobs },
  decorators: [(Story) => <div className="flex h-dvh flex-col bg-subtle p-6"><Story /></div>],
} satisfies Meta<typeof McpAppFrame>
export default meta
type Story = StoryObj<typeof meta>

export const RunningJob: Story = {}
export const NoJobs: Story = { args: { data: { jobs: [] } } }

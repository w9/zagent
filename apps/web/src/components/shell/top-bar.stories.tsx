import type { Meta, StoryObj } from '@storybook/react-vite'
import { TopBar } from './top-bar'

const meta = {
  title: 'Shell/Top bar',
  component: TopBar,
  parameters: { layout: 'fullscreen' },
  args: { mode: 'replay' },
} satisfies Meta<typeof TopBar>
export default meta
type Story = StoryObj<typeof meta>

export const WithSession: Story = { args: { xray: { active: false, onToggle: () => {} } } }
export const XrayOn: Story = { args: { xray: { active: true, onToggle: () => {} } } }
export const WithoutSession: Story = { args: { mode: null } }

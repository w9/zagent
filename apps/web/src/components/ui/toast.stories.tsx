import type { Meta, StoryObj } from '@storybook/react-vite'
import { Undo2 } from 'lucide-react'
import { Button } from './button'
import { Toast } from './toast'

const meta = { title: 'Primitives/Toast', component: Toast, parameters: { layout: 'fullscreen' } } satisfies Meta<typeof Toast>
export default meta
type Story = StoryObj<typeof meta>

export const WithAction: Story = {
  args: {
    onDismiss: () => {},
    action: <Button variant="ghost" size="sm" icon={Undo2}>Undo</Button>,
    children: 'Session archived',
  },
}

export const LongText: Story = {
  args: {
    ...WithAction.args,
    children: 'Archived “Somatic calling for SPC-northgate-001-1 against matched normal SPC-northgate-001-2”',
  },
}

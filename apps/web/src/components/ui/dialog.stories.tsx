import type { Meta, StoryObj } from '@storybook/react-vite'
import { Button } from './button'
import { Dialog } from './dialog'

const meta = {
  title: 'Primitives/Dialog',
  component: Dialog,
  decorators: [(Story) => <><p className="text-sm text-muted">Page content behind the dialog.</p><Story /></>],
} satisfies Meta<typeof Dialog>
export default meta
type Story = StoryObj<typeof meta>

const actions = (
  <>
    <Button>Cancel</Button>
    <Button variant="primary">Stop and archive</Button>
  </>
)

export const Warning: Story = {
  args: {
    open: true,
    onOpenChange: () => {},
    title: 'Archive “Library QC follow-up”?',
    actions,
    children: (
      <>
        <p>The agent is still responding. Archiving stops the response, and it can't be resumed.</p>
        <p>2 jobs will keep running and their results stay with the session.</p>
      </>
    ),
  },
}

export const LongTitle: Story = {
  args: {
    ...Warning.args,
    title: 'Archive “Somatic calling for SPC-northgate-001-1 against matched normal SPC-northgate-001-2”?',
    children: <p>1 job will keep running and its results stay with the session.</p>,
  },
}

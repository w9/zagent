import type { Meta, StoryObj } from '@storybook/react-vite'
import { cn } from '../../lib/utils'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from './resizable'

const meta = {
  title: 'Primitives/Resizable',
  component: ResizableHandle,
  decorators: [(Story) => <div className="h-64 w-full max-w-prose overflow-hidden rounded-md border border-subtle"><Story /></div>],
} satisfies Meta<typeof ResizableHandle>
export default meta
type Story = StoryObj<typeof meta>

const paneClassName = 'flex items-center justify-center p-4 text-sm text-muted'

export const Horizontal: Story = {
  render: () => (
    <ResizablePanelGroup>
      <ResizablePanel defaultSize="30%" minSize="20%" className={cn(paneClassName, 'bg-subtle')}>Sessions</ResizablePanel>
      <ResizableHandle aria-label="Resize sessions" />
      <ResizablePanel minSize="30%" className={paneClassName}>Conversation</ResizablePanel>
    </ResizablePanelGroup>
  ),
}

export const Vertical: Story = {
  render: () => (
    <ResizablePanelGroup orientation="vertical">
      <ResizablePanel minSize="20%" className={paneClassName}>Display</ResizablePanel>
      <ResizableHandle aria-label="Resize display" />
      <ResizablePanel minSize="20%" className={cn(paneClassName, 'bg-subtle')}>Model</ResizablePanel>
    </ResizablePanelGroup>
  ),
}

export const Nested: Story = {
  render: () => (
    <ResizablePanelGroup>
      <ResizablePanel defaultSize="25%" minSize="15%" className={cn(paneClassName, 'bg-subtle')}>Sessions</ResizablePanel>
      <ResizableHandle aria-label="Resize sessions" />
      <ResizablePanel minSize="50%">
        <ResizablePanelGroup>
          <ResizablePanel minSize="30%" className={paneClassName}>Conversation</ResizablePanel>
          <ResizableHandle aria-label="Resize conversation" />
          <ResizablePanel minSize="30%" className={cn(paneClassName, 'bg-subtle')}>Maximized artifact</ResizablePanel>
        </ResizablePanelGroup>
      </ResizablePanel>
    </ResizablePanelGroup>
  ),
}

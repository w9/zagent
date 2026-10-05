import type { Meta, StoryObj } from '@storybook/react-vite'
import { ArrowUp, ChevronLeft, Pencil, ScanEye, X } from 'lucide-react'
import { Button } from './button'
import { IconButton } from './icon-button'
import { Tooltip } from './tooltip'

const meta = { title: 'Primitives/Icon button', component: IconButton } satisfies Meta<typeof IconButton>
export default meta
type Story = StoryObj<typeof meta>

export const Variants: Story = {
  args: { label: 'Rename session', icon: Pencil },
  render: () => (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <IconButton label="Previous view" icon={ChevronLeft} />
        <IconButton label="Rename session" icon={Pencil} size="sm" />
        <IconButton label="Close" icon={X} variant="secondary" />
        <IconButton label="Send message" icon={ArrowUp} variant="primary" />
      </div>
      <div className="flex items-center gap-2">
        <IconButton label="X-ray" icon={ScanEye} aria-pressed />
        <IconButton label="Previous view" icon={ChevronLeft} disabled />
        <IconButton label="Send message" icon={ArrowUp} variant="primary" disabled />
      </div>
    </div>
  ),
}

export const WithTooltip: Story = {
  args: { label: 'Rename session', icon: Pencil },
  render: () => (
    <div className="flex justify-center p-12">
      <Tooltip content="Rename “Intake review for the northgate cohort”" open>
        <Button>Hover target</Button>
      </Tooltip>
    </div>
  ),
}

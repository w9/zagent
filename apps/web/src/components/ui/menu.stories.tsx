import type { Meta, StoryObj } from '@storybook/react-vite'
import { Archive, Ellipsis, Pencil } from 'lucide-react'
import { IconButton } from './icon-button'
import { Menu, MenuItem } from './menu'

const meta = { title: 'Primitives/Menu', component: Menu } satisfies Meta<typeof Menu>
export default meta
type Story = StoryObj<typeof meta>

const trigger = <IconButton size="sm" label="Actions for Library QC follow-up" icon={Ellipsis} />

export const Closed: Story = {
  args: { trigger, children: null },
  render: () => (
    <Menu trigger={trigger}>
      <MenuItem icon={Pencil} onSelect={() => {}}>Rename</MenuItem>
      <MenuItem icon={Archive} onSelect={() => {}}>Archive</MenuItem>
    </Menu>
  ),
}

export const Open: Story = {
  args: { trigger, children: null },
  render: () => (
    <div className="flex justify-end p-4 pb-32">
      {/* A modal menu marks the page aria-hidden, which axe flags around the focusable trigger. */}
      <Menu trigger={trigger} open modal={false}>
        <MenuItem icon={Pencil} onSelect={() => {}}>Rename</MenuItem>
        <MenuItem icon={Archive} onSelect={() => {}}>Archive</MenuItem>
        <MenuItem icon={Archive} disabled onSelect={() => {}}>Archive (unavailable)</MenuItem>
      </Menu>
    </div>
  ),
}

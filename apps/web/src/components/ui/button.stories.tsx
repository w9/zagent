import type { Meta, StoryObj } from '@storybook/react-vite'
import { Check, Plus, Save, Trash2 } from 'lucide-react'
import { Button } from './button'

const meta = { title: 'Primitives/Button', component: Button } satisfies Meta<typeof Button>
export default meta
type Story = StoryObj<typeof meta>

const variants = ['primary', 'secondary', 'ghost', 'danger'] as const
const sizes = ['sm', 'md', 'lg'] as const

export const Variants: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      {variants.map((variant) => (
        <div key={variant} className="flex flex-wrap items-center gap-2">
          {sizes.map((size) => (
            <Button key={size} variant={variant} size={size} icon={variant === 'danger' ? Trash2 : Plus}>
              {variant} {size}
            </Button>
          ))}
          <Button variant={variant}>No icon</Button>
        </div>
      ))}
    </div>
  ),
}

export const States: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" icon={Check} disabled>Confirm submission</Button>
        <Button icon={Save} disabled>Save changes</Button>
        <Button variant="primary" loading>Submitting</Button>
        <Button loading>Saving</Button>
      </div>
      <div className="flex w-48 flex-wrap gap-2 border border-dashed border-default p-2">
        <Button variant="primary" icon={Check}>Confirm submission</Button>
        <Button icon={Save}>Save changes</Button>
      </div>
    </div>
  ),
}

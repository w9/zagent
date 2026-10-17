import type { Meta, StoryObj } from '@storybook/react-vite'
import { MessageSquare, Table2 } from 'lucide-react'
import { useState } from 'react'
import { Tabs } from './tabs'

const meta = { title: 'Primitives/Tabs', component: Tabs } satisfies Meta<typeof Tabs>
export default meta
type Story = StoryObj<typeof meta>

export const Panels: Story = {
  args: { label: 'Workspace panels', items: [], value: '', onChange: () => {} },
  render: function Render() {
    const [value, setValue] = useState('chat')
    return (
      <Tabs label="Workspace panels" value={value} onChange={setValue} items={[
        { value: 'chat', label: 'Conversation', icon: MessageSquare },
        { value: 'artifacts', label: 'Artifacts', icon: Table2, count: 3 },
      ]} />
    )
  },
}

export const ManyTabs: Story = {
  args: { label: 'Views', items: [], value: '', onChange: () => {} },
  render: function Render() {
    const [value, setValue] = useState('view-1')
    const items = Array.from({ length: 8 }, (_, index) => ({ value: `view-${index + 1}`, label: `Specimen view ${index + 1}` }))
    return <div className="w-full max-w-96"><Tabs label="Views" value={value} onChange={setValue} items={items} /></div>
  },
}

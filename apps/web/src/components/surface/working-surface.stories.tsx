import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'
import { chartView, failingHandle, handleTableView, pendingHandle, resolveHandle, tableView } from '../fixtures'
import { WorkingSurface } from './working-surface'

const meta = {
  title: 'Surface/Working surface',
  component: WorkingSurface,
  parameters: { layout: 'fullscreen' },
  args: { sessionId: 'session-1', views: [tableView, chartView], onSelect: () => {}, resolveHandle },
  render: function Render(args) {
    const [selected, setSelected] = useState(args.selectedId)
    return <WorkingSurface {...args} selectedId={selected} onSelect={setSelected} />
  },
  decorators: [(Story) => <div className="flex h-dvh flex-col"><Story /></div>],
} satisfies Meta<typeof WorkingSurface>
export default meta
type Story = StoryObj<typeof meta>

export const Chart: Story = {}
export const Table: Story = { args: { selectedId: 'view-0001' } }
export const TableLoading: Story = { args: { views: [handleTableView], resolveHandle: pendingHandle } }
export const TableError: Story = { args: { views: [handleTableView], resolveHandle: failingHandle } }
export const ChartError: Story = { args: { views: [chartView], resolveHandle: failingHandle } }
export const Empty: Story = { args: { views: [] } }
export const Unavailable: Story = { args: { selectedId: 'view-0099' } }
export const EmptyTable: Story = {
  args: { views: [{ ...tableView, spec: { ...tableView.spec, props: { ...tableView.spec.props, rows: [], row_count: 0 } } }] },
}

import type { Meta, StoryObj } from '@storybook/react-vite'
import { Checkbox, Field, Input, Select, Textarea } from './field'

const meta = { title: 'Primitives/Field', component: Field } satisfies Meta<typeof Field>
export default meta
type Story = StoryObj<typeof meta>

export const Controls: Story = {
  args: { label: 'Label', children: null },
  render: () => (
    <div className="@container max-w-prose">
      <div className="grid grid-cols-1 gap-4 @medium:grid-cols-2">
        <Field label="Specimen query"><Input placeholder="query-0001" /></Field>
        <Field label="Minimum VAF" hint="Between 0.01 and 0.5"><Input type="number" defaultValue={0.05} step="any" /></Field>
        <Field label="Application">
          <Select defaultValue="somatic-snv">
            <option value="somatic-snv">Somatic variant calling</option>
            <option value="qc">Read quality control</option>
          </Select>
        </Field>
        <Field label="Minimum coverage" error="Must be at least 10."><Input type="number" defaultValue={4} /></Field>
        <Field label="Disabled"><Input defaultValue="query-0002" disabled /></Field>
        <Checkbox label="Include matched normal" defaultChecked />
        <Field label="Notes" className="@medium:col-span-2"><Textarea placeholder="Optional context for the reviewer" /></Field>
      </div>
    </div>
  ),
}

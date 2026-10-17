import type { Meta, StoryObj } from '@storybook/react-vite'
import { catalog, draft } from '../../fixtures'
import { DraftEditor } from './draft_form.artifact'

const meta = {
  title: 'Artifact/Draft editor',
  component: DraftEditor,
  args: { draft, catalog, sessionId: 'session-1' },
  decorators: [(Story) => <div className="@container max-w-prose"><Story /></div>],
} satisfies Meta<typeof DraftEditor>
export default meta
type Story = StoryObj<typeof meta>

export const Editing: Story = {}
export const NeedsReview: Story = {
  args: {
    draft: {
      ...draft,
      validation: [
        { code: 'missing_matched_normal', field: 'specimen_handle', message: 'A matched normal specimen is missing.' },
        { code: 'low_depth', field: 'parameters.min_depth', message: 'Minimum depth below 30 is not validated for pediatric tumours.' },
      ],
    },
  },
}
export const Submitted: Story = { args: { draft: { ...draft, status: 'submitted', job_id: 'job-0001' } } }
export const ReadOnly: Story = { args: { readOnly: true } }

import type { Meta, StoryObj } from '@storybook/react-vite'
import type { PublishedArtifact } from '../../lib/artifacts'
import { chartArtifact, draftArtifact, handleTableArtifact, jobArtifact, tableArtifact } from '../fixtures'
import { PanelHeader } from '../ui/panel-header'
import { ArtifactList } from './artifact-list'

const meta = {
  title: 'Artifact/Artifact list',
  component: ArtifactList,
  parameters: { layout: 'fullscreen' },
  args: { artifacts: [tableArtifact, chartArtifact, draftArtifact, jobArtifact], onSelect: () => {} },
  // As in the conversation panel: the list sits in the header's actions of a relative @container.
  render: (args) => (
    <section aria-label="Conversation" className="@container relative flex h-dvh flex-col bg-surface">
      <PanelHeader title="Conversation" subtitle="Intake review for the northgate cohort" actions={<ArtifactList {...args} />} />
    </section>
  ),
} satisfies Meta<typeof ArtifactList>
export default meta
type Story = StoryObj<typeof meta>

const many: PublishedArtifact[] = Array.from({ length: 12 }, (_, index) => ({
  ...[tableArtifact, chartArtifact, handleTableArtifact][index % 3],
  id: `view-${String(index + 1).padStart(4, '0')}`,
  seq: index + 1,
}))
const longTitles: PublishedArtifact[] = [
  {
    ...tableArtifact,
    spec: {
      ...tableArtifact.spec,
      props: { ...tableArtifact.spec.props, title: 'Specimens received in the last 24 hours for patient NGC-0041872 across every northgate collection site' },
    },
  },
  { ...chartArtifact, id: 'view-0002' },
]

export const Floating: Story = {}
export const Many: Story = { args: { artifacts: many } }
export const LongTitles: Story = { args: { artifacts: longTitles } }
export const One: Story = { args: { artifacts: [tableArtifact] } }
export const Collapsed: Story = { args: { defaultCollapsed: true } }
export const Narrow: Story = {
  render: (args) => (
    <section aria-label="Conversation" className="@container relative flex h-dvh w-full max-w-96 flex-col bg-surface">
      <PanelHeader title="Conversation" subtitle="Intake review for the northgate cohort" actions={<ArtifactList {...args} />} />
    </section>
  ),
}

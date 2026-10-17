import type { Meta, StoryObj } from '@storybook/react-vite'
import type { ComponentProps } from 'react'
import jobsHtml from '../../../../../services/agent/zagent/resources/jobs.html?raw'
import type { PublishedArtifact } from '../../lib/artifacts'
import type { HandleResolver } from './kinds/table.artifact'
import {
  catalog,
  chartArtifact,
  draft,
  draftArtifact,
  failingHandle,
  handleTableArtifact,
  jobArtifact,
  jobs,
  pendingHandle,
  resolveHandle,
  tableArtifact,
} from '../fixtures'
import { ArtifactPanel } from './artifact-panel'
import { ArtifactRenderer } from './artifact-renderer'
import { DraftEditor } from './kinds/draft_form.artifact'
import { McpAppFrame } from './mcp-app'

type Args = ComponentProps<typeof ArtifactPanel> & { resolver?: HandleResolver; content?: 'renderer' | 'draft' | 'job' }

function Panel({ artifact, resolver = resolveHandle, content = 'renderer', ...props }: Args) {
  return (
    <ArtifactPanel artifact={artifact} {...props}>
      {artifact && content === 'renderer' && (
        <ArtifactRenderer spec={artifact.spec} display="maximized" artifactId={artifact.id} sessionId="session-1" resolveHandle={resolver} />
      )}
      {content === 'draft' && <DraftEditor draft={draft} catalog={catalog} sessionId="session-1" />}
      {content === 'job' && (
        <McpAppFrame title="Read quality control" html={jobsHtml} data={jobs} readData={async () => jobs} displayMode="fullscreen" />
      )}
    </ArtifactPanel>
  )
}

const meta = {
  title: 'Artifact/Artifact panel',
  component: Panel,
  parameters: { layout: 'fullscreen' },
  args: { artifact: tableArtifact, onMinimize: () => {} },
  decorators: [(Story) => <div className="flex h-dvh flex-col"><Story /></div>],
} satisfies Meta<typeof Panel>
export default meta
type Story = StoryObj<typeof meta>

const longTitle: PublishedArtifact = {
  ...tableArtifact,
  spec: {
    ...tableArtifact.spec,
    props: { ...tableArtifact.spec.props, title: 'Specimens received in the last 24 hours for patient NGC-0041872 across every northgate collection site' },
  },
}

export const Table: Story = {}
export const Chart: Story = { args: { artifact: chartArtifact } }
export const TableLoading: Story = { args: { artifact: handleTableArtifact, resolver: pendingHandle } }
export const TableError: Story = { args: { artifact: handleTableArtifact, resolver: failingHandle } }
export const ChartError: Story = { args: { artifact: chartArtifact, resolver: failingHandle } }
export const EmptyTable: Story = {
  args: { artifact: { ...tableArtifact, spec: { ...tableArtifact.spec, props: { ...tableArtifact.spec.props, rows: [], row_count: 0 } } } },
}
export const Draft: Story = { args: { artifact: draftArtifact, content: 'draft' } }
export const Job: Story = { args: { artifact: jobArtifact, content: 'job' } }
export const LongTitle: Story = { args: { artifact: longTitle } }
export const Opening: Story = { args: { artifact: undefined, loading: true } }
export const Unavailable: Story = { args: { artifact: undefined } }

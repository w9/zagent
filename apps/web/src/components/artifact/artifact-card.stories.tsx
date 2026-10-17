import type { Meta, StoryObj } from '@storybook/react-vite'
import type { ComponentProps } from 'react'
import jobsHtml from '../../../../../services/agent/zagent/resources/jobs.html?raw'
import type { PublishedArtifact } from '../../lib/artifacts'
import type { DraftState } from '../../lib/events'
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
import { ArtifactCard } from './artifact-card'
import { ArtifactRenderer } from './artifact-renderer'
import type { HandleResolver } from './kinds/table.artifact'
import { DraftPreview } from './kinds/draft_form.artifact'
import { McpAppFrame } from './mcp-app'

type Args = Omit<ComponentProps<typeof ArtifactCard>, 'children'> & {
  resolver?: HandleResolver
  draftState?: DraftState
  readOnly?: boolean
}

function Card({ artifact, resolver = resolveHandle, draftState = draft, readOnly, ...props }: Args) {
  const kind = artifact.spec.kind
  return (
    <ArtifactCard artifact={artifact} {...props}>
      {kind === 'draft_form' ? (
        <DraftPreview draft={draftState} catalog={catalog} onMaximize={() => {}} readOnly={readOnly} />
      ) : kind === 'job_card' ? (
        <McpAppFrame title="Read quality control" html={jobsHtml} data={jobs} readData={async () => jobs} displayMode="inline" onRequestDisplayMode={() => {}} />
      ) : (
        <ArtifactRenderer spec={artifact.spec} display="inline" artifactId={artifact.id} sessionId="session-1" resolveHandle={resolver} onMaximize={() => {}} />
      )}
    </ArtifactCard>
  )
}

const meta = {
  title: 'Artifact/Artifact card',
  component: Card,
  args: { artifact: tableArtifact, onMaximize: () => {}, onMinimize: () => {} },
  decorators: [(Story) => <div className="@container max-w-prose"><Story /></div>],
} satisfies Meta<typeof Card>
export default meta
type Story = StoryObj<typeof meta>

const longTitle: PublishedArtifact = {
  ...tableArtifact,
  spec: {
    ...tableArtifact.spec,
    props: { ...tableArtifact.spec.props, title: 'Specimens received in the last 24 hours for patient NGC-0041872 across every northgate collection site' },
  },
}
const invalid: PublishedArtifact = { id: 'view-0099', seq: 1, spec: { kind: 'table', version: 9, props: { title: 'Specimens' } } }

export const Table: Story = {}
export const TableLoading: Story = { args: { artifact: handleTableArtifact, resolver: pendingHandle } }
export const TableError: Story = { args: { artifact: handleTableArtifact, resolver: failingHandle } }
export const Chart: Story = { args: { artifact: chartArtifact } }
export const Draft: Story = { args: { artifact: draftArtifact } }
export const DraftNeedsReview: Story = {
  args: {
    artifact: draftArtifact,
    draftState: {
      ...draft,
      parameters: { ...draft.parameters, min_tumor_purity: 0.2, call_indels: true, annotate: 'clinvar', panel: 'pediatric-solid' },
      validation: [{ code: 'missing_matched_normal', field: 'specimen_handle', message: 'A matched normal specimen is missing.' }],
    },
  },
}
export const DraftSubmitted: Story = { args: { artifact: draftArtifact, draftState: { ...draft, status: 'submitted', job_id: 'job-0001' } } }
export const DraftReadOnly: Story = { args: { artifact: draftArtifact, readOnly: true } }
export const Job: Story = { args: { artifact: jobArtifact } }
export const Maximized: Story = { args: { maximized: true } }
export const Unavailable: Story = { args: { artifact: invalid } }
export const LongTitleNarrow: Story = {
  args: { artifact: longTitle },
  decorators: [(Story) => <div className="w-64"><Story /></div>],
}
export const MaximizedNarrow: Story = {
  args: { artifact: longTitle, maximized: true },
  decorators: [(Story) => <div className="w-64"><Story /></div>],
}

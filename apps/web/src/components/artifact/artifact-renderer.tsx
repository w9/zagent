import { createElement } from 'react'
import type { ComponentType } from 'react'
import { validateArtifactSpec } from '../../lib/artifacts'
import type { ArtifactSpec } from '../../lib/artifacts'
import type { DraftState, JobState } from '../../lib/events'
import type { ConfirmedJob } from './kinds/draft_form.artifact'
import type { HandleResolver } from './kinds/table.artifact'
import { McpAppArtifact } from './mcp-app'

/** Inline is the card in the conversation; maximized is the right panel. */
export type ArtifactDisplay = 'inline' | 'maximized'

export type ArtifactRendererProps = {
  spec: ArtifactSpec
  display: ArtifactDisplay
  artifactId?: string
  resolveHandle?: HandleResolver
  sessionId?: string
  drafts?: Record<string, DraftState>
  jobs?: Record<string, JobState>
  onConfirmed?: (job: ConfirmedJob) => void
  onMaximize?: () => void
  onMinimize?: () => void
  readOnly?: boolean
}
type ArtifactComponent = ComponentType<ArtifactRendererProps> & { kind: string; version: number }
const modules = import.meta.glob<{ default: ArtifactComponent }>('./kinds/*.artifact.tsx', { eager: true })
const registry = new Map(
  Object.values(modules).map(({ default: Component }) => [`${Component.kind}:${Component.version}`, Component]),
)

export function ArtifactRenderer(props: ArtifactRendererProps) {
  const { spec } = props
  validateArtifactSpec(spec)
  if (spec.props.resource_uri || (spec.kind === 'job_card' && spec.version === 1)) return <McpAppArtifact {...props} />
  const Component = registry.get(`${spec.kind}:${spec.version}`)
  if (!Component) throw new Error(`No renderer for ${spec.kind} v${spec.version}`)
  return createElement(Component, props)
}

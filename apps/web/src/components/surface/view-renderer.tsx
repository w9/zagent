import { createElement } from 'react'
import type { ComponentType } from 'react'
import { validateViewSpec } from '../../lib/views'
import type { ViewSpec } from '../../lib/views'
import type { DraftState, JobState } from '../../lib/events'
import type { HandleResolver } from './views/table.view'
import { McpAppView } from './mcp-app-view'

export type ViewRendererProps = {
  spec: ViewSpec
  viewId?: string
  resolveHandle?: HandleResolver
  sessionId?: string
  drafts?: Record<string, DraftState>
  jobs?: Record<string, JobState>
  onConfirmed?: () => void
}
type ViewComponent = ComponentType<ViewRendererProps> & { kind: string; version: number }
const modules = import.meta.glob<{ default: ViewComponent }>('./views/*.view.tsx', { eager: true })
const registry = new Map(
  Object.values(modules).map(({ default: Component }) => [`${Component.kind}:${Component.version}`, Component]),
)

export function ViewRenderer(props: ViewRendererProps) {
  const { spec } = props
  validateViewSpec(spec)
  if (spec.props.resource_uri || (spec.kind === 'job_card' && spec.version === 1)) return <McpAppView {...props} />
  const Component = registry.get(`${spec.kind}:${spec.version}`)
  if (!Component) throw new Error(`No renderer for ${spec.kind} v${spec.version}`)
  return createElement(Component, props)
}

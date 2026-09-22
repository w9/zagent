import { createElement } from 'react'
import type { ComponentType } from 'react'
import { validateViewSpec } from '../lib/views'
import type { ViewSpec } from '../lib/views'
import type { HandleResolver } from './views/table.view'

export type ViewRendererProps = {
  spec: ViewSpec
  resolveHandle?: HandleResolver
}
type ViewComponent = ComponentType<ViewRendererProps> & {
  kind: string
  version: number
}
const modules = import.meta.glob<{ default: ViewComponent }>(
  './views/*.view.tsx',
  { eager: true },
)
const registry = new Map(
  Object.values(modules).map(({ default: Component }) => [
    `${Component.kind}:${Component.version}`,
    Component,
  ]),
)

export function ViewRenderer(props: ViewRendererProps) {
  const { spec } = props
  validateViewSpec(spec)
  const Component = registry.get(`${spec.kind}:${spec.version}`)
  if (!Component)
    throw new Error(`No renderer for ${spec.kind} v${spec.version}`)
  return createElement(Component, props)
}

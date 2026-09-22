import Ajv2020 from 'ajv/dist/2020'
import type { AnySchemaObject } from 'ajv'

export type ViewSpec = {
  kind: string
  version: number
  props: Record<string, unknown>
}
export type TableCell = string | number | boolean | null
export type TableColumn = {
  key: string
  label: string
  type: 'string' | 'number' | 'boolean'
}
export type TableData = {
  rows: TableCell[][]
  row_count: number
  columns?: TableColumn[]
}
export type TableProps = {
  title: string
  columns: TableColumn[]
  row_count: number
} & ({ rows: TableCell[][]; handle?: never } | { handle: string; rows?: never })
export type TableSpec = ViewSpec & {
  kind: 'table'
  version: 1
  props: TableProps
}
export type ChartProps = {
  title: string
  handle: string
  mark: 'bar' | 'line' | 'point'
  encoding: Record<string, {
    field: string
    type: 'nominal' | 'ordinal' | 'quantitative' | 'temporal'
    aggregate?: 'count' | 'sum' | 'mean' | 'min' | 'max'
  }>
}
export type ChartSpec = ViewSpec & {
  kind: 'chart'
  version: 1
  props: ChartProps
}
export type PushedView = { id: string; seq: number; spec: ViewSpec }

type ViewSchema = AnySchemaObject & {
  properties: { kind: { const: string }; version: { const: number } }
}

const schemas = import.meta.glob<ViewSchema>(
  '../../../../services/agent/zagent/view_schemas/*.json',
  { eager: true, import: 'default' },
)
const ajv = new Ajv2020({ allErrors: true, strict: false })
const validators = new Map(
  Object.values(schemas).map((schema) => [
    `${schema.properties.kind.const}:${schema.properties.version.const}`,
    ajv.compile(schema),
  ]),
)

export function validateViewSpec(value: unknown): ViewSpec {
  if (!value || typeof value !== 'object')
    throw new Error('View schema error: spec must be an object')
  const spec = value as ViewSpec
  const validate = validators.get(`${spec.kind}:${spec.version}`)
  if (!validate)
    throw new Error(`Unsupported view: ${spec.kind} v${spec.version}`)
  if (!validate(spec))
    throw new Error(`View schema error: ${ajv.errorsText(validate.errors)}`)
  if (spec.kind === 'table') {
    const props = (spec as TableSpec).props
    if (
      new Set(props.columns.map((column) => column.key)).size !==
      props.columns.length
    )
      throw new Error('View schema error: table column keys must be unique')
    if (props.rows) {
      if (props.row_count < props.rows.length)
        throw new Error(
          'View schema error: row_count is smaller than the supplied rows',
        )
      for (const row of props.rows) {
        if (row.length !== props.columns.length)
          throw new Error(
            'View schema error: each row must match the number of columns',
          )
        row.forEach((cell, index) => {
          if (cell !== null && typeof cell !== props.columns[index].type)
            throw new Error(
              `View schema error: cell does not match column ${props.columns[index].key}`,
            )
        })
      }
    }
  }
  return spec
}

export function viewPosition(views: PushedView[], selectedId?: string): number {
  const selected = views.findIndex((view) => view.id === selectedId)
  return selected >= 0 ? selected : views.length - 1
}

export function selectionAt(
  views: PushedView[],
  index: number,
): string | undefined {
  return index >= 0 && index < views.length - 1 ? views[index].id : undefined
}

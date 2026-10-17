import Ajv2020 from 'ajv/dist/2020'
import type { AnySchemaObject } from 'ajv'

export type ArtifactSpec = {
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
export type TableSpec = ArtifactSpec & {
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
export type ChartSpec = ArtifactSpec & {
  kind: 'chart'
  version: 1
  props: ChartProps
}
/** A published artifact. Its ID keeps the `view-0001` form the model knows it by. */
export type PublishedArtifact = { id: string; seq: number; spec: ArtifactSpec }

type ArtifactSchema = AnySchemaObject & {
  properties: { kind: { const: string }; version: { const: number } }
}

const schemas = import.meta.glob<ArtifactSchema>(
  '../../../../services/agent/zagent/artifact_schemas/*.json',
  { eager: true, import: 'default' },
)
const ajv = new Ajv2020({ allErrors: true, strict: false })
const validators = new Map(
  Object.values(schemas).map((schema) => [
    `${schema.properties.kind.const}:${schema.properties.version.const}`,
    ajv.compile(schema),
  ]),
)

export function validateArtifactSpec(value: unknown): ArtifactSpec {
  if (!value || typeof value !== 'object')
    throw new Error('Artifact schema error: spec must be an object')
  const spec = value as ArtifactSpec
  const validate = validators.get(`${spec.kind}:${spec.version}`)
  if (!validate)
    throw new Error(`Unsupported artifact: ${spec.kind} v${spec.version}`)
  if (!validate(spec))
    throw new Error(`Artifact schema error: ${ajv.errorsText(validate.errors)}`)
  if (spec.kind === 'table') {
    const props = (spec as TableSpec).props
    if (
      new Set(props.columns.map((column) => column.key)).size !==
      props.columns.length
    )
      throw new Error('Artifact schema error: table column keys must be unique')
    if (props.rows) {
      if (props.row_count < props.rows.length)
        throw new Error(
          'Artifact schema error: row_count is smaller than the supplied rows',
        )
      for (const row of props.rows) {
        if (row.length !== props.columns.length)
          throw new Error(
            'Artifact schema error: each row must match the number of columns',
          )
        row.forEach((cell, index) => {
          if (cell !== null && typeof cell !== props.columns[index].type)
            throw new Error(
              `Artifact schema error: cell does not match column ${props.columns[index].key}`,
            )
        })
      }
    }
  }
  return spec
}

export function artifactTitle(artifact: PublishedArtifact): string {
  return typeof artifact.spec.props.title === 'string' ? artifact.spec.props.title : artifact.spec.kind
}

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ViewRenderer } from './view-renderer'
import { StepMarker } from './step-marker'
import { RefusalChip } from './refusal-chip'
import { XrayContent } from './xray-panel'
import type { XrayData } from '../lib/api'
import { validateViewSpec } from '../lib/views'
import type { ChartSpec, TableData, TableSpec } from '../lib/views'
import type { HandleResolver } from './views/table.view'

afterEach(cleanup)

it('links real identifiers to model tokens without exposing raw values in the model pane', async () => {
  const empty = { session_id: 'session', seq: 1, messages: [], views: [], steps: [], conversation_turn: null }
  const data: XrayData = {
    display: { ...empty, messages: [{ id: 'user', seq: 1, role: 'user', text: 'Find NGC-0041872', status: 'complete' }] },
    model: empty,
    bindings: [{ token: '[PT_1]', value: 'NGC-0041872', kind: 'PT' }],
    executions: [{ conversation_turn_id: 'turn', tool: 'find_patients', arguments: { mrn: 'NGC-0041872' } }],
    requests: [{ request_id: 'request', conversation_turn_id: 'turn',
      request: { model: 'test-model', messages: [{ role: 'user', content: 'Find [PT_1]' }] },
      audit: { purpose: 'agent', mode: 'replay', request_hash: 'digest', outcome: 'completed' } }],
  }
  const { container } = render(<XrayContent data={data} />)
  const source = screen.getAllByRole('button', { name: 'Highlight [PT_1]' })[0]
  await userEvent.click(source)
  const linked = container.querySelectorAll('[data-token="[PT_1]"][aria-pressed="true"]')
  expect(linked.length).toBe(3)
  expect(screen.getByRole('region', { name: 'Model-visible requests' }).textContent).not.toContain('NGC-0041872')
  expect(screen.getByText('find_patients')).toBeTruthy()
})

it('renders refusal reasons and helpful messages as text, not assistant prose or markup', () => {
  const { container } = render(<RefusalChip refusal={{
    id: 'turn', seq: 3, code: 'requires_human_authority',
    message: 'An authorized person must approve this. <script>not markup</script>',
  }} />)
  expect(screen.getByRole('status').textContent).toBe('Human authorization required')
  expect(screen.getByTestId('refusal').getAttribute('data-reason')).toBe('requires_human_authority')
  expect(screen.getByText(/An authorized person/)).toBeTruthy()
  expect(container.querySelector('script')).toBeNull()
})

const embed = vi.hoisted(() => vi.fn(async () => ({
  finalize: vi.fn(),
  view: { resize: vi.fn(() => ({ runAsync: vi.fn(async () => undefined) })) },
})))
vi.mock('vega-embed', () => ({ default: embed }))

const spec: TableSpec = {
  kind: 'table',
  version: 1,
  props: {
    title: 'Intake review',
    row_count: 2,
    columns: [
      { key: 'specimen_id', label: 'Specimen', type: 'string' },
      { key: 'coverage', label: 'Coverage', type: 'number' },
      { key: 'ready', label: 'Ready', type: 'boolean' },
    ],
    rows: [
      ['SPC-0001', 120, true],
      ['SPC-0002', null, false],
    ],
  },
}
const handleSpec: TableSpec = {
  ...spec,
  props: {
    title: spec.props.title,
    columns: spec.props.columns,
    row_count: 2,
    handle: 'query-1',
  },
}

describe('registered table snapshots', () => {
  it.each([
    ['complete', spec],
    ['empty', { ...spec, props: { ...spec.props, rows: [], row_count: 0 } }],
    ['truncated', { ...spec, props: { ...spec.props, row_count: 14 } }],
  ] as const)('renders the %s state', (_, fixture) => {
    expect(
      renderToStaticMarkup(<ViewRenderer spec={fixture} />),
    ).toMatchSnapshot()
  })

  it('treats table labels and cell content as text, never markup', () => {
    const dangerous: TableSpec = {
      ...spec,
      props: {
        title: '<script>alert(1)</script>',
        columns: spec.props.columns,
        row_count: 1,
        rows: [['<img src=x onerror=alert(1)>', 1, true]],
      },
    }
    const { container } = render(<ViewRenderer spec={dangerous} />)
    expect(container.querySelector('script, img')).toBeNull()
    expect(screen.getByRole('heading').textContent).toBe(
      '<script>alert(1)</script>',
    )
  })

  it('does not pretend a handle is loaded without a resolver', () => {
    render(<ViewRenderer spec={handleSpec} />)
    expect(screen.getByRole('alert').textContent).toBe(
      'Data source unavailable.',
    )
  })
})

describe('additive table handle source', () => {
  it('maps a selected column order using query metadata', async () => {
    const resolver = vi.fn<HandleResolver>().mockResolvedValue({
      columns: [spec.props.columns[1], spec.props.columns[0], spec.props.columns[2]],
      rows: [[95, 'SPC-REORDERED', true]], row_count: 1,
    })
    render(<ViewRenderer spec={handleSpec} resolveHandle={resolver} />)
    await screen.findByText('SPC-REORDERED')
    expect(screen.getAllByRole('cell').map((cell) => cell.textContent)).toEqual([
      'SPC-REORDERED', '95', 'Yes',
    ])
  })

  it('loads using an injected resolver and retries a failure', async () => {
    const resolver = vi
      .fn<HandleResolver>()
      .mockRejectedValueOnce(new Error('Query unavailable'))
      .mockResolvedValueOnce({ rows: [['SPC-0003', 90, true]], row_count: 3 })
    render(<ViewRenderer spec={handleSpec} resolveHandle={resolver} />)
    expect(screen.getByRole('status').textContent).toBe('Loading data...')
    await screen.findByText('Query unavailable')
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await screen.findByText('SPC-0003')
    expect(screen.getByText('1 of 3 rows shown')).toBeTruthy()
    expect(resolver).toHaveBeenCalledTimes(2)
  })

  it('validates fetched rows against the same schema', async () => {
    const resolver = vi
      .fn<HandleResolver>()
      .mockResolvedValue({ rows: [[5]], row_count: 1 })
    render(<ViewRenderer spec={handleSpec} resolveHandle={resolver} />)
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toContain(
        'View schema error',
      ),
    )
  })

  it('aborts a pending source when the selected view changes', async () => {
    let complete!: (data: TableData) => void
    const resolver = vi.fn<HandleResolver>(
      () =>
        new Promise((resolve) => {
          complete = resolve
        }),
    )
    const { rerender } = render(
      <ViewRenderer spec={handleSpec} resolveHandle={resolver} />,
    )
    const signal = resolver.mock.calls[0][1]
    rerender(<ViewRenderer spec={spec} resolveHandle={resolver} />)
    expect(signal.aborted).toBe(true)
    complete({ rows: [['STALE', 1, false]], row_count: 1 })
    await waitFor(() => expect(screen.queryByText('STALE')).toBeNull())
    expect(screen.getByText('SPC-0001')).toBeTruthy()
  })
})

it('starts steps collapsed and retains the open state on completion', async () => {
  const step = {
    id: 'intake',
    seq: 2,
    title: 'Review intake',
    detail: 'Synthetic fixture.',
    status: 'running' as const,
  }
  const { container, rerender } = render(<StepMarker step={step} />)
  const details = container.querySelector('details')!
  expect(details.open).toBe(false)
  await userEvent.click(container.querySelector('summary')!)
  expect(details.open).toBe(true)
  rerender(
    <StepMarker
      step={{ ...step, status: 'complete', detail: '14 specimens reviewed.' }}
    />,
  )
  expect(details.open).toBe(true)
  expect(screen.getByText('14 specimens reviewed.')).toBeTruthy()
})

it('shows tool names, arguments, and correction errors inside a collapsed step', async () => {
  const { container } = render(<StepMarker step={{
    id: 'step-1', seq: 2, title: 'Agent step 1', detail: '', status: 'complete',
    tools: [{
      call_id: 'call-1', name: 'find_specimens', arguments: '{"received_within":"bad"}',
      result: { error: { code: 'invalid_arguments', message: 'Use a relative window' } },
    }],
  }} />)
  expect(container.querySelector('details')!.open).toBe(false)
  await userEvent.click(container.querySelector('summary')!)
  expect(screen.getByText('find_specimens')).toBeTruthy()
  expect(screen.getByText(/"received_within": "bad"/)).toBeTruthy()
  expect(screen.getByText(/Use a relative window/)).toBeTruthy()
})

const chartSpec: ChartSpec = {
  kind: 'chart', version: 1,
  props: {
    title: 'Library coverage', handle: 'query-0001', mark: 'bar',
    encoding: {
      x: { field: 'specimen_id', type: 'nominal' },
      y: { field: 'coverage', type: 'quantitative' },
    },
  },
}

it('renders charts from resolved rows and disables external loading', async () => {
  const resolver = vi.fn<HandleResolver>().mockResolvedValue({
    columns: spec.props.columns, rows: spec.props.rows!, row_count: 2,
  })
  render(<ViewRenderer spec={chartSpec} resolveHandle={resolver} />)
  await screen.findByText('2 rows')
  const call = embed.mock.calls.at(-1) as unknown as [Element, {
    data: { values: Record<string, unknown>[] }
  }, { loader: { load: () => Promise<never> } }]
  expect(call[1].data.values[0]).toEqual({ specimen_id: 'SPC-0001', coverage: 120, ready: true })
  await expect(call[2].loader.load()).rejects.toThrow('External chart data')
})

it('shows chart handle expiry instead of rendering an empty result', async () => {
  const resolver = vi.fn<HandleResolver>().mockRejectedValue(new Error('Handle expired'))
  render(<ViewRenderer spec={chartSpec} resolveHandle={resolver} />)
  await screen.findByText('Handle expired')
  expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy()
})

it('rejects chart URLs, expressions, and arbitrary Vega transforms', () => {
  for (const extra of [{ data: { url: 'https://example.com' } }, { transform: [] }, { href: 'x' }]) {
    expect(() => validateViewSpec({
      ...chartSpec, props: { ...chartSpec.props, ...extra },
    })).toThrow('View schema error')
  }
})

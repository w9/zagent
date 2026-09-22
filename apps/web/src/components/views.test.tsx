import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ViewRenderer } from './view-renderer'
import { StepMarker } from './step-marker'
import type { TableData, TableSpec } from '../lib/views'
import type { HandleResolver } from './views/table.view'

afterEach(cleanup)

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

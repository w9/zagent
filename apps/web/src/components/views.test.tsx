import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ViewRenderer } from './view-renderer'
import { StepMarker } from './step-marker'
import { RefusalChip } from './refusal-chip'
import { XrayContent } from './xray-panel'
import { TranscriptText } from './transcript-text'
import type { XrayData } from '../lib/api'
import { DraftEditor } from './views/draft_form.view'
import type { CatalogApp } from './views/draft_form.view'
import type { DraftState } from '../lib/events'
import catalog from '../../../../services/agent/zagent/catalog.json'
import { validateViewSpec } from '../lib/views'
import type { ChartSpec, TableData, TableSpec } from '../lib/views'
import type { HandleResolver } from './views/table.view'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('assistant Markdown', () => {
  it('renders Markdown and GFM without interpreting user messages', () => {
    const text = '# Summary\n\nA **strong** and *careful* answer with `inline code`.\n\n- First\n- Second\n\n1. Ordered\n\n> Evidence only\n\n```ts\nconst answer = 42\n```\n\n| Metric | Value |\n| --- | --- |\n| Coverage | 8x |'
    const { container, rerender } = render(<TranscriptText role="assistant" text={text} />)
    expect(screen.getByRole('heading', { name: 'Summary' })).toBeTruthy()
    expect(container.querySelector('strong')?.textContent).toBe('strong')
    expect(container.querySelector('em')?.textContent).toBe('careful')
    expect(container.querySelectorAll('li').length).toBe(3)
    expect(container.querySelector('blockquote')?.textContent).toContain('Evidence only')
    expect(container.querySelector('pre code')?.textContent).toBe('const answer = 42\n')
    expect(screen.getByRole('table').textContent).toContain('Coverage')
    rerender(<TranscriptText role="user" text={text} />)
    expect(container.querySelector('h1,strong,em,table,pre,a')).toBeNull()
    expect(container.textContent).toBe(text)
  })

  it('keeps every streaming prefix legible and renders the same completed text on remount', () => {
    const text = '## Result\n\n**Evidence** and [guide](https://docs.example.org).\n\n```text\npartial <tag>\n```\n\n| A | B |\n| - | - |\n| 1 | 2 |'
    const { container, rerender, unmount } = render(<TranscriptText role="assistant" text="" streaming />)
    for (let length = 1; length <= text.length; length += 1) {
      rerender(<TranscriptText role="assistant" text={text.slice(0, length)} streaming />)
      expect(container.querySelector('.stream-cursor')).toBeTruthy()
      expect(container.querySelector('script,img')).toBeNull()
      if (/[a-z0-9]/i.test(text.slice(0, length))) expect(container.textContent?.length).toBeGreaterThan(0)
    }
    rerender(<TranscriptText role="assistant" text={text} />)
    const completed = container.innerHTML
    unmount()
    const refreshed = render(<TranscriptText role="assistant" text={text} />)
    expect(refreshed.container.innerHTML).toBe(completed)
    const replay = new DOMParser().parseFromString(
      renderToStaticMarkup(<TranscriptText role="assistant" text={text} />), 'text/html',
    )
    expect(replay.body.innerHTML).toBe(completed)
  })

  it('escapes HTML, removes image requests, and blocks unsafe or host-owned navigation', () => {
    const text = '<script>alert(1)</script>\n\n<img src="https://tracker.example/pixel">\n\n![Visible alt](https://tracker.example/image)\n\n[safe](https://docs.example.org/guide) [http](http://docs.example.org) [script](javascript:alert%281%29) [data](data:text/html,hello) [file](file:///etc/passwd) [relative](/api/sessions/test/confirm) [view](?view=view-0001&panel=surface) [internal](http://localhost:8000/sessions/test) [protocol relative](//docs.example.org)'
    const { container } = render(<TranscriptText role="assistant" text={text} />)
    expect(container.querySelector('script,img,iframe,form')).toBeNull()
    expect(container.textContent).toContain('<script>alert(1)</script>')
    expect(container.textContent).toContain('Visible alt')
    const links = screen.getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual(['safe', 'http'])
    for (const link of links) {
      expect(link.getAttribute('target')).toBe('_blank')
      expect(link.getAttribute('rel')).toBe('noopener noreferrer nofollow')
      expect(link.getAttribute('referrerpolicy')).toBe('no-referrer')
    }
  })

  it('resolves privacy only in text nodes, including code and tables, never destinations', () => {
    const bindings = [{ token: '[PT_1]', value: 'NGC-0041872', kind: 'PT' }]
    const text = '**[PT_1]** ` [PT_1] `\n\n| Patient |\n| --- |\n| [PT_1] |\n\n[private](https://docs.example.org/[PT_1]) [encoded](https://docs.example.org/%255BPT_1%255D) [resolved](https://docs.example.org/NGC-0041872) [[PT_1]](https://docs.example.org/guide)'
    const { container } = render(<TranscriptText role="assistant" text={text} bindings={bindings}
      selected="[PT_1]" onSelect={vi.fn()} />)
    expect(container.querySelector('strong')?.textContent).toBe('NGC-0041872')
    expect(container.querySelector('code')?.textContent).toContain('NGC-0041872')
    expect(screen.getByRole('cell').textContent).toBe('NGC-0041872')
    const links = screen.getAllByRole('link')
    expect(links.length).toBe(1)
    expect(links[0].getAttribute('href')).toBe('https://docs.example.org/guide')
    expect(links[0].querySelector('button')).toBeNull()
    expect(links[0].textContent).toBe('NGC-0041872')
    expect(links[0].querySelector('[data-selected="true"]')).toBeTruthy()
    expect(text).toContain('https://docs.example.org/[PT_1]')
  })

  it('keeps resolved X-ray fallback text inert when the source message is unavailable', () => {
    const empty = { session_id: 'session', seq: 1, messages: [], views: [], steps: [], conversation_turn: null }
    const text = '[private note](https://untrusted.example/visit) **literal text**'
    const { container } = render(<XrayContent data={{
      display: { ...empty, messages: [{ id: 'answer', seq: 1, role: 'assistant', text, status: 'complete' }] },
      model: empty, bindings: [], requests: [], executions: [],
    }} />)
    expect(container.querySelector('a,strong')).toBeNull()
    expect(screen.getByTestId('message-text').textContent).toBe(text)
  })

  it('rejects encoded private and local destinations without changing their labels', () => {
    const destinations = [
      'https://docs.example.org/?patient=Arin+Vellorin',
      'https://docs.example.org/%252525255BPT_1%252525255D',
      'http://localhost./sessions/private', 'http://127.1/api', 'http://[::1]/api',
      'http://10.0.0.1/api', 'https://user:password@docs.example.org/',
      'mailto:someone@example.org', 'vbscript:alert%281%29',
    ]
    const text = destinations.map((url, index) => `[Link ${index}](${url})`).join('\n\n')
    const { container } = render(<TranscriptText role="assistant" text={text}
      bindings={[{ token: '[PT_1]', value: 'Arin Vellorin', kind: 'PT' }]} />)
    expect(container.querySelector('a')).toBeNull()
    for (let index = 0; index < destinations.length; index += 1) {
      expect(container.textContent).toContain(`Link ${index}`)
    }
  })
})

const analysisDraft: DraftState = {
  draft_id: 'draft-0001', view_id: 'view-0001', app_id: 'somatic-snv',
  specimen_handle: 'query-0001', parameters: { min_vaf: 0.05, min_depth: 20 },
  version: 1, content_hash: 'a'.repeat(64), status: 'editing', validation: [], job_id: null,
}

it('generates parameter controls and requires review after stale confirmation', async () => {
  const changed = { ...analysisDraft, version: 2, content_hash: 'b'.repeat(64), parameters: { min_vaf: 0.03, min_depth: 20 } }
  const fetcher = vi.fn().mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({
    detail: 'The draft changed.', current: changed,
    changes: [{ field: 'parameters.min_vaf', before: 0.05, after: 0.03 }],
  }) }).mockResolvedValueOnce({ ok: true, json: async () => ({ job_id: 'job-0001', status: 'pending' }) })
  vi.stubGlobal('fetch', fetcher)
  render(<DraftEditor draft={analysisDraft} catalog={catalog as unknown as CatalogApp[]} sessionId="session" />)
  expect((screen.getByRole('spinbutton', { name: 'Minimum VAF' }) as HTMLInputElement).value).toBe('0.05')
  await userEvent.click(screen.getByRole('button', { name: 'Confirm submission' }))
  await screen.findByText('Draft changed')
  expect(screen.getByText(/0.05 to 0.03/)).toBeTruthy()
  expect((screen.getByRole('button', { name: 'Confirm submission' }) as HTMLButtonElement).disabled).toBe(true)
  await userEvent.click(screen.getByRole('button', { name: 'Review current draft' }))
  expect((screen.getByRole('spinbutton', { name: 'Minimum VAF' }) as HTMLInputElement).value).toBe('0.03')
  await userEvent.click(screen.getByRole('button', { name: 'Confirm submission' }))
  await screen.findByText('Submitted / job-0001')
  expect(JSON.parse(fetcher.mock.calls[0][1].body).content_hash).toBe(analysisDraft.content_hash)
  expect(JSON.parse(fetcher.mock.calls[1][1].body).content_hash).toBe(changed.content_hash)
})

it('draft validation disables confirmation but permits editing and a save', async () => {
  const draft = { ...analysisDraft, validation: [{ code: 'missing_matched_normal', field: 'specimen_handle', message: 'A matched normal specimen is missing.' }] }
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...draft, version: 2 }) })
  vi.stubGlobal('fetch', fetcher)
  render(<DraftEditor draft={draft} catalog={catalog as unknown as CatalogApp[]} sessionId="session" />)
  expect(screen.getByText('A matched normal specimen is missing.')).toBeTruthy()
  expect((screen.getByRole('button', { name: 'Confirm submission' }) as HTMLButtonElement).disabled).toBe(true)
  const input = screen.getByRole('spinbutton', { name: 'Minimum VAF' })
  await userEvent.clear(input); await userEvent.type(input, '0.03')
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1))
  expect(fetcher.mock.calls[0][1].method).toBe('PATCH')
  expect(JSON.parse(fetcher.mock.calls[0][1].body).parameters).toEqual({ min_vaf: 0.03 })
})

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
  expect(screen.getByText('Specimen search failed')).toBeTruthy()
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

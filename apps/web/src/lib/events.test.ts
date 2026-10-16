import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useSession } from './use-session'
import type { PrivacyBinding } from './api'
import { reduceEvent } from './events'
import type { EventType, LogEvent, Payloads, Projection } from './events'
import fixture from '../../../../evals/fixtures/view-replay.json'
import { selectionAt, validateViewSpec, viewPosition } from './views'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const empty: Projection = {
  session_id: 'session',
  seq: 0,
  messages: [],
  views: [],
  steps: [],
  conversation_turn: null,
}

function event<Kind extends EventType>(
  seq: number,
  type: Kind,
  payload: Payloads[Kind],
): LogEvent {
  return {
    schema_version: 2,
    session_id: 'session',
    seq,
    conversation_turn_id: 'turn',
    created_at: '2026-01-01T00:00:00Z',
    type,
    payload,
  } as LogEvent
}

it('streams unchanged model text and fetches display bindings when a token crosses deltas', async () => {
  const streams: FakeEventSource[] = []
  class FakeEventSource extends EventTarget {
    url: string
    onopen: (() => void) | null = null
    onerror: (() => void) | null = null
    close = vi.fn()
    constructor(url: string) { super(); this.url = url; streams.push(this) }
  }
  let bindings: PrivacyBinding[] = []
  let activeSession = 'session'
  let failBindings = false
  const fetcher = vi.fn(async (path: string) => ({
    ok: !failBindings || !path.endsWith('/bindings'), status: 503,
    json: async () => path.endsWith('/bindings')
      ? failBindings ? { detail: 'Display bindings unavailable' } : bindings
      : { ...empty, session_id: activeSession },
  }))
  vi.stubGlobal('fetch', fetcher)
  vi.stubGlobal('EventSource', FakeEventSource)
  const { result, rerender } = renderHook(({ sessionId }) => useSession(sessionId), {
    initialProps: { sessionId: 'session' },
  })
  await waitFor(() => expect(streams.length).toBe(1))
  expect(fetcher.mock.calls[0][0]).toContain('representation=model')
  expect(streams[0].url).toContain('representation=model')
  act(() => {
    streams[0].onopen?.()
    streams[0].dispatchEvent(new MessageEvent('log', {
      data: JSON.stringify(event(1, 'text_delta', { message_id: 'answer', text: '**Patient [PT_' })),
      lastEventId: '1',
    }))
  })
  expect(result.current.state?.messages[0].text).toBe('**Patient [PT_')
  bindings = [{ token: '[PT_1]', value: 'Arin Vellorin', kind: 'PT' }]
  act(() => streams[0].dispatchEvent(new MessageEvent('log', {
    data: JSON.stringify(event(2, 'text_delta', { message_id: 'answer', text: '1]** [link](https://example.org/[PT_1])' })),
    lastEventId: '2',
  })))
  await waitFor(() => expect(result.current.bindings).toEqual(bindings))
  expect(result.current.state?.messages[0].text).toBe('**Patient [PT_1]** [link](https://example.org/[PT_1])')
  expect(empty.messages).toEqual([])
  activeSession = 'other-session'
  failBindings = true
  rerender({ sessionId: activeSession })
  expect(result.current.bindings).toEqual([])
  await waitFor(() => expect(result.current.state?.session_id).toBe(activeSession))
  expect(result.current.bindings).toEqual([])
  expect(result.current.error).toBe('Display bindings unavailable')
})

describe('event projection', () => {
  it('ignores duplicate replay without mutating the previous state', () => {
    const delta = event(1, 'text_delta', {
      message_id: 'answer',
      text: 'Hello ',
    })
    const first = reduceEvent(empty, delta)
    expect(reduceEvent(first, delta)).toBe(first)
    const second = reduceEvent(
      first,
      event(2, 'text_delta', { message_id: 'answer', text: 'world.' }),
    )
    expect(second.messages[0].text).toBe('Hello world.')
    expect(first.messages[0].text).toBe('Hello ')
    expect(empty.messages).toEqual([])
  })

  it('rejects gaps', () => {
    expect(() =>
      reduceEvent(empty, event(2, 'conversation_turn_started', {})),
    ).toThrow('Event gap')
  })

  it('rejects another session', () => {
    expect(() =>
      reduceEvent(empty, {
        ...event(1, 'conversation_turn_started', {}),
        session_id: 'other',
      }),
    ).toThrow('different session')
  })

  it('removes partial assistant messages by id and permits replacements', () => {
    const partial = reduceEvent(
      empty,
      event(1, 'text_delta', { message_id: 'old', text: 'partial' }),
    )
    const removed = reduceEvent(
      partial,
      event(2, 'message_dropped', { message_id: 'old' }),
    )
    expect(removed.messages).toEqual([])
    const replaced = reduceEvent(
      removed,
      event(3, 'text_delta', { message_id: 'new', text: 'answer' }),
    )
    const done = reduceEvent(
      replaced,
      event(4, 'message_done', { message_id: 'new' }),
    )
    expect(done.messages).toEqual([
      {
        id: 'new',
        seq: 3,
        role: 'assistant',
        text: 'answer',
        status: 'complete',
      },
    ])
  })

  it('ends a failed conversation turn instead of leaving partial messages streaming', () => {
    const partial = reduceEvent(
      empty,
      event(1, 'text_delta', { message_id: 'answer', text: 'text' }),
    )
    const failed = reduceEvent(
      partial,
      event(2, 'conversation_turn_failed', { error: 'Scripted failure' }),
    )
    expect(failed.conversation_turn).toEqual({
      id: 'turn',
      status: 'failed',
      error: 'Scripted failure',
    })
    expect(failed.messages[0].status).toBe('failed')
  })

  it('continues from a snapshot and starts the next conversation turn without losing history', () => {
    const snapshot: Projection = {
      ...empty,
      seq: 10,
      messages: [
        {
          id: 'answer',
          seq: 2,
          role: 'assistant',
          text: 'Hello ',
          status: 'streaming',
        },
      ],
      conversation_turn: { id: 'turn', status: 'running', error: null },
    }
    const resumed = reduceEvent(
      snapshot,
      event(11, 'text_delta', { message_id: 'answer', text: 'world.' }),
    )
    const finished = reduceEvent(
      resumed,
      event(12, 'conversation_turn_finished', {}),
    )
    expect(finished.conversation_turn?.status).toBe('finished')
    expect(finished.messages[0].text).toBe('Hello world.')
    const nextTurn = reduceEvent(finished, {
      ...event(13, 'user_message', { message_id: 'user', text: 'Again' }),
      conversation_turn_id: 'next-turn',
    })
    expect(nextTurn.messages).toHaveLength(2)
    expect(nextTurn.conversation_turn?.status).toBe('running')
    expect(nextTurn.conversation_turn?.id).toBe('next-turn')
  })

  it('replaces the latest attempt on retry and keeps its views', () => {
    const asked: Projection = {
      ...empty,
      seq: 7,
      messages: [
        { id: 'q1', seq: 1, role: 'user', text: 'Hello', status: 'complete' },
        { id: 'a1', seq: 2, role: 'assistant', text: 'Hi.', status: 'complete' },
        { id: 'q2', seq: 4, role: 'user', text: 'Chart it', status: 'complete' },
        { id: 'a2', seq: 7, role: 'assistant', text: 'Declined.', status: 'complete' },
      ],
      steps: [
        { id: 's1', seq: 3, title: 'Agent step 1', detail: '', status: 'complete' },
        { id: 's2', seq: 5, title: 'Agent step 1', detail: '', status: 'complete' },
      ],
      refusals: [{ id: 'turn', seq: 6, code: 'out_of_domain', message: 'Declined.' }],
      views: [{ id: 'view-0001', seq: 5, spec: { kind: 'table', version: 1, props: { title: 'Rows', columns: [], rows: [], row_count: 0 } } }],
      conversation_turn: { id: 'turn', status: 'finished', error: null },
    }
    const retried = reduceEvent(asked, {
      ...event(8, 'user_message', { message_id: 'q3', text: 'Chart it', retry_of: 'turn' }),
      conversation_turn_id: 'retry',
    })
    expect(retried.messages.map((message) => message.id)).toEqual(['q1', 'a1', 'q2'])
    expect(retried.steps.map((step) => step.id)).toEqual(['s1'])
    expect(retried.refusals).toEqual([])
    expect(retried.views).toBe(asked.views)
    expect(retried.conversation_turn).toEqual({ id: 'retry', status: 'running', error: null })
    const stale = reduceEvent(retried, {
      ...event(9, 'user_message', { message_id: 'q4', text: 'Again', retry_of: 'turn' }),
      conversation_turn_id: 'other',
    })
    expect(stale.messages.at(-1)?.id).toBe('q4')
  })

  it.each(['tool_call', 'tool_result', 'draft_updated'] as const)(
    'advances the cursor for the reserved %s vocabulary',
    (type) => {
      expect(reduceEvent(empty, event(1, type, {}))).toEqual({
        ...empty,
        seq: 1,
      })
    },
  )

  it('projects structured refusals once and preserves them through refresh and the next turn', () => {
    const refused = event(1, 'refused', {
      code: 'out_of_domain', message: 'I can help with specimen and library queries.',
    })
    const state = reduceEvent(empty, refused)
    expect(state.messages).toEqual([])
    expect(state.refusals).toEqual([{
      id: 'turn', seq: 1, ...refused.payload,
    }])
    expect(reduceEvent(state, refused)).toBe(state)
    const restored = JSON.parse(JSON.stringify(state)) as Projection
    const continued = reduceEvent(restored, event(2, 'conversation_turn_finished', {}))
    expect(continued.refusals).toEqual(state.refusals)
    expect(continued.conversation_turn?.status).toBe('finished')
    expect(empty.refusals).toBeUndefined()
  })

  it('updates one persisted draft without replacing view history or turn lifecycle', () => {
    const draft = { draft_id: 'draft-0001', view_id: 'view-0001', app_id: 'readqc',
      specimen_handle: 'query-0001', parameters: { min_coverage: 30 }, version: 1,
      content_hash: 'a'.repeat(64), status: 'editing' as const, validation: [], job_id: null }
    const first = reduceEvent(empty, event(1, 'draft_updated', { draft }))
    const next = reduceEvent(first, event(2, 'draft_updated', { draft: { ...draft, version: 2, parameters: { min_coverage: 40 } } }))
    expect(next.drafts?.[draft.draft_id].parameters.min_coverage).toBe(40)
    expect(first.drafts?.[draft.draft_id].parameters.min_coverage).toBe(30)
    expect(next.conversation_turn).toBeNull()
    expect(next.views).toBe(empty.views)
  })
})

describe('view and step replay', () => {
  const events = fixture.events.map(
    (draft, index) =>
      ({
        ...draft,
        seq: index + 1,
        schema_version: 2,
        session_id: 'session',
        conversation_turn_id: 'turn',
        created_at: '2026-01-01T00:00:00Z',
      }) as LogEvent,
  )
  const complete = events.reduce(reduceEvent, empty)

  it.each(events.map((_, index) => index))(
    'agrees with the shared log prefix %i',
    (index) => {
      const prefix = events.slice(0, index + 1).reduce(reduceEvent, empty)
      expect(prefix.views.map((view) => view.id)).toEqual(
        fixture.prefix_view_ids[index],
      )
      expect(reduceEvent(prefix, events[index])).toBe(prefix)
      const snapshot = JSON.parse(JSON.stringify(prefix)) as Projection
      expect(events.slice(index + 1).reduce(reduceEvent, snapshot)).toEqual(
        complete,
      )
      expect(empty.views).toEqual([])
    },
  )

  it('preserves view identity and marker positions across duplicates', () => {
    expect(complete.views.map((view) => view.seq)).toEqual([4, 8])
    expect(complete.steps.map((step) => [step.seq, step.status])).toEqual([
      [3, 'complete'],
      [7, 'complete'],
    ])
    expect(complete.steps[0].detail).toBe('14 specimens; 1 displayed.')
    expect(complete.messages[1].seq).toBe(5)
  })

  it('keeps prior surface and pending marker states when a turn fails', () => {
    const prefix = events.slice(0, 8).reduce(reduceEvent, empty)
    const failed = reduceEvent(
      prefix,
      event(9, 'conversation_turn_failed', { error: 'Invalid view' }),
    )
    expect(failed.views).toBe(prefix.views)
    expect(failed.steps[1].status).toBe('failed')
    expect(prefix.steps[1].status).toBe('running')
  })

  it('rejects malformed view events without mutating the current surface', () => {
    expect(() =>
      reduceEvent(
        empty,
        event(1, 'view_pushed', {
          view_id: 'invalid',
          spec: { kind: 'table', version: 1, props: {} },
        }),
      ),
    ).toThrow('View schema error')
    expect(empty.views).toEqual([])
  })

  it('pins history by identity and resumes following only at the head', () => {
    const views = complete.views
    expect(viewPosition([], undefined)).toBe(-1)
    expect(viewPosition(views, undefined)).toBe(1)
    const pinned = selectionAt(views, 0)
    expect(pinned).toBe('intake')
    const appended = [...views, { ...views[1], id: 'third', seq: 20 }]
    expect(viewPosition(appended, pinned)).toBe(0)
    expect(viewPosition(appended, undefined)).toBe(2)
    expect(selectionAt(appended, 2)).toBeUndefined()
    expect(viewPosition(appended, 'missing')).toBe(-1)
    expect(viewPosition(appended, views[1].id)).toBe(1)
    expect(viewPosition([...appended, { ...views[0], id: 'fourth', seq: 30 }], 'third')).toBe(2)
  })

  it('shares table row, cell, and source constraints with the server', () => {
    const spec = complete.views[0].spec
    expect(validateViewSpec(spec)).toBe(spec)
    for (const props of [
      { ...spec.props, rows: [[12]] },
      { ...spec.props, rows: [['extra', 'cell']] },
      { ...spec.props, row_count: 0 },
      { ...spec.props, handle: 'query-1' },
    ])
      expect(() => validateViewSpec({ ...spec, props })).toThrow(
        'View schema error',
      )
    expect(() => validateViewSpec({ ...spec, version: 2 })).toThrow(
      'Unsupported view',
    )
  })
})

import { describe, expect, it } from 'vitest'
import { reduceEvent } from './events'
import type { EventType, LogEvent, Payloads, Projection } from './events'

const empty: Projection = {
  session_id: 'session',
  seq: 0,
  messages: [],
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
      { id: 'new', role: 'assistant', text: 'answer', status: 'complete' },
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

  it.each([
    'step_started',
    'step_finished',
    'tool_call',
    'tool_result',
    'view_pushed',
    'refused',
    'draft_updated',
  ] as const)('advances the cursor for the reserved %s vocabulary', (type) => {
    expect(reduceEvent(empty, event(1, type, {}))).toEqual({ ...empty, seq: 1 })
  })
})

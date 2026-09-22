import { validateViewSpec } from './views'
import type { PushedView, ViewSpec } from './views'

type MessageRef = { message_id: string }
type MessageText = MessageRef & { text: string }

export type Payloads = {
  user_message: MessageText
  conversation_turn_started: Record<string, never>
  conversation_turn_finished: Record<string, never>
  conversation_turn_failed: { error: string }
  text_delta: MessageText
  message_done: MessageRef
  message_dropped: MessageRef
  step_started: { step_id: string; title: string; detail?: string }
  step_finished: {
    step_id: string
    status?: 'complete' | 'failed'
    detail?: string | null
  }
  tool_call: {
    step_id: string
    call_id: string
    name: string
    arguments: string
  }
  tool_result: {
    step_id: string
    call_id: string
    name: string
    result: Record<string, unknown>
  }
  view_pushed: { view_id: string; spec: ViewSpec }
  refused: Record<string, unknown>
  draft_updated: Record<string, unknown>
}

export type EventType = keyof Payloads
export type LogEvent = {
  [Kind in EventType]: {
    schema_version: 2
    session_id: string
    seq: number
    conversation_turn_id: string
    created_at: string
    type: Kind
    payload: Payloads[Kind]
  }
}[EventType]

export type ChatMessage = {
  id: string
  seq: number
  role: 'user' | 'assistant'
  text: string
  status: 'streaming' | 'complete' | 'failed'
}

export type StepState = {
  id: string
  seq: number
  title: string
  detail: string
  status: 'running' | 'complete' | 'failed'
  tools?: {
    call_id: string
    name: string
    arguments: string
    result: Record<string, unknown> | null
  }[]
}

export type Projection = {
  session_id: string
  seq: number
  messages: ChatMessage[]
  views: PushedView[]
  steps: StepState[]
  conversation_turn: {
    id: string
    status: 'running' | 'finished' | 'failed'
    error: string | null
  } | null
}

export function reduceEvent(state: Projection, event: LogEvent): Projection {
  if (event.schema_version !== 2) throw new Error('Unsupported event schema')
  if (event.session_id !== state.session_id)
    throw new Error('Event belongs to a different session')
  if (event.seq <= state.seq) return state
  if (event.seq !== state.seq + 1) throw new Error('Event gap')

  const next: Projection = { ...state, seq: event.seq }
  switch (event.type) {
    case 'user_message':
      next.messages = [
        ...state.messages,
        {
          id: event.payload.message_id,
          seq: event.seq,
          role: 'user',
          text: event.payload.text,
          status: 'complete',
        },
      ]
      next.conversation_turn = {
        id: event.conversation_turn_id,
        status: 'running',
        error: null,
      }
      break
    case 'conversation_turn_started':
      next.conversation_turn = {
        id: event.conversation_turn_id,
        status: 'running',
        error: null,
      }
      break
    case 'text_delta': {
      const existing = state.messages.some(
        (message) => message.id === event.payload.message_id,
      )
      next.messages = existing
        ? state.messages.map((message) =>
            message.id === event.payload.message_id
              ? { ...message, text: message.text + event.payload.text }
              : message,
          )
        : [
            ...state.messages,
            {
              id: event.payload.message_id,
              seq: event.seq,
              role: 'assistant',
              text: event.payload.text,
              status: 'streaming',
            },
          ]
      break
    }
    case 'message_done':
      next.messages = state.messages.map((message) =>
        message.id === event.payload.message_id
          ? { ...message, status: 'complete' }
          : message,
      )
      break
    case 'message_dropped':
      next.messages = state.messages.filter(
        (message) => message.id !== event.payload.message_id,
      )
      break
    case 'view_pushed': {
      const spec = validateViewSpec(event.payload.spec)
      if (!state.views.some((view) => view.id === event.payload.view_id)) {
        next.views = [
          ...state.views,
          { id: event.payload.view_id, seq: event.seq, spec },
        ]
      }
      break
    }
    case 'step_started':
      if (!state.steps.some((step) => step.id === event.payload.step_id)) {
        next.steps = [
          ...state.steps,
          {
            id: event.payload.step_id,
            seq: event.seq,
            title: event.payload.title,
            detail: event.payload.detail ?? '',
            status: 'running',
            tools: [],
          },
        ]
      }
      break
    case 'tool_call':
      next.steps = state.steps.map((step) =>
        step.id === event.payload.step_id &&
        !step.tools?.some((tool) => tool.call_id === event.payload.call_id)
          ? {
              ...step,
              tools: [...(step.tools ?? []), {
                call_id: event.payload.call_id,
                name: event.payload.name,
                arguments: event.payload.arguments,
                result: null,
              }],
            }
          : step,
      )
      break
    case 'tool_result':
      next.steps = state.steps.map((step) =>
        step.id === event.payload.step_id
          ? {
              ...step,
              tools: step.tools?.map((tool) =>
                tool.call_id === event.payload.call_id
                  ? { ...tool, result: event.payload.result }
                  : tool,
              ),
            }
          : step,
      )
      break
    case 'step_finished':
      next.steps = state.steps.map((step) =>
        step.id === event.payload.step_id
          ? {
              ...step,
              status: event.payload.status ?? 'complete',
              detail: event.payload.detail ?? step.detail,
            }
          : step,
      )
      break
    case 'conversation_turn_failed':
    case 'conversation_turn_finished': {
      const failed = event.type === 'conversation_turn_failed'
      next.conversation_turn = {
        id: event.conversation_turn_id,
        status: failed ? 'failed' : 'finished',
        error:
          event.type === 'conversation_turn_failed'
            ? event.payload.error
            : null,
      }
      next.messages = state.messages.map((message) =>
        message.status === 'streaming'
          ? { ...message, status: failed ? 'failed' : 'complete' }
          : message,
      )
      next.steps = state.steps.map((step) =>
        step.status === 'running'
          ? { ...step, status: failed ? 'failed' : 'complete' }
          : step,
      )
      break
    }
  }
  return next
}

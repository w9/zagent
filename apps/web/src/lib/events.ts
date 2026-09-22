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
  step_started: Record<string, unknown>
  step_finished: Record<string, unknown>
  tool_call: Record<string, unknown>
  tool_result: Record<string, unknown>
  view_pushed: Record<string, unknown>
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
  role: 'user' | 'assistant'
  text: string
  status: 'streaming' | 'complete' | 'failed'
}

export type Projection = {
  session_id: string
  seq: number
  messages: ChatMessage[]
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
      break
    }
  }
  return next
}

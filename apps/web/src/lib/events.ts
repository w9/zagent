import { validateArtifactSpec } from './artifacts'
import type { ArtifactSpec, PublishedArtifact } from './artifacts'

type MessageRef = { message_id: string }
type MessageText = MessageRef & { text: string }
export type RefusalCode = 'out_of_domain' | 'unsupported_capability'
  | 'requires_human_authority' | 'unsafe_request'
export type RefusedState = { id: string; seq: number; code: RefusalCode; message: string }
export type DraftState = {
  draft_id: string; artifact_id: string; app_id: string; specimen_handle: string | null
  parameters: Record<string, string | number | boolean>; version: number; content_hash: string
  status: 'editing' | 'submitted'; job_id: string | null
  validation: { code: string; field: string; message: string }[]
}
export type JobState = {
  job_id: string; draft_id: string; app_id: string; specimen_handle: string | null
  parameters: Record<string, string | number | boolean>; confirmed_version: number
  content_hash: string; status: 'pending'
}

export type Payloads = {
  user_message: MessageText & { retry_of?: string }
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
  artifact_published: { artifact_id: string; spec: ArtifactSpec }
  refused: { code: RefusalCode; message: string }
  draft_updated: { draft?: DraftState }
  job_submitted: { job: JobState }
  session_updated: Record<string, unknown>
  privacy_alert: { code: 'egress_identifier'; message: string }
}

export type EventType = keyof Payloads
export type LogEvent = {
  [Kind in EventType]: {
    schema_version: 3
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

/** The artifact a tool published, from its receipt. Receipts keep the model-facing `view_id` key. */
export function toolArtifact({ result }: NonNullable<StepState['tools']>[number]) {
  const id = result?.view_id, title = result?.title
  return typeof id === 'string' && typeof title === 'string' ? { id, title } : undefined
}

export type Projection = {
  session_id: string
  seq: number
  messages: ChatMessage[]
  artifacts: PublishedArtifact[]
  steps: StepState[]
  refusals?: RefusedState[]
  drafts?: Record<string, DraftState>
  jobs?: Record<string, JobState>
  conversation_turn: {
    id: string
    status: 'running' | 'finished' | 'failed'
    error: string | null
  } | null
}

export function reduceEvent(state: Projection, event: LogEvent): Projection {
  if (event.schema_version !== 3) throw new Error('Unsupported event schema')
  if (event.session_id !== state.session_id)
    throw new Error('Event belongs to a different session')
  if (event.seq <= state.seq) return state
  if (event.seq !== state.seq + 1) throw new Error('Event gap')

  const next: Projection = { ...state, seq: event.seq }
  switch (event.type) {
    case 'user_message': {
      const question = state.messages.findLast((message) => message.role === 'user')
      if (question && event.payload.retry_of && event.payload.retry_of === state.conversation_turn?.id) {
        // A retry keeps the question and hides the attempt it replaces.
        next.messages = state.messages.filter((message) => message.seq <= question.seq)
        next.steps = state.steps.filter((step) => step.seq < question.seq)
        next.refusals = state.refusals?.filter((refusal) => refusal.seq < question.seq)
      } else {
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
      }
      next.conversation_turn = {
        id: event.conversation_turn_id,
        status: 'running',
        error: null,
      }
      break
    }
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
    case 'refused': {
      if (!['out_of_domain', 'unsupported_capability', 'requires_human_authority', 'unsafe_request']
        .includes(event.payload.code) || typeof event.payload.message !== 'string')
        throw new Error('Invalid refusal event')
      if (!state.refusals?.some((item) => item.id === event.conversation_turn_id)) {
        next.refusals = [...(state.refusals ?? []), {
          id: event.conversation_turn_id, seq: event.seq, ...event.payload,
        }]
      }
      break
    }
    case 'draft_updated':
      if (event.payload.draft?.draft_id) next.drafts = {
        ...state.drafts, [event.payload.draft.draft_id]: event.payload.draft,
      }
      break
    case 'job_submitted':
      next.jobs = { ...state.jobs, [event.payload.job.job_id]: event.payload.job }
      break
    case 'artifact_published': {
      const spec = validateArtifactSpec(event.payload.spec)
      if (!state.artifacts.some((artifact) => artifact.id === event.payload.artifact_id)) {
        next.artifacts = [
          ...state.artifacts,
          { id: event.payload.artifact_id, seq: event.seq, spec },
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

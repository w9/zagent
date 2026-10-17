import type { PublishedArtifact } from '../../lib/artifacts'
import type { ChatMessage, Projection, RefusedState, StepState } from '../../lib/events'

export type Entry =
  | { kind: 'message'; value: ChatMessage }
  | { kind: 'steps'; value: StepState[] }
  | { kind: 'refusal'; value: RefusedState }
  | { kind: 'artifact'; value: PublishedArtifact }

/**
 * Messages, steps, refusals and artifacts in log order. Consecutive steps form one group, and an
 * artifact published during a run of steps follows the whole run, so a turn's steps stay together.
 */
export function timeline(state: Projection): Entry[] {
  const items = [
    ...state.messages.map((value) => ({ kind: 'message' as const, value })),
    ...state.steps.map((value) => ({ kind: 'step' as const, value })),
    ...(state.refusals ?? []).map((value) => ({ kind: 'refusal' as const, value })),
    ...state.artifacts.map((value) => ({ kind: 'artifact' as const, value })),
  ].sort((first, second) => first.value.seq - second.value.seq)
  const entries: Entry[] = []
  for (const item of items) {
    if (item.kind !== 'step') {
      entries.push(item)
      continue
    }
    let index = entries.length - 1
    while (entries[index]?.kind === 'artifact') index -= 1
    const group = entries[index]
    if (group?.kind === 'steps') group.value.push(item.value)
    else entries.push({ kind: 'steps', value: [item.value] })
  }
  return entries
}

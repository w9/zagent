import { Component } from 'react'
import type { ReactNode } from 'react'
import { Notice } from '../ui/notice'

/** Contains a failing artifact so the rest of the conversation and the panel keep working. */
export class ArtifactBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    return this.state.error ? (
      <Notice tone="danger" role="alert" title="Artifact unavailable">{this.state.error.message}</Notice>
    ) : (
      this.props.children
    )
  }
}

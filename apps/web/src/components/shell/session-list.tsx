import { Link } from '@tanstack/react-router'
import { Check, MessageSquare, Pencil, Plus, ShieldCheck, X } from 'lucide-react'
import { useState } from 'react'
import type { Persona, Session } from '../../lib/api'
import { formatTimestamp } from '../../lib/format'
import { Button } from '../ui/button'
import { Field, Input, Select } from '../ui/field'
import { IconButton } from '../ui/icon-button'
import { Notice } from '../ui/notice'

export function SessionList({
  sessions,
  selectedId,
  creating = false,
  showTitle = true,
  personas = [],
  persona,
  onPersonaChange,
  onCreate,
  onNavigate,
  onRename,
}: {
  sessions: Session[]
  selectedId?: string
  creating?: boolean
  showTitle?: boolean
  personas?: Persona[]
  persona?: string
  onPersonaChange?: (persona: string) => void
  onCreate: () => void
  onNavigate?: () => void
  onRename: (id: string, title: string) => Promise<void>
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [saving, setSaving] = useState(false)
  const [renameError, setRenameError] = useState<string | null>(null)
  const chosen = personas.find((item) => item.id === persona)

  async function save(id: string) {
    if (saving || !title.trim()) return
    setSaving(true)
    try {
      await onRename(id, title.trim())
      setEditing(null)
      setRenameError(null)
    } catch (reason) {
      setRenameError(reason instanceof Error ? reason.message : 'Rename failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {showTitle && (
        <div className="flex items-center justify-between px-4 pt-5 pb-3">
          <h2 className="text-sm font-semibold text-strong">Sessions</h2>
          <span className="font-mono text-xs text-muted">{sessions.length}</span>
        </div>
      )}
      <div className={showTitle ? 'flex flex-col gap-3 px-3' : 'flex flex-col gap-3 px-3 pt-3'}>
        {personas.length > 0 && (
          <Field label="Persona for new sessions" hint={chosen?.description}>
            <Select value={persona} disabled={creating} onChange={(event) => onPersonaChange?.(event.target.value)}>
              {personas.map((item) => (
                <option key={item.id} value={item.id}>{`${item.title} · ${item.name}`}</option>
              ))}
            </Select>
          </Field>
        )}
        <Button icon={Plus} loading={creating} onClick={onCreate} className="w-full justify-start">New session</Button>
      </div>
      <nav aria-label="Sessions" className="min-h-0 flex-1 overflow-y-auto px-2 py-3">
        {!sessions.length && (
          <p className="px-2 py-4 text-sm text-muted">No sessions yet. Start one to ask about specimens and analyses.</p>
        )}
        <ul className="flex flex-col gap-0.5">
          {sessions.map((session) => (
            <li key={session.id} data-session-id={session.id} className="group flex items-center gap-1">
              {editing === session.id ? (
                <form
                  className="flex w-full items-center gap-1 p-1"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void save(session.id)
                  }}
                >
                  <Input
                    aria-label="Session title"
                    value={title}
                    maxLength={120}
                    autoFocus
                    className="text-sm"
                    onChange={(event) => setTitle(event.target.value)}
                  />
                  <IconButton size="sm" type="submit" label="Save session title" icon={Check} disabled={saving || !title.trim()} />
                  <IconButton size="sm" label="Cancel rename" icon={X} onClick={() => setEditing(null)} />
                </form>
              ) : (
                <>
                  <Link
                    to="/sessions/$sessionId"
                    params={{ sessionId: session.id }}
                    search={{}}
                    aria-current={selectedId === session.id ? 'page' : undefined}
                    onClick={onNavigate}
                    className="flex min-w-0 flex-1 items-start gap-2 rounded-md px-2 py-2 text-sm text-default transition-colors hover:bg-hover aria-[current=page]:bg-selected aria-[current=page]:font-medium aria-[current=page]:text-strong"
                  >
                    <MessageSquare aria-hidden className="mt-0.5 size-icon-sm shrink-0 text-muted" />
                    <span className="min-w-0 flex-1">
                      <span className="block wrap-anywhere">{session.title}</span>
                      <span className="block font-mono text-xs font-normal text-muted">{formatTimestamp(session.created_at)}</span>
                    </span>
                  </Link>
                  <IconButton
                    size="sm"
                    label={`Rename ${session.title}`}
                    icon={Pencil}
                    className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100"
                    onClick={() => {
                      setEditing(session.id)
                      setTitle(session.title)
                      setRenameError(null)
                    }}
                  />
                </>
              )}
            </li>
          ))}
        </ul>
        {renameError && <Notice tone="danger" role="alert" className="mx-2 mt-2">{renameError}</Notice>}
      </nav>
      <footer className="flex shrink-0 items-center gap-2 border-t border-subtle px-4 py-3 text-xs text-muted">
        <ShieldCheck aria-hidden className="size-icon-sm" />
        Synthetic data
        <span className="ml-auto font-mono">01</span>
      </footer>
    </div>
  )
}

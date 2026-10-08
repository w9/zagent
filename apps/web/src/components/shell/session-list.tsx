import { Link } from '@tanstack/react-router'
import { Archive, ArchiveRestore, ArrowLeft, Check, Ellipsis, Pencil, Plus, ShieldCheck, X } from 'lucide-react'
import { useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { Persona, Session } from '../../lib/api'
import { formatTimestamp } from '../../lib/format'
import { Button } from '../ui/button'
import { Field, Input, Select } from '../ui/field'
import { IconButton } from '../ui/icon-button'
import { Menu, MenuItem } from '../ui/menu'
import { Notice } from '../ui/notice'
import { Spinner } from '../ui/spinner'

export type SessionListView = 'active' | 'archived'

/** One line per session; the full title and creation time are in its tooltip. */
function SessionRow({
  session,
  selected,
  onNavigate,
  actions,
}: {
  session: Session
  selected: boolean
  onNavigate?: () => void
  actions: ReactNode
}) {
  return (
    <li data-session-id={session.id} className="group relative">
      <Link
        to="/sessions/$sessionId"
        params={{ sessionId: session.id }}
        search={{}}
        title={`${session.title}\n${formatTimestamp(session.created_at)}`}
        aria-current={selected ? 'page' : undefined}
        onClick={onNavigate}
        className="flex h-control items-center rounded-md px-2 text-sm text-default transition-colors -outline-offset-2 group-hover:bg-hover group-hover:pr-8 group-focus-within:pr-8 group-has-[[data-state=open]]:bg-hover group-has-[[data-state=open]]:pr-8 pointer-coarse:pr-8 aria-[current=page]:bg-selected aria-[current=page]:font-medium aria-[current=page]:text-strong"
      >
        <span className="truncate">{session.title}</span>
      </Link>
      <div className="absolute top-0.5 right-0.5 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 has-[[data-state=open]]:opacity-100 pointer-coarse:opacity-100">
        {actions}
      </div>
    </li>
  )
}

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
  view = 'active',
  archived,
  onViewChange,
  onArchive,
  onUnarchive,
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
  view?: SessionListView
  /** Archived sessions, newest archive first; null while loading. */
  archived?: Session[] | null
  onViewChange?: (view: SessionListView) => void
  onArchive: (session: Session) => void
  onUnarchive: (session: Session) => void
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [saving, setSaving] = useState(false)
  const [renameError, setRenameError] = useState<string | null>(null)
  const renaming = useRef(false)
  const chosen = personas.find((item) => item.id === persona)
  const archivedView = view === 'archived'
  const shown = archivedView ? (archived ?? []) : sessions

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
          <h2 className="text-sm font-semibold text-strong">{archivedView ? 'Archived sessions' : 'Sessions'}</h2>
          <span className="font-mono text-xs text-muted">{archivedView ? archived?.length : sessions.length}</span>
        </div>
      )}
      <div className={showTitle ? 'flex flex-col gap-3 px-3' : 'flex flex-col gap-3 px-3 pt-3'}>
        {archivedView ? (
          <Button variant="ghost" icon={ArrowLeft} onClick={() => onViewChange?.('active')} className="w-full justify-start">
            Back to sessions
          </Button>
        ) : (
          <>
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
          </>
        )}
      </div>
      <nav aria-label={archivedView ? 'Archived sessions' : 'Sessions'} className="min-h-0 flex-1 overflow-y-auto px-2 py-3">
        {archivedView && archived === null ? (
          <p role="status" className="flex items-center gap-2 px-2 py-4 text-sm text-muted"><Spinner />Loading archived sessions…</p>
        ) : !shown.length && (
          <p className="px-2 py-4 text-sm text-muted">
            {archivedView
              ? 'No archived sessions. Archive one from its actions menu to keep the list short.'
              : 'No sessions yet. Start one to ask about specimens and analyses.'}
          </p>
        )}
        <ul className="flex flex-col gap-0.5">
          {shown.map((session) =>
            editing === session.id ? (
              <li key={session.id} data-session-id={session.id}>
                <form
                  className="flex w-full items-center gap-1"
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
              </li>
            ) : (
              <SessionRow
                key={session.id}
                session={session}
                selected={selectedId === session.id}
                onNavigate={onNavigate}
                actions={
                  archivedView ? (
                    <IconButton size="sm" label={`Unarchive ${session.title}`} icon={ArchiveRestore} onClick={() => onUnarchive(session)} />
                  ) : (
                    <Menu
                      trigger={<IconButton size="sm" label={`Actions for ${session.title}`} icon={Ellipsis} />}
                      onCloseAutoFocus={(event) => {
                        // The rename field takes focus instead of the menu button.
                        if (renaming.current) event.preventDefault()
                        renaming.current = false
                      }}
                    >
                      <MenuItem
                        icon={Pencil}
                        onSelect={() => {
                          renaming.current = true
                          setEditing(session.id)
                          setTitle(session.title)
                          setRenameError(null)
                        }}
                      >
                        Rename
                      </MenuItem>
                      <MenuItem icon={Archive} onSelect={() => onArchive(session)}>Archive</MenuItem>
                    </Menu>
                  )
                }
              />
            ),
          )}
        </ul>
        {renameError && <Notice tone="danger" role="alert" className="mx-2 mt-2">{renameError}</Notice>}
      </nav>
      <footer className="flex shrink-0 flex-wrap items-center gap-x-2 gap-y-1 border-t border-subtle px-4 py-2 text-xs text-muted">
        {!archivedView && (
          <Button variant="ghost" size="sm" icon={Archive} onClick={() => onViewChange?.('archived')} className="-ml-2">
            Archived
          </Button>
        )}
        <span className="inline-flex items-center gap-2">
          <ShieldCheck aria-hidden className="size-icon-sm" />
          Synthetic data
        </span>
        <span className="ml-auto font-mono">01</span>
      </footer>
    </div>
  )
}

import type { ReactNode } from 'react'
import { CircleAlert, CircleCheck, Info, Plus, Send, TriangleAlert } from 'lucide-react'

const backgrounds = [
  ['surface', 'bg-surface text-muted'],
  ['subtle', 'bg-subtle text-muted'],
  ['muted', 'bg-muted text-muted'],
  ['hover', 'bg-hover text-muted'],
  ['selected', 'bg-selected text-muted'],
  ['accent-subtle', 'bg-accent-subtle text-muted'],
  ['inverse', 'bg-inverse text-inverse'],
  ['accent', 'bg-accent text-on-accent'],
  ['privacy', 'bg-privacy text-privacy'],
] as const
const texts = [
  ['strong', 'text-strong'],
  ['default', 'text-default'],
  ['muted', 'text-muted'],
  ['disabled', 'text-disabled'],
  ['accent', 'text-accent'],
  ['danger', 'text-danger'],
  ['warning', 'text-warning'],
  ['info', 'text-info'],
  ['success', 'text-success'],
] as const
const borders = [
  ['subtle', 'border-subtle'],
  ['default', 'border-default'],
  ['strong', 'border-strong'],
  ['control', 'border-control'],
  ['accent', 'border-accent'],
] as const
const sizes = [
  ['xs', 'text-xs', 'Mono metadata, labels, badges'],
  ['sm', 'text-sm', 'Secondary text, table cells'],
  ['base', 'text-base', 'Body and UI default'],
  ['md', 'text-md', 'Conversation prose'],
  ['lg', 'text-lg', 'Section headings'],
  ['xl', 'text-xl', 'View titles'],
  ['2xl', 'text-2xl', 'Display, serif only'],
] as const
const spacing = [
  ['0.5', 'w-0.5'], ['1', 'w-1'], ['1.5', 'w-1.5'], ['2', 'w-2'], ['3', 'w-3'], ['4', 'w-4'], ['5', 'w-5'],
  ['6', 'w-6'], ['8', 'w-8'], ['10', 'w-10'], ['12', 'w-12'], ['16', 'w-16'], ['24', 'w-24'],
] as const
const status = [
  ['danger', CircleAlert, 'Query failed', 'bg-danger-subtle border-danger text-danger'],
  ['warning', TriangleAlert, 'Reconnecting', 'bg-warning-subtle border-warning text-warning'],
  ['info', Info, 'Outside scope', 'bg-info-subtle border-info text-info'],
  ['success', CircleCheck, 'Job completed', 'bg-success-subtle border-success text-success'],
] as const

function Label({ children }: { children: ReactNode }) {
  return <span className="font-mono text-xs text-muted">{children}</span>
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="font-mono text-xs tracking-caps text-muted uppercase">{title}</h2>
      {children}
    </section>
  )
}

function ThemeColumn({ theme }: { theme: 'light' | 'dark' }) {
  return (
    <div data-theme={theme} className="flex min-w-0 flex-col gap-8 bg-surface p-6 text-default">
      <h1 className="text-lg font-semibold text-strong">{theme === 'light' ? 'Light' : 'Dark'}</h1>

      <Section title="Backgrounds">
        <div className="grid grid-cols-3 gap-2">
          {backgrounds.map(([name, cls]) => (
            <div key={name} className={`flex h-16 items-end rounded-md border border-subtle p-2 ${cls}`}>
              <span className="font-mono text-xs">{name}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Text on surface / subtle / muted">
        <div className="grid grid-cols-3 overflow-hidden rounded-md border border-subtle">
          {['bg-surface', 'bg-subtle', 'bg-muted'].map((bg) => (
            <div key={bg} className={`flex flex-col gap-1 p-3 ${bg}`}>
              {texts.map(([name, cls]) => (
                <span key={name} className={`text-sm ${cls}`}>{name}</span>
              ))}
            </div>
          ))}
        </div>
      </Section>

      <Section title="Borders">
        <div className="grid grid-cols-5 gap-2">
          {borders.map(([name, cls]) => (
            <div key={name} className={`flex h-12 items-end rounded-md border bg-surface p-2 ${cls}`}>
              <Label>{name}</Label>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Status">
        <div className="flex flex-wrap gap-2">
          {status.map(([name, Icon, text, cls]) => (
            <span key={name} className={`inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-xs ${cls}`}>
              <Icon className="size-icon-sm" />
              {text}
            </span>
          ))}
        </div>
      </Section>

      <Section title="Controls">
        <div className="flex flex-wrap items-center gap-2">
          <button className="inline-flex h-control items-center gap-1.5 rounded-md bg-accent px-3 text-sm font-medium text-on-accent transition-colors hover:bg-accent-hover">
            <Send className="size-icon" />Confirm
          </button>
          <button className="inline-flex h-control items-center gap-1.5 rounded-md border border-default bg-surface px-3 text-sm font-medium text-default transition-colors hover:bg-hover">
            <Plus className="size-icon" />New session
          </button>
          <button className="inline-flex h-control items-center rounded-md px-3 text-sm font-medium text-muted transition-colors hover:bg-hover hover:text-default">
            Ghost
          </button>
          <button className="inline-flex h-control items-center rounded-md px-3 text-sm font-medium text-muted outline-2 outline-offset-2 outline-focus">
            Focused
          </button>
          <button disabled className="inline-flex h-control items-center rounded-md bg-accent px-3 text-sm font-medium text-on-accent opacity-50">
            Disabled
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <input className="h-control min-w-0 flex-1 rounded-sm border border-control bg-surface px-2 text-base text-default" placeholder="Search sessions" />
          <label className="inline-flex items-center gap-1.5 text-sm"><input type="checkbox" defaultChecked className="size-icon" />Include controls</label>
        </div>
      </Section>

      <Section title="Prose, privacy token, tooltip">
        <p className="max-w-prose text-md text-default">
          Specimen <span className="rounded-sm border-b border-privacy bg-privacy px-0.5 text-privacy">[PATIENT_7]</span> has
          three libraries; <span className="rounded-sm bg-privacy-selected px-0.5 text-strong">[SAMPLE_2]</span> failed QC.
          See <a className="text-accent underline underline-offset-2">Library QC table</a> and <code className="rounded-sm bg-muted px-1 font-mono text-sm">run_id=4471</code>.
        </p>
        <span className="w-fit rounded-sm bg-inverse px-2 py-1 text-xs text-inverse shadow-md">Rename session</span>
      </Section>

      <Section title="Chart palette">
        <div className="flex gap-2">
          {[1, 2, 3, 4, 5, 6].map((index) => (
            <div key={index} className="h-8 flex-1 rounded-sm" style={{ background: `var(--chart-${index})` }} />
          ))}
        </div>
      </Section>
    </div>
  )
}

export function Specimen() {
  return (
    <main className="flex flex-col">
      <div className="grid grid-cols-1 desktop:grid-cols-2">
        <ThemeColumn theme="light" />
        <ThemeColumn theme="dark" />
      </div>
      <div className="grid grid-cols-1 gap-8 border-t border-subtle bg-subtle p-6 desktop:grid-cols-2">
        <Section title="Type scale">
          {sizes.map(([name, cls, usage]) => (
            <div key={name} className="flex items-baseline gap-4">
              <span className="w-10 shrink-0"><Label>{name}</Label></span>
              <span className={`${cls} ${name === '2xl' ? 'font-serif' : ''} text-strong`}>{usage}</span>
            </div>
          ))}
          <div className="flex flex-col gap-1 pt-2">
            <span className="text-base">DM Sans: Specimens, libraries and runs <span className="font-medium">500</span> <span className="font-semibold">600</span></span>
            <span className="font-serif text-xl">Newsreader: Clinical genomics</span>
            <span className="font-mono text-sm">IBM Plex Mono: RUN-0042 chr17:43,044,295</span>
          </div>
        </Section>
        <div className="flex flex-col gap-8">
          <Section title="Spacing">
            {spacing.map(([step, cls]) => (
              <div key={step} className="flex items-center gap-3">
                <span className="w-10 shrink-0"><Label>{step}</Label></span>
                <div className={`h-2 rounded-sm bg-accent ${cls}`} />
              </div>
            ))}
          </Section>
          <Section title="Radii and shadows">
            <div className="flex flex-wrap gap-4">
              {['rounded-sm', 'rounded-md', 'rounded-lg', 'rounded-full'].map((radius) => (
                <div key={radius} className={`grid size-16 place-items-center border border-control bg-surface ${radius}`}><Label>{radius.slice(8)}</Label></div>
              ))}
              {['shadow-sm', 'shadow-md', 'shadow-lg'].map((shadow) => (
                <div key={shadow} className={`grid size-16 place-items-center rounded-md bg-surface ${shadow}`}><Label>{shadow.slice(7)}</Label></div>
              ))}
            </div>
          </Section>
        </div>
      </div>
    </main>
  )
}

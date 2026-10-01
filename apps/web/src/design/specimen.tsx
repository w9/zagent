import type { ReactNode } from 'react'
import { CircleAlert, CircleCheck, Info, Plus, Send, TriangleAlert } from 'lucide-react'

const backgrounds = [
  { name: 'surface', className: 'bg-surface text-muted' },
  { name: 'subtle', className: 'bg-subtle text-muted' },
  { name: 'muted', className: 'bg-muted text-muted' },
  { name: 'hover', className: 'bg-hover text-muted' },
  { name: 'selected', className: 'bg-selected text-muted' },
  { name: 'accent-subtle', className: 'bg-accent-subtle text-muted' },
  { name: 'inverse', className: 'bg-inverse text-inverse' },
  { name: 'accent', className: 'bg-accent text-on-accent' },
  { name: 'privacy', className: 'bg-privacy text-privacy' },
]
const texts = [
  { name: 'strong', className: 'text-strong' },
  { name: 'default', className: 'text-default' },
  { name: 'muted', className: 'text-muted' },
  { name: 'accent', className: 'text-accent' },
  { name: 'danger', className: 'text-danger' },
  { name: 'warning', className: 'text-warning' },
  { name: 'info', className: 'text-info' },
  { name: 'success', className: 'text-success' },
]
const textBackgrounds = [
  { name: 'surface', className: 'bg-surface' },
  { name: 'subtle', className: 'bg-subtle' },
  { name: 'muted', className: 'bg-muted' },
]
const borders = [
  { name: 'subtle', className: 'border-subtle' },
  { name: 'default', className: 'border-default' },
  { name: 'strong', className: 'border-strong' },
  { name: 'control', className: 'border-control' },
  { name: 'accent', className: 'border-accent' },
]
const statuses = [
  { name: 'danger', Icon: CircleAlert, label: 'Query failed', className: 'bg-danger-subtle border-danger text-danger' },
  { name: 'warning', Icon: TriangleAlert, label: 'Reconnecting', className: 'bg-warning-subtle border-warning text-warning' },
  { name: 'info', Icon: Info, label: 'Outside scope', className: 'bg-info-subtle border-info text-info' },
  { name: 'success', Icon: CircleCheck, label: 'Job completed', className: 'bg-success-subtle border-success text-success' },
]
const sizes = [
  { name: 'xs', usage: 'Mono metadata, labels, badges', className: 'text-xs text-strong' },
  { name: 'sm', usage: 'Secondary text, table cells', className: 'text-sm text-strong' },
  { name: 'base', usage: 'Body and UI default', className: 'text-base text-strong' },
  { name: 'md', usage: 'Conversation prose', className: 'text-md text-strong' },
  { name: 'lg', usage: 'Section headings', className: 'text-lg text-strong' },
  { name: 'xl', usage: 'View titles', className: 'text-xl text-strong' },
  { name: '2xl', usage: 'Display, serif only', className: 'font-serif text-2xl text-strong' },
]
const spacing = [
  { name: '0.5', className: 'w-0.5' },
  { name: '1', className: 'w-1' },
  { name: '1.5', className: 'w-1.5' },
  { name: '2', className: 'w-2' },
  { name: '3', className: 'w-3' },
  { name: '4', className: 'w-4' },
  { name: '5', className: 'w-5' },
  { name: '6', className: 'w-6' },
  { name: '8', className: 'w-8' },
  { name: '10', className: 'w-10' },
  { name: '12', className: 'w-12' },
  { name: '16', className: 'w-16' },
  { name: '24', className: 'w-24' },
]
const radii = [
  { name: 'sm', className: 'rounded-sm' },
  { name: 'md', className: 'rounded-md' },
  { name: 'lg', className: 'rounded-lg' },
  { name: 'full', className: 'rounded-full' },
]
const shadows = [
  { name: 'sm', className: 'shadow-sm' },
  { name: 'md', className: 'shadow-md' },
  { name: 'lg', className: 'shadow-lg' },
]

function Label({ children }: { children: ReactNode }) {
  return <span className="font-mono text-xs text-muted">{children}</span>
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex min-w-0 flex-col gap-3">
      <h2 className="font-mono text-xs tracking-caps text-muted uppercase">{title}</h2>
      {children}
    </section>
  )
}

/** Every token on one page, in the current theme. */
export function Specimen() {
  return (
    <main className="@container bg-surface p-4 text-default">
      <div className="grid grid-cols-1 gap-8 @wide:grid-cols-2">
        <Section title="Backgrounds">
          <div className="grid grid-cols-2 gap-2 @medium:grid-cols-3">
            {backgrounds.map(({ name, className }) => (
              <div key={name} className={`flex h-16 items-end rounded-md border border-subtle p-2 ${className}`}>
                <span className="font-mono text-xs">{name}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Text on surface, subtle and muted">
          <div className="grid grid-cols-1 overflow-hidden rounded-md border border-subtle @narrow:grid-cols-3">
            {textBackgrounds.map((background) => (
              <div key={background.name} className={`flex flex-col gap-1 p-3 ${background.className}`}>
                {texts.map(({ name, className }) => (
                  <span key={name} className={`text-sm ${className}`}>{name}</span>
                ))}
              </div>
            ))}
          </div>
        </Section>

        <Section title="Borders">
          <div className="grid grid-cols-2 gap-2 @medium:grid-cols-5">
            {borders.map(({ name, className }) => (
              <div key={name} className={`flex h-12 items-end rounded-md border bg-surface p-2 ${className}`}>
                <Label>{name}</Label>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Status">
          <div className="flex flex-wrap gap-2">
            {statuses.map(({ name, Icon, label, className }) => (
              <span key={name} className={`inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-xs ${className}`}>
                <Icon aria-hidden className="size-icon-sm" />
                {label}
              </span>
            ))}
          </div>
        </Section>

        <Section title="Controls">
          <div className="flex flex-wrap items-center gap-2">
            <button className="inline-flex h-control items-center gap-1.5 rounded-md bg-accent px-3 text-sm font-medium text-on-accent transition-colors hover:bg-accent-hover">
              <Send aria-hidden className="size-icon" />Confirm
            </button>
            <button className="inline-flex h-control items-center gap-1.5 rounded-md border border-default bg-surface px-3 text-sm font-medium text-default transition-colors hover:bg-hover">
              <Plus aria-hidden className="size-icon" />New session
            </button>
            <button className="inline-flex h-control items-center rounded-md px-3 text-sm font-medium text-muted transition-colors hover:bg-hover hover:text-default">
              Ghost
            </button>
            <button className="inline-flex h-control items-center rounded-md px-3 text-sm font-medium text-muted outline-2 outline-offset-2 outline-focus">
              Focused
            </button>
            <button disabled className="inline-flex h-control items-center rounded-md bg-accent px-3 text-sm font-medium text-on-accent disabled:opacity-50">
              Disabled
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <input aria-label="Search sessions" placeholder="Search sessions" className="h-control min-w-0 flex-1 rounded-sm border border-control bg-surface px-2 text-base text-default" />
            <label className="inline-flex items-center gap-1.5 text-sm">
              <input type="checkbox" defaultChecked className="size-icon" />Include controls
            </label>
          </div>
        </Section>

        <Section title="Prose, privacy token, tooltip">
          <p className="max-w-prose text-md text-default">
            Specimen <span className="rounded-sm border-b border-privacy bg-privacy px-0.5 text-privacy">[PATIENT_7]</span> has
            three libraries; <span className="rounded-sm bg-privacy-selected px-0.5 text-strong">[SAMPLE_2]</span> failed QC.
            See <a href="#qc" className="text-accent underline underline-offset-2">Library QC table</a> and{' '}
            <code className="rounded-sm bg-muted px-1 font-mono text-sm">run_id=4471</code>.
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

        <Section title="Type scale">
          {sizes.map(({ name, usage, className }) => (
            <div key={name} className="flex items-baseline gap-4">
              <span className="w-10 shrink-0"><Label>{name}</Label></span>
              <span className={className}>{usage}</span>
            </div>
          ))}
          <div className="flex flex-col gap-1 pt-2">
            <span className="text-base">
              DM Sans: Specimens, libraries and runs <span className="font-medium">500</span>{' '}
              <span className="font-semibold">600</span>
            </span>
            <span className="font-serif text-xl">Newsreader: Clinical genomics</span>
            <span className="font-mono text-sm wrap-anywhere">IBM Plex Mono: RUN-0042 chr17:43,044,295</span>
          </div>
        </Section>

        <Section title="Spacing">
          {spacing.map(({ name, className }) => (
            <div key={name} className="flex items-center gap-3">
              <span className="w-10 shrink-0"><Label>{name}</Label></span>
              <div className={`h-2 rounded-sm bg-accent ${className}`} />
            </div>
          ))}
        </Section>

        <Section title="Radii and shadows">
          <div className="flex flex-wrap gap-4">
            {radii.map(({ name, className }) => (
              <div key={name} className={`grid size-16 place-items-center border border-control bg-surface ${className}`}>
                <Label>{name}</Label>
              </div>
            ))}
            {shadows.map(({ name, className }) => (
              <div key={name} className={`grid size-16 place-items-center rounded-md bg-surface ${className}`}>
                <Label>{name}</Label>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </main>
  )
}

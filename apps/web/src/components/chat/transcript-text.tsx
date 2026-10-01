import { Children, createContext, createElement, useContext } from 'react'
import type { ReactNode } from 'react'
import Markdown from 'react-markdown'
import type { Components, ExtraProps } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { PrivacyBinding } from '../../lib/api'
import { cn } from '../../lib/utils'

const LinkText = createContext(false)

type PrivacyProps = {
  bindings?: PrivacyBinding[]
  selected?: string | null
  onSelect?: (token: string) => void
}

const PrivacyContext = createContext<PrivacyProps>({})

export type ViewLink = (viewId: string, children: ReactNode) => ReactNode
const ViewLinkContext = createContext<ViewLink | undefined>(undefined)
const VIEW_HREF = /^view:(view-[0-9]{4,})$/

const tokenClassName =
  'inline rounded-sm border-b border-privacy bg-privacy px-0.5 text-privacy wrap-anywhere aria-pressed:bg-privacy-selected aria-pressed:text-strong data-[selected=true]:bg-privacy-selected data-[selected=true]:text-strong'

// Assistant Markdown, element by element. Code blocks and tables scroll inside the transcript.
const proseClassNames: Record<string, string> = {
  p: 'my-3 first:mt-0 last:mb-0',
  h1: 'mt-6 mb-2 text-lg font-semibold text-strong first:mt-0',
  h2: 'mt-5 mb-2 font-semibold text-strong first:mt-0',
  h3: 'mt-4 mb-1 font-semibold text-strong first:mt-0',
  h4: 'mt-4 mb-1 font-semibold text-strong first:mt-0',
  h5: 'mt-4 mb-1 font-semibold text-strong first:mt-0',
  h6: 'mt-4 mb-1 font-semibold text-strong first:mt-0',
  strong: 'font-semibold text-strong',
  em: 'italic',
  del: 'line-through',
  ul: 'my-3 list-disc pl-6 first:mt-0 last:mb-0',
  ol: 'my-3 list-decimal pl-6 first:mt-0 last:mb-0',
  li: 'my-1 pl-1 [&>p]:my-0',
  blockquote: 'my-4 border-l-2 border-default pl-4 text-muted first:mt-0 last:mb-0',
  th: 'border-b border-subtle bg-subtle px-3 py-2 text-left font-semibold whitespace-nowrap text-strong',
  td: 'border-b border-subtle px-3 py-2 whitespace-nowrap',
  code: 'rounded-sm bg-muted px-1 py-0.5 font-mono text-sm',
}

function MarkdownLink({ children, href }: { children?: ReactNode; href?: string }) {
  const viewLink = useContext(ViewLinkContext)
  const content = <LinkText value={true}><VisibleText>{children}</VisibleText></LinkText>
  const view = href?.match(VIEW_HREF)?.[1]
  if (view) return viewLink ? viewLink(view, content) : <span><VisibleText>{children}</VisibleText></span>
  return href ? (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer nofollow"
      referrerPolicy="no-referrer"
      className="text-accent underline underline-offset-2 hover:text-strong"
    >
      {content}
    </a>
  ) : (
    <span><VisibleText>{children}</VisibleText></span>
  )
}

/** Text with privacy values highlighted; in X-ray, hovering or focusing one highlights its pair. */
export function PrivacyText({ text, bindings = [], model = false, selected, onSelect }: PrivacyProps & {
  text: string
  model?: boolean
}) {
  const inLink = useContext(LinkText)
  const values = bindings
    .flatMap((binding) => (model ? [binding.token] : [binding.token, binding.value]))
    .filter(Boolean)
    .sort((first, second) => second.length - first.length)
  if (!values.length) return <>{text}</>
  const pattern = new RegExp(
    `(${[...new Set(values)].map((value) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`,
    'g',
  )
  return (
    <>
      {text.split(pattern).map((part, index) => {
        const binding = bindings.find((item) => item.token === part || (!model && item.value === part))
        if (!binding) return part
        const value = model ? part : binding.value
        return onSelect && !inLink ? (
          <button
            type="button"
            key={index}
            className={tokenClassName}
            data-token={binding.token}
            aria-pressed={selected === binding.token}
            aria-label={`Highlight ${binding.token}`}
            title={binding.token}
            onClick={() => onSelect(binding.token)}
            onMouseEnter={() => onSelect(binding.token)}
            onFocus={() => onSelect(binding.token)}
          >
            {value}
          </button>
        ) : (
          <mark
            key={index}
            className={tokenClassName}
            data-token={binding.token}
            data-selected={selected === binding.token}
            title={binding.token}
            onMouseEnter={() => onSelect?.(binding.token)}
          >
            {value}
          </mark>
        )
      })}
    </>
  )
}

function safeLink(destination: string, bindings: PrivacyBinding[]) {
  let decoded = destination
  try {
    for (let attempt = 0; attempt < 4; attempt += 1) {
      const next = decodeURIComponent(decoded)
      if (next === decoded) break
      decoded = next
    }
    const comparable = decoded.replace(/\+/g, ' ').normalize('NFKC').toLowerCase()
    const hasControls = [...decoded].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)
    if (/%[\da-f]{2}/i.test(decoded) || hasControls || decoded.includes('\\') || /\[[a-z][a-z0-9]*_/.test(comparable)) return
    if (bindings.some(({ token, value }) => [token, value].some((part) =>
      part && comparable.includes(part.normalize('NFKC').toLowerCase()),
    ))) return
    const url = new URL(destination)
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return
    const host = url.hostname.toLowerCase().replace(/\.$/, '')
    if (host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local') ||
      !host.includes('.') || /^(?:0\.|10\.|127\.|169\.254\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(host) ||
      (typeof window !== 'undefined' && host === window.location.hostname.toLowerCase().replace(/\.$/, ''))) return
    return url.href
  } catch {
    return
  }
}

function VisibleText({ children }: { children?: ReactNode }) {
  const privacy = useContext(PrivacyContext)
  return <>{Children.map(children, (child) => typeof child === 'string'
    ? <PrivacyText text={child} {...privacy} /> : child)}</>
}

function TextElement({ node, children, className }: ExtraProps & { children?: ReactNode; className?: string }) {
  const tag = node?.tagName ?? 'span'
  return createElement(tag, { className: cn(proseClassNames[tag], className) }, <VisibleText>{children}</VisibleText>)
}

const components: Components = {
  p: TextElement, h1: TextElement, h2: TextElement, h3: TextElement,
  h4: TextElement, h5: TextElement, h6: TextElement, strong: TextElement,
  em: TextElement, del: TextElement, ul: TextElement, ol: TextElement, li: TextElement,
  blockquote: TextElement, th: TextElement, td: TextElement, code: TextElement,
  pre: ({ children }) => (
    <pre
      tabIndex={0}
      aria-label="Code block"
      className="my-4 max-h-96 overflow-auto rounded-md border border-subtle bg-subtle p-3 font-mono text-sm leading-normal whitespace-pre first:mt-0 last:mb-0 [&_code]:bg-transparent [&_code]:p-0"
    >
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div
      role="region"
      aria-label="Markdown table"
      tabIndex={0}
      data-testid="markdown-table"
      className="my-4 max-w-full overflow-auto rounded-md border border-subtle first:mt-0 last:mb-0"
    >
      <table className="w-max min-w-full border-collapse text-sm [&_tr:last-child_td]:border-b-0">{children}</table>
    </div>
  ),
  a: MarkdownLink,
  img: ({ alt }) => <span><VisibleText>{alt ?? ''}</VisibleText></span>,
}

export function TranscriptText({
  text,
  role,
  size = 'md',
  streaming = false,
  bindings = [],
  selected,
  onSelect,
  viewLink,
}: PrivacyProps & {
  text: string
  role: 'assistant' | 'user'
  size?: 'sm' | 'md'
  streaming?: boolean
  viewLink?: ViewLink
}) {
  const sizeClassName = size === 'sm' ? 'text-sm' : 'text-md'
  if (role === 'user') {
    return (
      <p data-testid="message-text" className={cn('whitespace-pre-wrap wrap-anywhere', sizeClassName)}>
        <PrivacyText text={text} bindings={bindings} selected={selected} onSelect={onSelect} />
      </p>
    )
  }
  return (
    <PrivacyContext value={{ bindings, selected, onSelect }}>
      <ViewLinkContext value={viewLink}>
        <div
          data-testid="message-text"
          className={cn('min-w-0 wrap-anywhere', sizeClassName, streaming && '[&>p:nth-last-child(2)]:inline')}
        >
          <Markdown
            remarkPlugins={[remarkGfm]}
            components={components}
            urlTransform={(value, key) =>
              key !== 'href' ? undefined : VIEW_HREF.test(value) ? value : safeLink(value, bindings)
            }
          >
            {text}
          </Markdown>
          {streaming && (
            <span
              data-testid="stream-cursor"
              aria-hidden
              className="ml-0.5 inline-block h-4 w-0.5 translate-y-0.5 animate-pulse bg-accent"
            />
          )}
        </div>
      </ViewLinkContext>
    </PrivacyContext>
  )
}

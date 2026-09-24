import { Children, createContext, createElement, useContext } from 'react'
import type { ReactNode } from 'react'
import Markdown from 'react-markdown'
import type { Components, ExtraProps } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { PrivacyBinding } from '../lib/api'

const LinkText = createContext(false)

type PrivacyProps = {
  bindings?: PrivacyBinding[]
  selected?: string | null
  onSelect?: (token: string) => void
}

const PrivacyContext = createContext<PrivacyProps>({})

export function PrivacyText({ text, bindings = [], model = false, selected, onSelect }: PrivacyProps & {
  text: string
  model?: boolean
}) {
  const inLink = useContext(LinkText)
  const values = bindings.flatMap((binding) => model
    ? [binding.token] : [binding.token, binding.value]).filter(Boolean)
    .sort((first, second) => second.length - first.length)
  if (!values.length) return <>{text}</>
  const pattern = new RegExp(`(${[...new Set(values)].map((value) =>
    value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
  ).join('|')})`, 'g')
  return <>{text.split(pattern).map((part, index) => {
    const binding = bindings.find((item) => item.token === part || (!model && item.value === part))
    if (!binding) return part
    const value = model ? part : binding.value
    return onSelect && !inLink ? <button
      type="button" key={index} className="privacy-token"
      data-token={binding.token} aria-pressed={selected === binding.token}
      aria-label={`Highlight ${binding.token}`} title={binding.token}
      onClick={() => onSelect(binding.token)} onMouseEnter={() => onSelect(binding.token)}
      onFocus={() => onSelect(binding.token)}
    >{value}</button> : <mark key={index} className="privacy-token" data-token={binding.token}
      data-selected={selected === binding.token} title={binding.token}
      onMouseEnter={() => onSelect?.(binding.token)}>{value}</mark>
  })}</>
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
  return createElement(node?.tagName ?? 'span', { className }, <VisibleText>{children}</VisibleText>)
}

const components: Components = {
  p: TextElement, h1: TextElement, h2: TextElement, h3: TextElement,
  h4: TextElement, h5: TextElement, h6: TextElement, strong: TextElement,
  em: TextElement, del: TextElement, li: TextElement, blockquote: TextElement,
  th: TextElement, td: TextElement, code: TextElement,
  pre: ({ children }) => <pre tabIndex={0} aria-label="Code block">{children}</pre>,
  table: ({ children }) => <div className="markdown-table" role="region" aria-label="Markdown table" tabIndex={0}>
    <table>{children}</table>
  </div>,
  a: ({ children, href }) => href
    ? <a href={href} target="_blank" rel="noopener noreferrer nofollow" referrerPolicy="no-referrer">
      <LinkText value={true}><VisibleText>{children}</VisibleText></LinkText>
    </a>
    : <span><VisibleText>{children}</VisibleText></span>,
  img: ({ alt }) => <span><VisibleText>{alt ?? ''}</VisibleText></span>,
}

export function TranscriptText({ text, role, streaming = false, bindings = [], selected, onSelect }: PrivacyProps & {
  text: string
  role: 'assistant' | 'user'
  streaming?: boolean
}) {
  if (role === 'user') return <p className="message-text" data-testid="message-text">
    <PrivacyText text={text} bindings={bindings} selected={selected} onSelect={onSelect} />
  </p>

  return <PrivacyContext value={{ bindings, selected, onSelect }}><div className="message-text assistant-markdown" data-testid="message-text">
    <Markdown remarkPlugins={[remarkGfm]} components={components}
      urlTransform={(value, key) => key === 'href' ? safeLink(value, bindings) : undefined}
    >{text}</Markdown>
    {streaming && <span className="stream-cursor" aria-hidden="true" />}
  </div></PrivacyContext>
}
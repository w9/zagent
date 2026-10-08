import type { StepState } from './events'

/** The citation format the agent prompt asks for: `[document@version:Lstart-Lend]`. */
const CITATION = /\[([a-z0-9]+(?:-[a-z0-9]+)*)@([A-Za-z0-9._-]+):L([0-9]+)(?:-L([0-9]+))?\]/g
const WHOLE_CITATION = /^\[?\[([a-z0-9]+(?:-[a-z0-9]+)*)@([A-Za-z0-9._-]+):L([0-9]+)(?:-L([0-9]+))?\]\]?$/
// Models sometimes put the citation in the link's address instead of its text.
const CITATION_URL = /^\[?([a-z0-9]+(?:-[a-z0-9]+)*)@([A-Za-z0-9._-]+):L([0-9]+)(?:-L([0-9]+))?\]?$/
const CITE_HREF = /^cite:([a-z0-9]+(?:-[a-z0-9]+)*)@([A-Za-z0-9._-]+):L([0-9]+)-L([0-9]+)$/
const QUOTATION = /\u201c([^\u201c\u201d]{20,}?)\u201d|(?:^|(?<=[\s(:]))"([^"\n]{20,}?)"/g
const NUMBERED_LINE = /^L([0-9]+): ?(.*)$/
const QUOTE_LIMIT = 300
const SOURCES: Record<string, string> = {
  qms: 'QMS', wiki: 'Wiki', ticketing: 'Service desk', reference: 'Reference', wikipedia: 'Library',
}

export type Citation = { document: string; version: string; start: number; end: number; quote?: string }

/** A read_document result as the client received it, in its display representation. */
export type CitedRead = {
  document: string
  version: string
  snapshot: string
  title: string
  source: string
  status?: string
  start: number
  end: number
  lines: { number: number; text: string }[]
}

export function isCitationHref(href: string) {
  return CITE_HREF.test(href)
}

export function parseCitationHref(href: string, quote?: string | null): Citation | undefined {
  const match = href.match(CITE_HREF)
  if (!match) return
  return { document: match[1], version: match[2], start: Number(match[3]), end: Number(match[4]), quote: quote || undefined }
}

/** Every read_document result in the conversation, earliest first. */
export function readResults(steps: StepState[]): CitedRead[] {
  return [...steps].sort((first, second) => first.seq - second.seq).flatMap((step) =>
    (step.tools ?? []).flatMap(({ name, result }) => {
      if (name !== 'read_document' || !result) return []
      const { document, version, snapshot, title, source, status, start_line, end_line, text } = result
      if (typeof document !== 'string' || typeof version !== 'string' || typeof snapshot !== 'string' ||
        typeof start_line !== 'number' || typeof end_line !== 'number' || typeof text !== 'string') return []
      const lines = text.split('\n').flatMap((line) => {
        const match = line.match(NUMBERED_LINE)
        return match ? [{ number: Number(match[1]), text: match[2] }] : []
      })
      return [{
        document, version, snapshot, lines, start: start_line, end: end_line,
        title: typeof title === 'string' ? title : document,
        source: typeof source === 'string' ? source : '',
        status: typeof status === 'string' ? status : undefined,
      }]
    }),
  )
}

/** The earliest read that covers every cited line, if the assistant read them at all. */
export function citedRead(reads: CitedRead[], citation: Citation) {
  return reads.find((read) =>
    read.document === citation.document && read.version === citation.version &&
    read.start <= citation.start && citation.end <= read.end,
  )
}

export function citationLabel(citation: Citation, read?: CitedRead) {
  const { document, version } = citation
  const controlled = document.match(/^(.+)-v([0-9]+)$/)
  if (controlled && controlled[2] === version) return `${controlled[1].toUpperCase()} v${version}`
  if (document.startsWith('wiki-')) return `Wiki ${document.slice(5)}`
  if (/^[a-z]+-[0-9]+$/.test(document)) return document.toUpperCase()
  return read?.title ?? `${document}@${version}`
}

export function lineLabel({ start, end }: Citation) {
  return start === end ? `L${start}` : `L${start}\u2013${end}`
}

export function sourceName(source: string) {
  return SOURCES[source] ?? 'Knowledge base'
}

/** The last quotation in text, which is what a citation right after it supports. */
function lastQuotation(text: string) {
  const quotes = [...text.matchAll(QUOTATION)].map((match) => (match[1] ?? match[2]).trim())
  const quote = quotes.at(-1)
  return quote ? quote.slice(0, QUOTE_LIMIT) : undefined
}

type MarkdownNode = { type: string; value?: string; url?: string; title?: string | null; children?: MarkdownNode[] }

function plainText(node: MarkdownNode): string {
  return node.value ?? (node.children ?? []).map(plainText).join('')
}

function citationUrl(url = '') {
  try {
    return decodeURIComponent(url).match(CITATION_URL)
  } catch {
    return null
  }
}

function citationNode(match: RegExpMatchArray, quote?: string): MarkdownNode {
  const [raw, document, version, start, end] = match
  return {
    type: 'link',
    url: `cite:${document}@${version}:L${start}-L${end ?? start}`,
    title: quote ?? null,
    children: [{ type: 'text', value: raw }],
  }
}

function rewrite(parent: MarkdownNode) {
  if (!parent.children) return
  const merged: MarkdownNode[] = []
  for (const child of parent.children) {
    const last = merged.at(-1)
    if (child.type === 'text' && last?.type === 'text') merged[merged.length - 1] = { ...last, value: `${last.value}${child.value}` }
    else merged.push(child)
  }
  const children: MarkdownNode[] = []
  let before = ''
  for (const child of merged) {
    const whole = child.type === 'link' ? plainText(child).match(WHOLE_CITATION) : null
    const target = child.type === 'link' && !whole ? citationUrl(child.url) : null
    if (whole) {
      children.push(citationNode(whole, lastQuotation(before)))
      before = ''
    } else if (target) {
      children.push(...(child.children ?? []))
      children.push(citationNode(target, lastQuotation(before + plainText(child))))
      before = ''
    } else if (child.type === 'text') {
      const text = child.value ?? ''
      let offset = 0
      for (const match of text.matchAll(CITATION)) {
        const preceding = text.slice(offset, match.index)
        if (preceding) children.push({ type: 'text', value: preceding })
        children.push(citationNode(match, lastQuotation(before + preceding)))
        before = ''
        offset = match.index + match[0].length
      }
      const rest = text.slice(offset)
      if (rest) children.push({ type: 'text', value: rest })
      before += rest
    } else {
      if (!['link', 'linkReference', 'inlineCode', 'code', 'html'].includes(child.type)) rewrite(child)
      children.push(child)
      before += plainText(child)
    }
  }
  parent.children = children
}

/** A remark plugin that turns citations into `cite:` links carrying the quotation before them. */
export function remarkCitations() {
  return (tree: MarkdownNode) => rewrite(tree)
}

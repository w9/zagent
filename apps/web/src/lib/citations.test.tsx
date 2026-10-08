import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CitationChip } from '../components/chat/citation-chip'
import { TranscriptText } from '../components/chat/transcript-text'
import { bindings, cited, citedSteps } from '../components/fixtures'
import { citationLabel, citedRead, lineLabel, readResults } from './citations'
import type { Citation } from './citations'
import type { StepState } from './events'

const goldens = import.meta.glob('../../../../evals/goldens/*.json', { eager: true, import: 'default' }) as
  Record<string, { messages?: { role: string; text: string }[]; steps?: StepState[] }>

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

function citations(text: string) {
  const found: Citation[] = []
  render(<TranscriptText role="assistant" text={text} citationLink={(citation) => {
    found.push(citation)
    return <button type="button" data-testid="chip">{citation.document}</button>
  }} />)
  return found
}

describe('citations', () => {
  it('finds every citation, including ones wrapped in a link, with the quotation before it', () => {
    const found = citations(cited.messages[1].text)
    expect(found).toEqual([
      { document: 'sop-qc-001-v3', version: '3', start: 9, end: 10, quote: 'Tumor libraries intended for somatic calling require a mean coverage of at least 40x.' },
      { document: 'sop-qc-001-v3', version: '3', start: 8, end: 8, quote: "a selected library's coverage is below the confirmed minimum coverage" },
      { document: 'inc-0142', version: '2025-12-04', start: 7, end: 8, quote: 'somatic-snv failed with genotype_concordance_failed for patient NGC-0041872.' },
      { document: 'sop-var-001-v2', version: '2', start: 6, end: 8, quote: undefined },
    ])
    expect(screen.queryByRole('link')).toBeNull()
  })

  it('keeps the text of a link whose address is a citation and puts the chip after it', () => {
    const text = 'VCF stands for **Variant Call Format**. [Wikipedia contributors describe VCF as \u201ca standard text file format used in bioinformatics for storing gene sequence or DNA sequence variations.\u201d](wp-variant-call-format@1373132868:L3) See also [the spec](<[wp-variant-call-format@1373132868:L26-L28]>).'
    const found = citations(text)
    expect(found).toEqual([
      { document: 'wp-variant-call-format', version: '1373132868', start: 3, end: 3, quote: 'a standard text file format used in bioinformatics for storing gene sequence or DNA sequence variations.' },
      { document: 'wp-variant-call-format', version: '1373132868', start: 26, end: 28, quote: undefined },
    ])
    expect(screen.getByTestId('message-text').textContent).toBe(
      'VCF stands for Variant Call Format. Wikipedia contributors describe VCF as \u201ca standard text file format used in bioinformatics for storing gene sequence or DNA sequence variations.\u201dwp-variant-call-format See also the specwp-variant-call-format.',
    )
    expect(screen.queryByRole('link')).toBeNull()
    cleanup()
    expect(citations('A [plain link](https://docs.example.org/vcf) and [a relative one](wp-variant-call-format).')).toEqual([])
  })

  it('renders every recorded citation as a chip backed by a read from its own conversation', () => {
    let total = 0
    for (const [path, golden] of Object.entries(goldens)) {
      const reads = readResults(golden.steps ?? [])
      for (const message of (golden.messages ?? []).filter((item) => item.role === 'assistant')) {
        const written = message.text.match(/\[[a-z0-9]+(?:-[a-z0-9]+)*@[A-Za-z0-9._-]+:L[0-9]+(?:-L[0-9]+)?\]/g) ?? []
        const found = citations(message.text)
        cleanup()
        expect(found.length, path).toBe(written.length)
        for (const citation of found) expect(citedRead(reads, citation), `${path} ${citation.document}`).toBeDefined()
        total += found.length
      }
    }
    expect(total).toBeGreaterThanOrEqual(14)
  })

  it('leaves code, plain links and malformed citations alone, and stays plain text without a renderer', () => {
    const text = 'See `[sop-qc-001-v3@3:L2]`, [the SOP](https://docs.example.org/sop) and [SOP-QC-001@3:L2] or [sop-qc-001-v3@3:2].'
    expect(citations(text)).toEqual([])
    cleanup()
    const { container } = render(<TranscriptText role="assistant" text="Covered [sop-qc-001-v3@3:L2]." />)
    expect(container.textContent).toBe('Covered [sop-qc-001-v3@3:L2].')
    expect(container.querySelector('a')).toBeNull()
  })

  it('matches the earliest read that covers every cited line and labels by document number', () => {
    const reads = readResults(citedSteps)
    const swap = { document: 'inc-0142', version: '2025-12-04', start: 7, end: 8 }
    expect(citedRead(reads, swap)?.title).toBe('Genotype concordance failure from a tumor/normal swap')
    expect(citedRead(reads, { ...swap, end: 9 })).toBeUndefined()
    expect(citedRead(reads, { ...swap, version: '2025-12-05' })).toBeUndefined()
    expect(citationLabel({ document: 'sop-qc-001-v3', version: '3', start: 9, end: 10 })).toBe('SOP-QC-001 v3')
    expect(citationLabel(swap)).toBe('INC-0142')
    expect(citationLabel({ document: 'wiki-40152', version: '18', start: 1, end: 1 })).toBe('Wiki 40152')
    expect(citationLabel({ document: 'ref-glossary', version: '2026-09', start: 1, end: 1 })).toBe('ref-glossary@2026-09')
    expect(lineLabel(swap)).toBe('L7\u20138')
    expect(lineLabel({ ...swap, end: 7 })).toBe('L7')
  })

  it('previews the cited lines with privacy values and opens the citation on click', async () => {
    const onOpen = vi.fn()
    const citation = { document: 'inc-0142', version: '2025-12-04', start: 7, end: 8 }
    const read = citedRead(readResults(citedSteps), citation)
    render(<CitationChip citation={citation} read={read} bindings={bindings} onOpen={onOpen} />)
    const chip = screen.getByRole('button', { name: /INC-0142 · L7–8/ })
    expect(chip.dataset.verified).toBe('true')
    await userEvent.hover(chip)
    const preview = await screen.findByRole('tooltip')
    expect(preview.textContent).toContain('The manifest listed the tumor and normal tubes the other way round.')
    expect(preview.textContent).not.toContain('Links: SOP-IDENTITY-001')
    expect(preview.querySelector('[data-token="[PT_1]"]')?.textContent).toBe('NGC-0041872')
    await userEvent.click(chip)
    expect(onOpen).toHaveBeenCalledWith(citation, read)
  })

  it('marks a citation with no matching read as unverified', async () => {
    render(<CitationChip citation={{ document: 'sop-var-001-v2', version: '2', start: 6, end: 8 }} onOpen={() => {}} />)
    const chip = screen.getByRole('button', { name: 'SOP-VAR-001 v2 · L6–8, unverified' })
    expect(chip.dataset.verified).toBe('false')
    await userEvent.hover(chip)
    expect((await screen.findByRole('tooltip')).textContent).toContain('Not in what the assistant read')
  })
})

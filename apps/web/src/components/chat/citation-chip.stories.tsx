import type { Meta, StoryObj } from '@storybook/react-vite'
import { readResults } from '../../lib/citations'
import type { CitedRead } from '../../lib/citations'
import { bindings, citedSteps } from '../fixtures'
import { CitationChip } from './citation-chip'

const [coverage, incident] = readResults(citedSteps)
const glossary: CitedRead = {
  document: 'ref-glossary',
  version: '2026-09',
  snapshot: coverage.snapshot,
  title: 'Glossary of laboratory, sequencing and controlled-document terms used across the genomics core',
  source: 'reference',
  start: 140,
  end: 141,
  lines: [
    { number: 140, text: '| min_coverage | The confirmed minimum mean coverage a library must reach before analysis. |' },
    { number: 141, text: '| observed_coverage | The mean coverage measured by readqc for a library. |' },
  ],
}
const longRead: CitedRead = {
  ...coverage,
  start: 1,
  end: 16,
  lines: Array.from({ length: 16 }, (_, index) => ({
    number: index + 1,
    text: index === 9 ? coverage.lines[2].text : `Step ${index + 1} of the readqc review records the library, its observed coverage and the confirmed threshold.`,
  })),
}

const meta = {
  title: 'Chat/Citation chip',
  component: CitationChip,
  args: {
    citation: { document: 'sop-qc-001-v3', version: '3', start: 9, end: 10 },
    read: coverage,
    bindings,
    onOpen: () => {},
  },
  decorators: [
    (Story, { parameters }) => (
      <p className={parameters.narrow ? 'w-48 pt-48 text-md text-default' : 'max-w-prose pt-48 text-md text-default'}>
        The SOP sets a higher bar for tumor libraries <Story /> than for normal ones.
      </p>
    ),
  ],
} satisfies Meta<typeof CitationChip>
export default meta
type Story = StoryObj<typeof meta>

export const Verified: Story = {}
export const Preview: Story = { args: { open: true } }
export const SingleLine: Story = { args: { citation: { document: 'sop-qc-001-v3', version: '3', start: 8, end: 8 } } }
export const PrivacyValues: Story = {
  args: { citation: { document: 'inc-0142', version: '2025-12-04', start: 7, end: 8 }, read: incident, open: true },
}
export const LongTitle: Story = {
  args: { citation: { document: 'ref-glossary', version: '2026-09', start: 140, end: 141 }, read: glossary, open: true },
}
export const ManyLines: Story = {
  args: { citation: { document: 'sop-qc-001-v3', version: '3', start: 1, end: 16 }, read: longRead, open: true },
}
export const Unverified: Story = {
  args: { citation: { document: 'sop-var-001-v2', version: '2', start: 6, end: 8 }, read: undefined, open: true },
}
export const NarrowBox: Story = {
  args: { citation: { document: 'ref-glossary', version: '2026-09', start: 140, end: 141 }, read: glossary },
  parameters: { narrow: true },
}

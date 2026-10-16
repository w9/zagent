// Synthetic data for stories. Every identifier here is invented.
import catalogJson from '../../../../services/agent/zagent/catalog.json'
import type { Persona, PrivacyBinding, Session, XrayData } from '../lib/api'
import type { DraftState, Projection, StepState } from '../lib/events'
import type { PushedView, TableData } from '../lib/views'
import type { HandleResolver } from './surface/views/table.view'
import type { CatalogApp } from './surface/views/draft_form.view'

export const catalog = catalogJson as unknown as CatalogApp[]

export const personas: Persona[] = [
  { id: 'lab-technologist', name: 'Tamsin Rook', title: 'Lab technologist', roles: ['lab-technologist'], description: 'Published documents for this site' },
  { id: 'analyst', name: 'Ilse Marrow', title: 'Analyst', roles: ['analyst'], description: 'Published documents for this site' },
  {
    id: 'qa-officer',
    name: 'Odile Fenn',
    title: 'QA officer',
    roles: ['qa-officer'],
    description: 'Also draft procedures, QC review notes and open change proposals',
  },
  {
    id: 'lab-director',
    name: 'Caspar Wend',
    title: 'Lab director',
    roles: ['lab-director'],
    description: 'Also draft procedures, QC review notes and administration pages',
  },
]

export const sessions: Session[] = [
  { id: 'session-1', seq: 42, created_at: '2026-10-01T14:03:00Z', title: 'Intake review for the northgate cohort', title_source: 'automatic', persona: 'qa-officer' },
  { id: 'session-2', seq: 18, created_at: '2026-09-30T09:41:00Z', title: 'Library QC follow-up', title_source: 'manual', persona: 'analyst' },
  {
    id: 'session-3',
    seq: 7,
    created_at: '2026-09-29T16:20:00Z',
    title: 'Somatic calling for SPC-northgate-001-1 against matched normal SPC-northgate-001-2',
    title_source: 'automatic',
    persona: 'analyst',
  },
  { id: 'session-4', seq: 0, created_at: '2026-09-28T11:05:00Z', title: 'New session', title_source: 'fallback', persona: 'lab-technologist' },
]

export const bindings: PrivacyBinding[] = [{ token: '[PT_1]', value: 'NGC-0041872', kind: 'PT' }]

const columns: TableData['columns'] = [
  { key: 'specimen_id', label: 'Specimen', type: 'string' },
  { key: 'tissue', label: 'Tissue', type: 'string' },
  { key: 'coverage', label: 'Coverage', type: 'number' },
  { key: 'qc_passed', label: 'QC passed', type: 'boolean' },
]
const rows: TableData['rows'] = [
  ['SPC-northgate-001-1', 'Tumour, left femur', 118.4, true],
  ['SPC-northgate-001-2', 'Blood, matched normal', 42.1, true],
  ['SPC-northgate-002-1', 'Tumour, posterior fossa', 96.7, false],
  ['SPC-northgate-003-1', 'Bone marrow aspirate', null, false],
  ['SPC-northgate-004-1', 'Tumour, adrenal', 131.9, true],
  ['SPC-northgate-005-1', 'Blood, matched normal', 38.5, true],
]

export const tableData: TableData = { columns, rows, row_count: 14 }
export const resolveHandle: HandleResolver = async () => tableData
export const pendingHandle: HandleResolver = () => new Promise(() => {})
export const failingHandle: HandleResolver = async () => {
  throw new Error('Handle query-0002 expired. Ask the agent to run the query again.')
}

export const tableView: PushedView = {
  id: 'view-0001',
  seq: 6,
  spec: { kind: 'table', version: 1, props: { title: 'Specimens received this week', columns, rows, row_count: 14 } },
}
export const chartView: PushedView = {
  id: 'view-0002',
  seq: 12,
  spec: {
    kind: 'chart',
    version: 1,
    props: {
      title: 'Library coverage by specimen',
      handle: 'query-0002',
      mark: 'bar',
      encoding: { x: { field: 'specimen_id', type: 'nominal' }, y: { field: 'coverage', type: 'quantitative' } },
    },
  },
}
export const handleTableView: PushedView = {
  id: 'view-0003',
  seq: 14,
  spec: { kind: 'table', version: 1, props: { title: 'Libraries for SPC-northgate-001-1', columns, handle: 'query-0003', row_count: 14 } },
}

const answer = `Six of the **14 specimens** received this week are shown in [Specimens received this week](view:view-0001).

- Two failed intake QC: \`SPC-northgate-002-1\` (low tumour content) and \`SPC-northgate-003-1\` (no library yet).
- Patient NGC-0041872 has both a tumour and a matched normal, so somatic calling can start.

| Status | Specimens |
| --- | --- |
| Passed | 4 |
| Failed | 2 |

> Counts come from the synthetic intake log, not from a sequencing run.`

export const steps: StepState[] = [
  {
    id: 'step-1',
    seq: 2,
    title: 'Agent step 1',
    detail: '',
    status: 'complete',
    tools: [{ call_id: 'call-1', name: 'find_specimens', arguments: '{"received_within":"7d","cohort":"northgate"}', result: { count: 14, handle: 'query-0001' } }],
  },
  {
    id: 'step-2',
    seq: 5,
    title: 'Agent step 2',
    detail: '',
    status: 'complete',
    tools: [{ call_id: 'call-2', name: 'push_view', arguments: '{"handle":"query-0001"}', result: { ok: true, view_id: 'view-0001', kind: 'table', title: 'Specimens received this week' } }],
  },
]

export const conversation: Projection = {
  session_id: 'session-1',
  seq: 42,
  messages: [
    { id: 'message-1', seq: 1, role: 'user', text: 'Which northgate specimens arrived this week, and did any fail intake QC?', status: 'complete' },
    { id: 'message-2', seq: 7, role: 'assistant', text: answer, status: 'complete' },
    { id: 'message-3', seq: 8, role: 'user', text: 'Book a courier to collect the failed samples tomorrow.', status: 'complete' },
    { id: 'message-4', seq: 11, role: 'user', text: 'Then chart library coverage for all of them.', status: 'complete' },
    { id: 'message-5', seq: 13, role: 'assistant', text: 'The coverage chart is on the working surface. `SPC-northgate-003-1` has no library, so it has no bar.', status: 'complete' },
  ],
  steps,
  refusals: [{
    id: 'refusal-1',
    seq: 9,
    code: 'out_of_domain',
    message: 'Courier booking is outside this workbench. I can list the specimens that need collection so you can book it in the logistics portal.',
  }],
  views: [tableView, chartView],
  conversation_turn: { id: 'turn-3', status: 'finished', error: null },
}

export const responding: Projection = {
  ...conversation,
  seq: 47,
  messages: [
    ...conversation.messages,
    { id: 'message-6', seq: 44, role: 'user', text: 'Which libraries does SPC-northgate-001-1 have?', status: 'complete' },
    { id: 'message-7', seq: 47, role: 'assistant', text: 'Checking the library index for', status: 'streaming' },
  ],
  steps: [
    ...steps,
    {
      id: 'step-3',
      seq: 45,
      title: 'Agent step 3',
      detail: '',
      status: 'running',
      tools: [{ call_id: 'call-3', name: 'find_libraries', arguments: '{"specimen":"SPC-northgate-001-1"}', result: null }],
    },
  ],
  conversation_turn: { id: 'turn-4', status: 'running', error: null },
}

export const failed: Projection = {
  ...conversation,
  seq: 46,
  messages: [
    ...conversation.messages,
    { id: 'message-6', seq: 44, role: 'user', text: 'Which libraries does SPC-northgate-001-1 have?', status: 'complete' },
    { id: 'message-7', seq: 46, role: 'assistant', text: 'Checking the library index', status: 'failed' },
  ],
  steps: [
    ...steps,
    {
      id: 'step-3',
      seq: 45,
      title: 'Agent step 3',
      detail: '',
      status: 'failed',
      tools: [{ call_id: 'call-3', name: 'find_libraries', arguments: '{"specimen":"SPC-northgate-001-1"}', result: { error: { code: 'timeout', message: 'Library index did not answer within 30s.' } } }],
    },
  ],
  conversation_turn: { id: 'turn-4', status: 'failed', error: 'The model request timed out. Send the message again to retry.' },
}

/** The latest turn ended in a refusal, so Retry stands alone under it. */
export const refused: Projection = {
  ...conversation,
  seq: 10,
  messages: conversation.messages.slice(0, 3),
  views: [tableView],
  conversation_turn: { id: 'turn-2', status: 'finished', error: null },
}

/** The latest turn failed before any output, so Retry sits under the question. */
export const unanswered: Projection = {
  ...conversation,
  seq: 45,
  messages: [
    ...conversation.messages,
    { id: 'message-6', seq: 44, role: 'user', text: 'Which libraries does SPC-northgate-001-1 have?', status: 'complete' },
  ],
  conversation_turn: { id: 'turn-4', status: 'failed', error: 'The model gateway is unavailable.' },
}

export const empty: Projection = {
  session_id: 'session-4',
  seq: 0,
  messages: [],
  views: [],
  steps: [],
  conversation_turn: null,
}

const snapshot = '30ce85e0e7f2b691da0dc9088fc1b28d3a2dc71c05d818cec912773a03bb620a'
const citedAnswer = `Tumor libraries need more coverage than normal ones. The SOP says “Tumor libraries intended for somatic calling require a mean coverage of at least 40x.” [sop-qc-001-v3@3:L9-L10]

- A run fails readqc when “a selected library's coverage is below the confirmed minimum coverage” [[sop-qc-001-v3@3:L8]](https://intranet.example/sop-qc-001).
- The last swap incident started when “somatic-snv failed with genotype_concordance_failed for patient NGC-0041872.” [inc-0142@2025-12-04:L7-L8]
- Variant review thresholds are listed separately [sop-var-001-v2@2:L6-L8].`

export const citedSteps: StepState[] = [
  {
    id: 'step-k1',
    seq: 2,
    title: 'Agent step 1',
    detail: '',
    status: 'complete',
    tools: [
      { call_id: 'call-k1', name: 'read_document', arguments: '{"document":"sop-qc-001-v3","start_line":8,"end_line":10}', result: {
        snapshot, document: 'sop-qc-001-v3', title: 'Read Quality and Low Purity Review', source: 'qms', doc_type: 'sop',
        version: '3', status: 'effective', start_line: 8, end_line: 10, truncated: false,
        text: "L8: Readqc fails when a selected library's coverage is below the confirmed minimum coverage.\nL9: Normal and germline libraries require a mean coverage of at least 30x.\nL10: Tumor libraries intended for somatic calling require a mean coverage of at least 40x.",
      } },
      { call_id: 'call-k2', name: 'read_document', arguments: '{"document":"inc-0142","start_line":5,"end_line":8}', result: {
        snapshot, document: 'inc-0142', title: 'Genotype concordance failure from a tumor/normal swap', source: 'ticketing',
        doc_type: 'incident', version: '2025-12-04', status: 'resolved', start_line: 5, end_line: 8, truncated: false,
        text: 'L5: Links: SOP-IDENTITY-001, SOP-DEV-001, SOP-ACC-001\nL6: ## Description\nL7: somatic-snv failed with genotype_concordance_failed for patient NGC-0041872.\nL8: The manifest listed the tumor and normal tubes the other way round.',
      } },
    ],
  },
]

export const cited: Projection = {
  session_id: 'session-5',
  seq: 6,
  messages: [
    { id: 'message-k1', seq: 1, role: 'user', text: 'What coverage do tumor libraries need, and what went wrong in the last sample swap?', status: 'complete' },
    { id: 'message-k2', seq: 5, role: 'assistant', text: citedAnswer, status: 'complete' },
  ],
  steps: citedSteps,
  views: [],
  conversation_turn: { id: 'turn-k1', status: 'finished', error: null },
}

export const draft: DraftState = {
  draft_id: 'draft-0001',
  view_id: 'view-0004',
  app_id: 'somatic-snv',
  specimen_handle: 'query-0001',
  parameters: { min_vaf: 0.05, min_depth: 20 },
  version: 2,
  content_hash: 'a'.repeat(64),
  status: 'editing',
  validation: [],
  job_id: null,
}

export const xray: XrayData = {
  display: {
    ...empty,
    session_id: 'session-1',
    messages: [
      { id: 'message-1', seq: 1, role: 'user', text: 'Find specimens for NGC-0041872', status: 'complete' },
      { id: 'message-2', seq: 4, role: 'assistant', text: 'NGC-0041872 has **two specimens**: a tumour and a matched normal.', status: 'complete' },
    ],
    refusals: [{ id: 'refusal-1', seq: 6, code: 'out_of_domain', message: 'Courier booking is outside this workbench.' }],
  },
  model: {
    ...empty,
    session_id: 'session-1',
    messages: [
      { id: 'message-1', seq: 1, role: 'user', text: 'Find specimens for [PT_1]', status: 'complete' },
      { id: 'message-2', seq: 4, role: 'assistant', text: '[PT_1] has **two specimens**: a tumour and a matched normal.', status: 'complete' },
    ],
  },
  bindings,
  executions: [{ conversation_turn_id: 'turn-1', tool: 'find_specimens', arguments: { patient: 'NGC-0041872', received_within: '30d' } }],
  requests: [
    {
      request_id: 'request-1',
      conversation_turn_id: 'turn-1',
      request: { model: 'openai/gpt-6-luna', messages: [{ role: 'system', content: 'Classify whether the request is within the clinical genomics workbench scope.' }, { role: 'user', content: 'Find specimens for [PT_1]' }] },
      audit: { purpose: 'scope_guard', mode: 'replay', request_hash: '9f2c1e7a4b0d3e8f6a5c2b1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f', outcome: 'completed' },
    },
    {
      request_id: 'request-2',
      conversation_turn_id: 'turn-1',
      request: {
        model: 'openai/gpt-6-luna',
        messages: [
          { role: 'system', content: 'You are the Zagent clinical genomics agent. Use tools for every record.' },
          { role: 'user', content: 'Find specimens for [PT_1]' },
          { role: 'assistant', content: null, tool_calls: [{ id: 'call-1', function: { name: 'find_specimens', arguments: '{"patient":"[PT_1]"}' } }] },
          { role: 'tool', tool_call_id: 'call-1', content: '{"count":2,"handle":"query-0001"}' },
        ],
        tools: [{ type: 'function', function: { name: 'find_specimens' } }],
      },
      audit: { purpose: 'agent', mode: 'replay', request_hash: '1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b', outcome: 'completed' },
    },
  ],
}

// A start time in the future pins the job's elapsed time at 0m 0s, so screenshots are stable.
const started = '2099-01-01T00:00:00Z'
export const jobs = {
  jobs: [
    {
      job_id: 'job-0001',
      app_id: 'read-qc',
      title: 'Read quality control',
      status: 'running',
      progress: 0.62,
      detail: 'Trimming adapters for LIB-northgate-001-1 (lane 2 of 3).',
      attempt: 1,
      log_seq: 5,
      started_at: started,
      finished_at: null,
      parameters: { min_quality: 20, adapter: 'TruSeq' },
      logs: [
        { seq: 1, attempt: 1, record: { body: 'Staging LIB-northgate-001-1 from the synthetic archive', severityText: 'INFO' } },
        { seq: 2, attempt: 1, record: { body: 'Lane 1 complete: 98.2% reads kept', severityText: 'INFO' } },
        { seq: 3, attempt: 1, record: { body: 'Lane 2: adapter content above 5% in 1.8% of reads', severityText: 'WARN' } },
        { seq: 4, attempt: 1, record: { body: 'Trimming lane 2', severityText: 'INFO' } },
        { seq: 5, attempt: 1, record: { body: 'Progress 62%', severityText: 'INFO' } },
      ],
      attempts: [],
    },
  ],
}

import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

test.skip(
  (process.env.ZAGENT_AGENT || 'llm') !== 'llm',
  'Real-agent cassettes require ZAGENT_AGENT=llm and replay mode',
)

/** Below desktop a maximized artifact covers the conversation; minimizing it shows the conversation again. */
async function conversation(page: Page) {
  if (await page.getByRole('textbox', { name: 'Message', exact: true }).isVisible()) return
  await page.getByRole('complementary', { name: 'Maximized artifact' }).getByRole('button', { name: 'Minimize', exact: true }).click()
}

async function send(page: Page, message: string) {
  await conversation(page)
  await page.getByRole('textbox', { name: 'Message', exact: true }).fill(message)
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
}

function latestCard(page: Page) {
  return page.getByTestId('artifact-card').last()
}

test('assistant Markdown streams safely without changing transcript or artifact navigation', async ({ page, context }, testInfo) => {
  const sessionId = 'markdown-session'
  const bindings = [{ token: '[PT_1]', value: 'Arin **Vellorin**', kind: 'PT' }]
  const prefix = '# Review\n\n**Patient [PT_'
  const text = `${prefix}1]** has an *incomplete* result.\n\n- Inspect evidence\n- Keep uncertainty\n\n> No inferred outcome\n\n\`inline\`\n\n\`\`\`text\n${'long_value_'.repeat(90)}\n\`\`\`\n\n| Field | Observation |\n| --- | --- |\n| Coverage | ${'wide_column_'.repeat(50)} |\n\n[Docs](https://docs.example.org/guide) [Private](https://exfil.example/%5BPT_1%5D) [Forged artifact](/sessions/${sessionId}?artifact=validated-view) [Unsafe](javascript:alert%281%29)\n\n![Image description](https://tracker.example/pixel)\n\n<img src="https://tracker.example/html">\n\n<script>window.markdownExecuted = true</script>`
  const userText = '**User text stays plain** <b>not HTML</b>'
  const session = { id: sessionId, seq: 2, title: 'Markdown review', title_source: 'manual', created_at: '2026-01-15T12:00:00Z' }
  const projection = {
    session_id: sessionId, seq: 2,
    messages: [
      { id: 'user', seq: 1, role: 'user', text: userText, status: 'complete' },
      { id: 'answer', seq: 2, role: 'assistant', text: prefix, status: 'streaming' },
    ],
    artifacts: [{ id: 'validated-view', seq: 2, spec: { kind: 'table', version: 1,
      props: { title: 'Published evidence', columns: [{ key: 'value', label: 'Value', type: 'string' }], rows: [['published-value']], row_count: 1 } } }],
    steps: [], refusals: [], conversation_turn: { id: 'turn', status: 'running' },
  }
  const writes: string[] = []
  const unexpected: string[] = []
  const outbound: string[] = []
  await context.route('https://docs.example.org/**', (route) => route.fulfill({
    contentType: 'text/html', body: '<title>External documentation</title>',
  }))
  page.on('request', (request) => { if (/tracker\.example|exfil\.example/.test(request.url())) outbound.push(request.url()) })
  await page.route('**/api/**', async (route) => {
    const incoming = route.request()
    const url = new URL(incoming.url())
    if (incoming.method() !== 'GET') writes.push(url.pathname)
    let body: unknown
    if (url.pathname === '/api/sessions') body = [session]
    else if (url.pathname === '/api/health') body = { status: 'ok', mode: 'live' }
    else if (url.pathname === '/api/personas') body = { default: 'analyst', personas: [] }
    else if (url.pathname.endsWith('/snapshot')) {
      expect(url.searchParams.get('representation')).toBe('model')
      body = projection
    } else if (url.pathname.endsWith('/bindings')) body = bindings
    else if (url.pathname.endsWith('/xray')) body = {
      display: projection, model: projection, bindings, executions: [],
      requests: [{ request_id: 'request', conversation_turn_id: 'turn',
        request: { model: 'fixture', messages: [{ role: 'assistant', content: text }] },
        audit: { purpose: 'agent', mode: 'replay', request_hash: 'unchanged', outcome: 'completed' } }],
    }
    else { unexpected.push(url.pathname); body = {} }
    await route.fulfill({ json: body })
  })
  await page.addInitScript(() => {
    const sources: EventTarget[] = []
    Object.assign(window, { markdownSources: sources })
    window.EventSource = class extends EventTarget {
      onopen: (() => void) | null = null
      onerror: (() => void) | null = null
      constructor() { super(); sources.push(this); queueMicrotask(() => this.onopen?.()) }
      close() { sources.splice(sources.indexOf(this), 1) }
    } as unknown as typeof EventSource
  })
  await page.goto(`/sessions/${sessionId}`)
  const answer = page.getByTestId('assistant-message').getByTestId('message-text')
  await expect(answer.getByRole('heading', { name: 'Review' })).toBeVisible()
  await expect(answer).toContainText('Patient [PT_')
  await expect(page.getByTestId('user-message').getByTestId('message-text')).toHaveText(userText)
  const events = [
    { type: 'text_delta', payload: { message_id: 'answer', text: text.slice(prefix.length) } },
    { type: 'message_done', payload: { message_id: 'answer' } },
    { type: 'conversation_turn_finished', payload: {} },
  ].map((event, index) => ({ ...event, schema_version: 3, session_id: sessionId,
    conversation_turn_id: 'turn', created_at: session.created_at, seq: index + 3 }))
  await page.evaluate((entries) => {
    const source = (window as unknown as { markdownSources: EventTarget[] }).markdownSources.at(-1)!
    for (const entry of entries) source.dispatchEvent(new MessageEvent('log', {
      data: JSON.stringify(entry), lastEventId: String(entry.seq),
    }))
  }, events)
  projection.messages[1].text = text
  projection.messages[1].status = 'complete'
  projection.conversation_turn.status = 'finished'
  projection.seq = 5
  await expect(answer.locator('strong')).toHaveText('Patient Arin **Vellorin**')
  await expect(answer.locator('script,img,iframe,button')).toHaveCount(0)
  await expect(answer.getByRole('link')).toHaveCount(1)
  await expect(answer.getByRole('link')).toHaveAttribute('rel', 'noopener noreferrer nofollow')
  const transcriptUrl = page.url()
  const popupReady = page.waitForEvent('popup')
  await answer.getByRole('link', { name: 'Docs', exact: true }).click()
  const popup = await popupReady
  await popup.waitForLoadState()
  expect(await popup.evaluate(() => ({ opener: window.opener, referrer: document.referrer })))
    .toEqual({ opener: null, referrer: '' })
  await popup.close()
  expect(page.url()).toBe(transcriptUrl)
  const completed = await answer.innerHTML()
  const viewports = testInfo.project.name === 'mobile'
    ? [{ width: 390, height: 844 }, { width: 320, height: 568 }]
    : [{ width: 1440, height: 960 }]
  for (const viewport of viewports) {
    await page.setViewportSize(viewport)
    await expect.poll(() => answer.evaluate((element) => {
      const regions = [...element.querySelectorAll('pre,[data-testid="markdown-table"]')]
      return document.documentElement.scrollWidth <= innerWidth && regions.every((region) => {
        const bounds = region.getBoundingClientRect()
        return bounds.width > 0 && bounds.left >= 0 && bounds.right <= innerWidth + 1
          && region.scrollWidth > region.clientWidth
      })
    })).toBe(true)
    await answer.locator('pre').scrollIntoViewIfNeeded()
    await page.screenshot({ path: testInfo.outputPath(`markdown-${viewport.width}.png`), animations: 'disabled' })
  }
  await page.reload()
  await expect(answer).toContainText('Arin **Vellorin**')
  expect(await answer.innerHTML()).toBe(completed)
  await page.getByTestId('artifact-card').getByRole('button', { name: 'Maximize', exact: true }).click()
  await expect(page).toHaveURL(/artifact=validated-view/)
  await expect(page.getByTestId('maximized-artifact').getByRole('cell', { name: 'published-value', exact: true })).toBeVisible()
  await page.getByRole('button', { name: /X-ray/ }).click()
  const display = page.getByRole('region', { name: 'Displayed conversation' })
  await expect(display.getByRole('heading', { name: 'Review' })).toBeVisible()
  await display.getByRole('button', { name: 'Highlight [PT_1]' }).first().click()
  const modelTab = page.getByRole('tab', { name: 'Model', exact: true })
  if (await modelTab.isVisible()) await modelTab.click()
  const model = page.getByRole('region', { name: 'Model-visible requests' })
  expect(await model.locator('[data-testid="xray-message"] pre').textContent()).toBe(text)
  await expect(model.locator('strong,table,a,img,script')).toHaveCount(0)
  await expect(model.locator('[data-token="[PT_1]"][aria-pressed="true"]').first()).toBeVisible()
  expect(writes).toEqual([])
  expect(outbound).toEqual([])
  expect(unexpected).toEqual([])
  expect(projection.messages[1].text).toBe(text)
})

test('real-agent tables, follow-ups, tools and charts survive refresh', async ({
  page, request,
}, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const session = await (await request.post('/api/sessions')).json()
  await page.goto(`/sessions/${session.id}`)
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Ready')
  await send(page, 'What specimens came in yesterday for patient NGC-0041872?')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete')
  const step = page.getByTestId('step-marker').filter({ hasText: 'find_specimens' }).first()
  await expect(step).toHaveAttribute('data-open', 'false')
  await step.getByRole('button', { name: 'Step details' }).click()
  await expect(step).toContainText('query-0002')
  await expect(step).toContainText('Arguments')
  await expect(step).toContainText('Result')
  const cards = page.getByTestId('artifact-card')
  const maximized = page.getByTestId('maximized-artifact')
  const mobile = testInfo.project.name === 'mobile'
  await expect(cards).toHaveCount(1)
  await expect(cards.first().getByRole('cell', { name: 'SPC-northgate-001-1', exact: true })).toBeVisible()
  await expect(maximized).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('real-table.png'), animations: 'disabled' })
  const firstArtifact = await cards.first().getAttribute('data-artifact-id')
  await page.locator(`a[data-testid="artifact-link"][data-artifact-id="${firstArtifact}"]`).first().click()
  await expect(page).toHaveURL(new RegExp(`artifact=${firstArtifact}`))
  await expect(maximized.getByRole('cell', { name: 'SPC-northgate-001-1', exact: true })).toBeVisible()
  await page.reload()
  await expect(maximized.getByRole('cell', { name: 'SPC-northgate-001-1', exact: true })).toBeVisible()
  await send(page, 'What libraries belong to those specimens?')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete')
  await expect(cards).toHaveCount(2)
  if (!mobile) await expect(maximized).toHaveAttribute('data-artifact-id', firstArtifact!)
  await expect(latestCard(page).getByRole('cell', { name: 'LIB-northgate-001-1', exact: true })).toBeVisible()
  await send(page, 'Show a coverage chart for those libraries.')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete')
  await expect(cards).toHaveCount(3)
  await expect(latestCard(page).locator('[data-testid="chart-canvas"] svg')).toBeVisible()
  await expect(latestCard(page).locator('[data-testid="chart-canvas"] .mark-rect.role-mark path')).toHaveCount(3)
  await latestCard(page).getByRole('button', { name: 'Maximize', exact: true }).click()
  await expect(maximized.locator('[data-testid="chart-canvas"] .mark-rect.role-mark path')).toHaveCount(3)
  await page.reload()
  await expect(maximized.locator('[data-testid="chart-canvas"] .mark-rect.role-mark path')).toHaveCount(3)

  const viewports = mobile
    ? [{ width: 390, height: 844 }, { width: 320, height: 568 }]
    : [{ width: 1440, height: 960 }]
  for (const viewport of viewports) {
    await page.setViewportSize(viewport)
    await expect.poll(() => page.evaluate(() => {
      const chart = document.querySelector('[data-testid="maximized-artifact"] [data-testid="chart-canvas"] svg')!.getBoundingClientRect()
      const panel = document.querySelector('[data-testid="maximized-artifact"]')!.getBoundingClientRect()
      return chart.width > 100 && chart.height > 200 && chart.left >= panel.left
        && chart.right <= panel.right + 1 && document.documentElement.scrollWidth <= innerWidth
    })).toBe(true)
    const visiblePixels = await page.evaluate(async () => {
      const svg = document.querySelector('[data-testid="maximized-artifact"] [data-testid="chart-canvas"] svg')!
      const bounds = svg.getBoundingClientRect()
      const image = new Image()
      image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new XMLSerializer().serializeToString(svg))}`
      await image.decode()
      const canvas = document.createElement('canvas')
      canvas.width = Math.ceil(bounds.width)
      canvas.height = Math.ceil(bounds.height)
      const context = canvas.getContext('2d')!
      context.drawImage(image, 0, 0)
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data
      let visible = 0
      for (let offset = 3; offset < pixels.length; offset += 4) {
        if (pixels[offset] > 0) visible += 1
      }
      return visible
    })
    expect(visiblePixels).toBeGreaterThan(1000)
    await page.screenshot({
      path: testInfo.outputPath(`real-chart-${viewport.width}.png`), animations: 'disabled',
    })
  }
  const beforeNavigation = await (await request.get(`/api/sessions/${session.id}/snapshot`)).json()
  await conversation(page)
  await page.locator(`a[data-testid="artifact-link"][data-artifact-id="${firstArtifact}"]`).first().click()
  await expect(maximized).toHaveAttribute('data-artifact-id', firstArtifact!)
  await conversation(page)
  const chartArtifact = beforeNavigation.artifacts[2].id
  await page.locator(`a[data-testid="artifact-link"][data-artifact-id="${chartArtifact}"]`).first().click()
  await expect(maximized).toHaveAttribute('data-artifact-id', chartArtifact)
  // Below desktop, reaching the conversation minimized the artifact, which is a step of its own.
  await page.goBack()
  if (mobile) {
    await expect(maximized).toHaveCount(0)
    await page.goBack()
  }
  await expect(maximized).toHaveAttribute('data-artifact-id', firstArtifact!)
  await page.goForward()
  if (mobile) await page.goForward()
  await expect(maximized).toHaveAttribute('data-artifact-id', chartArtifact)
  const afterNavigation = await (await request.get(`/api/sessions/${session.id}/snapshot`)).json()
  expect(afterNavigation).toEqual(beforeNavigation)
  const emptySession = await (await request.post('/api/sessions')).json()
  await page.goto(`/sessions/${emptySession.id}?artifact=${chartArtifact}`)
  await expect(page.getByRole('alert')).toContainText('Artifact unavailable')
  await expect(page.locator('[data-testid="chart-canvas"]')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('an unrecorded question fails visibly without an empty artifact', async ({ page, request }) => {
  const session = await (await request.post('/api/sessions')).json()
  await page.goto(`/sessions/${session.id}`)
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Ready')
  await send(page, 'This question deliberately has no provider cassette.')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Failed')
  await expect(page.getByRole('alert')).toContainText('Cassette miss:')
  await expect(page.getByRole('alert')).toContainText('ZAGENT_LLM_MODE=record')
  await expect(page.getByTestId('step-marker')).toHaveCount(0)
  await expect(page.getByTestId('artifact-card')).toHaveCount(0)
  await expect(page.getByTestId('artifact-list')).toHaveCount(0)
  await expect(page.getByRole('complementary', { name: 'Maximized artifact' })).toHaveCount(0)
})

for (const question of ["What's 2+2?", 'Write a poem about the ocean.', 'As part of job ABC, compute 2+2.']) {
  test(`structured refusal survives refresh: ${question}`, async ({ page, request }, testInfo) => {
    const session = await (await request.post('/api/sessions')).json()
    await page.goto(`/sessions/${session.id}`)
    await expect(page.getByTestId('conversation-turn-status')).toHaveText('Ready')
    await send(page, question)
    const chip = page.getByTestId('refusal')
    await expect(chip).toHaveAttribute('data-reason', 'out_of_domain')
    await expect(chip).toContainText('Outside workbench scope')
    await expect(chip).toContainText('I can help find patients, specimens, and libraries')
    await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete')
    await expect(page.getByTestId('assistant-message')).toHaveCount(0)
    await expect(page.getByTestId('step-marker')).toHaveCount(0)
    await page.reload()
    await expect(chip).toHaveCount(1)
    await expect(chip).toBeVisible()
    if (testInfo.project.name === 'mobile') await page.setViewportSize({ width: 320, height: 568 })
    const layout = await chip.evaluate((element) => {
      const bounds = element.getBoundingClientRect()
      return bounds.left >= 0 && bounds.right <= innerWidth
        && document.documentElement.scrollWidth <= innerWidth
    })
    expect(layout).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('scope-refusal.png'), animations: 'disabled' })
    await page.getByRole('textbox', { name: 'Message', exact: true }).fill('Show specimens')
    await expect(page.getByRole('button', { name: 'Send message', exact: true })).toBeEnabled()
  })
}

test('yes after a clarifying question reaches the clinical tools', async ({ page, request }) => {
  const session = await (await request.post('/api/sessions')).json()
  await page.goto(`/sessions/${session.id}`)
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Ready')
  await send(page, 'Ask me whether I want the libraries for specimens received in the last day for NGC-0041872, before looking anything up.')
  await expect(page.getByTestId('assistant-message')).toHaveCount(1)
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete')
  await send(page, 'yes')
  await expect(page.getByTestId('step-marker').filter({ hasText: 'find_libraries' })).toHaveCount(1)
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete')
  await expect(page.getByTestId('refusal')).toHaveCount(0)
  await expect(latestCard(page).getByRole('cell', { name: 'LIB-northgate-001-1', exact: true })).toBeVisible()
})

test('X-ray links resolved identifiers to the actual token-only model requests', async ({
  page, request,
}, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const session = await (await request.post('/api/sessions')).json()
  await page.goto(`/sessions/${session.id}`)
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Ready')
  await send(page, 'Give me the metadata of patient NGC-0041872. Show the patient table.')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete')
  await expect(latestCard(page).getByRole('cell', { name: 'NGC-0041872', exact: true })).toBeVisible()
  await expect(latestCard(page).getByRole('cell', { name: 'Mira Vellorin', exact: true })).toBeVisible()
  const model = await (await request.get(`/api/sessions/${session.id}/snapshot?representation=model`)).json()
  expect(JSON.stringify(model)).not.toContain('NGC-0041872')
  expect(JSON.stringify(model)).not.toContain('Mira Vellorin')
  expect(JSON.stringify(model)).toContain('[PT_1]')

  await page.getByRole('button', { name: 'X-ray', exact: true }).click()
  const displayed = page.getByRole('region', { name: 'Displayed conversation' })
  const modelPane = page.getByRole('region', { name: 'Model-visible requests' })
  await expect(displayed).toContainText('NGC-0041872')
  await expect(displayed).toContainText('find_patients')
  const source = displayed.getByRole('button', { name: 'Highlight [PT_1]', exact: true }).first()
  await source.click()
  if (testInfo.project.name === 'mobile') {
    await page.getByRole('tab', { name: 'Model', exact: true }).click()
  }
  await expect(modelPane).toBeVisible()
  await expect(modelPane).toContainText('[PT_1]')
  await expect(modelPane).not.toContainText('NGC-0041872')
  await expect(modelPane).not.toContainText('Mira Vellorin')
  await expect(modelPane.locator('[data-token][aria-pressed="true"]:visible').first()).toBeVisible()
  const xray = await (await request.get(`/api/sessions/${session.id}/xray`)).json()
  expect(xray.requests.length).toBeGreaterThan(1)
  expect(JSON.stringify(xray.requests)).not.toContain('NGC-0041872')
  expect(xray.executions.some((entry: { tool: string; arguments: { mrn?: string } }) =>
    entry.tool === 'find_patients' && entry.arguments.mrn === 'NGC-0041872',
  )).toBe(true)
  if (testInfo.project.name === 'mobile') await page.setViewportSize({ width: 320, height: 568 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('privacy-xray.png'), animations: 'disabled' })
  await page.reload()
  await expect(page.getByRole('button', { name: 'X-ray', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'X-ray', exact: true }).click()
  await send(page, 'Show the specimens received in the last day for that patient.')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete')
  await expect(latestCard(page).getByRole('cell', { name: 'SPC-northgate-001-1', exact: true })).toBeVisible()
  expect(errors).toEqual([])
})
import { expect, test } from '@playwright/test'

test.skip((process.env.ZAGENT_AGENT || 'llm') !== 'llm', 'Job views use real-agent replay')

test('MCP-owned job cards and grid update independently and reopen without execution', async ({ page, request }, testInfo) => {
  test.setTimeout(90000)
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const session = await (await request.post('/api/sessions')).json()
  await page.goto(`/sessions/${session.id}`)
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Ready')
  const message = page.getByRole('textbox', { name: 'Message', exact: true })
  await message.fill('Prepare two separate readqc drafts for all specimens received in the last week for NGC-0041877. Use default parameters for both and do not submit either.')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete', { timeout: 30000 })
  const initial = await (await request.get(`/api/sessions/${session.id}/snapshot`)).json()
  const drafts = Object.values(initial.drafts) as { draft_id: string; content_hash: string }[]
  expect(drafts).toHaveLength(2)
  for (const draft of drafts) {
    const confirmed = await request.post(`/api/sessions/${session.id}/drafts/${draft.draft_id}/confirm`, { data: { content_hash: draft.content_hash } })
    expect(confirmed.ok()).toBe(true)
  }
  await message.fill('Show a live job grid for this session.')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete', { timeout: 30000 })
  const link = page.getByRole('link', { name: 'Analysis jobs', exact: true }).first()
  await link.focus()
  await page.keyboard.press('Enter')
  const selected = await page.getByTestId('active-view').getAttribute('data-view-id')
  const frame = page.frameLocator('[data-testid="mcp-job-frame"]')
  await expect(frame.locator('[data-job-id]')).toHaveCount(2)
  await expect(page.getByTestId('mcp-job-frame')).toHaveAttribute('sandbox', 'allow-scripts')
  for (const job of ['job-0001', 'job-0002']) {
    const card = frame.getByRole('region', { name: `Job ${job}`, exact: true })
    await expect(card.getByRole('progressbar')).toBeVisible()
    await expect.poll(async () => Number(await card.getByRole('progressbar').getAttribute('value')), { timeout: 45000 }).toBeGreaterThan(0.2)
  }
  const before = await (await request.get(`/api/sessions/${session.id}/snapshot`)).json()
  const denied = await frame.locator('body').evaluate(() => new Promise((resolve) => {
    const identity = `probe-${Date.now()}`
    const listener = (event: MessageEvent) => {
      if (event.source === window.parent && event.data?.id === identity) {
        window.removeEventListener('message', listener)
        resolve(event.data)
      }
    }
    window.addEventListener('message', listener)
    window.parent.postMessage({ jsonrpc: '2.0', id: identity, method: 'tools/call', params: { name: 'update_draft', arguments: { app_id: 'readqc' } } }, '*')
  }))
  expect(JSON.stringify(denied)).toContain('bound job reads only')
  const viewport = testInfo.project.name === 'mobile' ? { width: 320, height: 568 } : { width: 1440, height: 960 }
  await page.setViewportSize(viewport)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(await frame.locator('body').evaluate((body) => body.ownerDocument.documentElement.scrollWidth <= body.ownerDocument.defaultView!.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath(`job-grid-${viewport.width}.png`), animations: 'disabled' })
  await page.reload()
  await expect(page.getByTestId('active-view')).toHaveAttribute('data-view-id', selected!)
  await expect(frame.locator('[data-job-id]')).toHaveCount(2)
  const chat = page.getByRole('tab', { name: 'Conversation', exact: true })
  if (await chat.isVisible()) await chat.click()
  await page.getByTestId('view-reference').filter({ hasText: 'Read quality control' }).first().click()
  await expect(frame.locator('[data-job-id]')).toHaveCount(1)
  await page.goBack()
  const surface = page.getByRole('tab', { name: /Working surface/ })
  if (await surface.isVisible()) await surface.click()
  await expect(page.getByTestId('active-view')).toHaveAttribute('data-view-id', selected!)
  const after = await (await request.get(`/api/sessions/${session.id}/snapshot`)).json()
  expect(after).toEqual(before)
  for (const job of ['job-0001', 'job-0002']) {
    await expect.poll(async () => (await (await request.get(`/api/sessions/${session.id}/jobs/${job}`)).json()).status, { timeout: 50000 }).toBe('completed')
    const current = await (await request.get(`/api/sessions/${session.id}/jobs/${job}`)).json()
    expect(current.attempts).toHaveLength(1)
  }
  expect(errors).toEqual([])
})
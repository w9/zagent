import { expect, test } from '@playwright/test'

test.skip((process.env.ZAGENT_AGENT || 'llm') !== 'llm', 'Job artifacts use real-agent replay')

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
  const maximized = page.getByTestId('maximized-artifact')
  const panel = page.getByRole('complementary', { name: 'Maximized artifact' })
  await expect(maximized).toHaveAttribute('data-kind', 'job_grid')
  const selected = await maximized.getAttribute('data-artifact-id')
  await expect(page.locator(`[data-testid="artifact-card"][data-artifact-id="${selected}"]`)).toHaveAttribute('data-state', 'maximized')
  const frame = maximized.frameLocator('[data-testid="mcp-job-frame"]')
  await expect(maximized.getByTestId('mcp-job-frame')).toHaveAttribute('data-display-mode', 'fullscreen')
  await expect(frame.locator('[data-job-id]')).toHaveCount(2)
  await expect(maximized.getByTestId('mcp-job-frame')).toHaveAttribute('sandbox', 'allow-scripts')
  for (const job of ['job-0001', 'job-0002']) {
    const card = frame.getByRole('region', { name: `Job ${job}`, exact: true })
    await expect(card.getByRole('progressbar')).toBeVisible()
    await expect(card.getByRole('log')).toBeVisible()
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
  await expect(maximized).toHaveAttribute('data-artifact-id', selected!)
  await expect(frame.locator('[data-job-id]')).toHaveCount(2)

  // Inline, a job card is a compact live summary; its "Show log" asks the host for fullscreen.
  await panel.getByRole('button', { name: 'Minimize', exact: true }).click()
  await expect(panel).toHaveCount(0)
  const jobCard = page.locator('[data-testid="artifact-card"][data-kind="job_card"]').first()
  await jobCard.scrollIntoViewIfNeeded()
  await expect(jobCard.getByTestId('mcp-job-frame')).toHaveAttribute('data-display-mode', 'inline')
  const inline = jobCard.frameLocator('[data-testid="mcp-job-frame"]')
  await expect(inline.locator('[data-job-id]')).toHaveCount(1)
  await expect(inline.getByRole('progressbar')).toBeVisible()
  await expect(inline.getByRole('log')).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath(`job-card-inline-${viewport.width}.png`), animations: 'disabled' })
  await inline.getByRole('button', { name: 'Show log' }).click()
  await expect(maximized).toHaveAttribute('data-artifact-id', (await jobCard.getAttribute('data-artifact-id'))!)
  await expect(maximized.getByTestId('mcp-job-frame')).toHaveAttribute('data-display-mode', 'fullscreen')
  await expect(frame.locator('[data-job-id]')).toHaveCount(1)
  await expect(frame.getByRole('log')).toBeVisible()
  await page.goBack()
  await expect(panel).toHaveCount(0)
  await page.goBack()
  await expect(maximized).toHaveAttribute('data-artifact-id', selected!)
  const after = await (await request.get(`/api/sessions/${session.id}/snapshot`)).json()
  expect(after).toEqual(before)
  for (const job of ['job-0001', 'job-0002']) {
    await expect.poll(async () => (await (await request.get(`/api/sessions/${session.id}/jobs/${job}`)).json()).status, { timeout: 50000 }).toBe('completed')
    const current = await (await request.get(`/api/sessions/${session.id}/jobs/${job}`)).json()
    expect(current.attempts).toHaveLength(1)
  }
  expect(errors).toEqual([])
})
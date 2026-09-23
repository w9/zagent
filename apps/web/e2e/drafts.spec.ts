import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'

test.skip((process.env.ZAGENT_AGENT || 'llm') !== 'llm', 'Draft flows require the real replay agent')

async function createSession(request: APIRequestContext) {
  return (await (await request.post('/api/sessions')).json()).id as string
}

async function open(page: Page, sessionId: string) {
  await page.goto(`/sessions/${sessionId}`)
  await expect(page.getByTestId('conversation-turn-status')).not.toHaveText(/Connecting|Reconnecting/)
}

async function send(page: Page, text: string) {
  const tab = page.getByRole('tab', { name: 'Conversation', exact: true })
  if (await tab.isVisible()) await tab.click()
  await page.getByRole('textbox', { name: 'Message', exact: true }).fill(text)
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete', { timeout: 30_000 })
}

async function showSurface(page: Page) {
  const tab = page.getByRole('tab', { name: /Working surface/ })
  if (await tab.isVisible()) await tab.click()
}

test('draft chat edits, missing-normal validation and exact-view links survive refresh', async ({ page, request }, testInfo) => {
  const sessionId = await createSession(request)
  await open(page, sessionId)
  await send(page, 'Prepare somatic calling on specimens received in the last day for NGC-0041875.')
  const link = page.getByRole('link', { name: 'Somatic variant calling', exact: true })
  await expect(link).toBeVisible()
  await link.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/view=view-/)
  await expect(page.locator('.surface-content')).toBeFocused()
  await expect(page.getByRole('region', { name: 'Analysis draft' }).getByText('A matched normal specimen is missing.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Confirm submission' })).toBeDisabled()
  const original = await page.getByTestId('active-view').getAttribute('data-view-id')
  await send(page, 'min VAF 0.03')
  await showSurface(page)
  await expect(page.getByRole('spinbutton', { name: 'Minimum VAF' })).toHaveValue('0.03')
  await expect(page.getByTestId('active-view')).toHaveAttribute('data-view-id', original!)
  await page.reload()
  await expect(page.getByRole('spinbutton', { name: 'Minimum VAF' })).toHaveValue('0.03')
  for (const viewport of testInfo.project.name === 'mobile'
    ? [{ width: 390, height: 844 }, { width: 320, height: 568 }]
    : [{ width: 1440, height: 960 }]) {
    await page.setViewportSize(viewport)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`draft-${viewport.width}.png`), animations: 'disabled' })
  }
  await page.goto(`/sessions/${sessionId}?view=missing-view&panel=surface`)
  await expect(page.getByRole('alert')).toContainText('View unavailable')
})

test('form edits synchronize, stale confirmation shows a diff, and confirmation creates one job', async ({ page, context, request }, testInfo) => {
  const sessionId = await createSession(request)
  await open(page, sessionId)
  await send(page, 'Prepare a readqc draft for specimens received in the last day for NGC-0041872 with minimum coverage 40. Do not submit it.')
  await showSurface(page)
  await expect(page.getByRole('spinbutton', { name: 'Minimum coverage' })).toHaveValue('40')
  const second = await context.newPage()
  await open(second, sessionId)
  await showSurface(second)
  const input = page.getByRole('spinbutton', { name: 'Minimum coverage' })
  await input.fill('45')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(second.getByRole('spinbutton', { name: 'Minimum coverage' })).toHaveValue('45')
  const snapshot = await (await request.get(`/api/sessions/${sessionId}/snapshot`)).json()
  const draft = Object.values(snapshot.drafts)[0] as { draft_id: string; content_hash: string }
  await page.route(`**/api/sessions/${sessionId}/drafts/${draft.draft_id}/confirm`, async (route) => {
    await request.patch(`/api/sessions/${sessionId}/drafts/${draft.draft_id}`, {
      data: { content_hash: draft.content_hash, parameters: { min_coverage: 46 } },
    })
    await route.continue()
  }, { times: 1 })
  await page.getByRole('button', { name: 'Confirm submission' }).click()
  await expect(page.getByRole('alert')).toContainText('Draft changed')
  await expect(page.getByRole('alert')).toContainText('45 to 46')
  const before = await (await request.get(`/api/sessions/${sessionId}/snapshot`)).json()
  expect(Object.keys(before.jobs)).toHaveLength(0)
  await page.getByRole('button', { name: 'Review current draft' }).click()
  await page.getByRole('button', { name: 'Confirm submission' }).click()
  await expect(page.getByRole('region', { name: 'Submitted job' })).toBeVisible()
  await expect(page.getByText('Pending', { exact: true })).toBeVisible()
  const after = await (await request.get(`/api/sessions/${sessionId}/snapshot`)).json()
  expect(Object.keys(after.jobs)).toHaveLength(1)
  const current = Object.values(after.drafts)[0] as { content_hash: string }
  const repeated = await request.post(`/api/sessions/${sessionId}/drafts/${draft.draft_id}/confirm`, { data: { content_hash: current.content_hash } })
  expect(repeated.status()).toBe(200)
  await page.screenshot({ path: testInfo.outputPath('pending-job.png'), animations: 'disabled' })
  const chat = page.getByRole('tab', { name: 'Conversation', exact: true })
  if (await chat.isVisible()) await chat.click()
  const references = page.getByRole('link', { name: 'Read quality control', exact: true })
  const sequence = after.seq
  await references.first().click()
  await expect(page.getByRole('region', { name: 'Analysis draft' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('region', { name: 'Analysis draft' })).toBeVisible()
  const navigated = await (await request.get(`/api/sessions/${sessionId}/snapshot`)).json()
  expect(navigated.seq).toBe(sequence)
  expect(navigated.drafts).toEqual(after.drafts)
  expect(navigated.jobs).toEqual(after.jobs)
  await second.close()
})

test('newest sessions stay first and manual topic titles persist across tabs', async ({ page, context, request }) => {
  const first = await createSession(request)
  const second = await createSession(request)
  const sessions = await (await request.get('/api/sessions')).json()
  expect(sessions[0].id).toBe(second)
  await open(page, first)
  const other = await context.newPage()
  await open(other, first)
  const drawer = page.getByRole('button', { name: 'Open sessions' })
  if (await drawer.isVisible()) await drawer.click()
  const entry = page.locator(`.session-entry[data-session-id="${first}"]:visible`)
  await entry.getByRole('button', { name: /^Rename / }).click()
  await page.getByRole('textbox', { name: 'Session title' }).fill('My intake review')
  await page.getByRole('button', { name: 'Save session title' }).click()
  if (await page.getByRole('button', { name: 'Close sessions' }).isVisible()) {
    await page.getByRole('button', { name: 'Close sessions' }).click()
  }
  await expect(other.locator('.chat-heading .session-subtitle')).toHaveText('My intake review')
  await page.reload()
  await expect(page.locator('.chat-heading .session-subtitle')).toHaveText('My intake review')
  const ordered = await (await request.get('/api/sessions')).json()
  expect(ordered[0].id).toBe(second)
  expect(ordered.find((item: { id: string }) => item.id === first).title_source).toBe('manual')
  const third = await createSession(request)
  if (await drawer.isVisible()) await drawer.click()
  await expect(page.locator('.session-entry:visible').first()).toHaveAttribute('data-session-id', third)
  await expect(page).toHaveURL(new RegExp(`/sessions/${first}`))
  await expect(other.locator('.chat-heading .session-subtitle')).toHaveText('My intake review')
  await other.close()
})
import { expect, test } from '@playwright/test'
import type { APIRequestContext, BrowserContext, Locator, Page } from '@playwright/test'

test.skip((process.env.ZAGENT_AGENT || 'llm') !== 'llm', 'Recorded knowledge answers require the real replay agent')

// The KB-VERSIONS-QA and KB-VERSIONS-ANALYST conversations, replayed from their cassettes.
const TURNS = [
  'Which versions of SOP-QC-001 can I see, and which one is effective?',
  'What would the draft version change? Quote it.',
]

async function converse(page: Page, request: APIRequestContext, persona: string) {
  const sessionId = (await (await request.post('/api/sessions', { data: { persona } })).json()).id as string
  await page.goto(`/sessions/${sessionId}`)
  await expect(page.getByTestId('conversation-turn-status')).not.toHaveText(/Connecting|Reconnecting/)
  for (const text of TURNS) {
    await page.getByRole('textbox', { name: 'Message', exact: true }).fill(text)
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete', { timeout: 30_000 })
  }
  return sessionId
}

async function seq(request: APIRequestContext, sessionId: string) {
  return (await (await request.get(`/api/sessions/${sessionId}/snapshot`)).json()).seq as number
}

/** Opens a chip the way a reader would and returns the intranet tab. */
async function open(context: BrowserContext, chip: Locator, mobile: boolean) {
  const opened = context.waitForEvent('page')
  if (mobile) await chip.tap()
  else await chip.click()
  const tab = await opened
  await tab.waitForLoadState()
  return tab
}

test('a QA officer previews a cited draft and opens it highlighted on the intranet', async ({
  page, context, request,
}, testInfo) => {
  const mobile = testInfo.project.name === 'mobile'
  const sessionId = await converse(page, request, 'qa-officer')
  const chips = page.getByTestId('citation-chip')
  await expect(chips.first()).toBeVisible()
  for (const chip of await chips.all()) await expect(chip).toHaveAttribute('data-verified', 'true')
  const draft = page.locator('[data-testid="citation-chip"][data-document="sop-qc-001-v4"]').first()
  await expect(draft).toHaveText('SOP-QC-001 v4 · L10–22')
  if (!mobile) {
    await draft.hover()
    await expect(page.getByRole('tooltip')).toContainText('would require a mean coverage of at least 45x')
    await page.screenshot({ path: testInfo.outputPath('citation-preview.png'), animations: 'disabled' })
  }
  const before = await seq(request, sessionId)
  const tab = await open(context, draft, mobile)
  await expect(tab).toHaveURL(/\/qms\/documents\/SOP-QC-001\/v4\?/)
  expect(tab.url()).not.toContain('token')
  expect(await tab.evaluate(() => window.opener)).toBeNull()
  await expect(tab.getByText('Opened from your workbench session as Odile Fenn')).toBeVisible()
  await expect(tab.locator('[id^="L"].hl')).toHaveCount(13)
  await expect(tab.locator('[id^="L"].hl').filter({ hasText: 'at least 45x' })).toHaveCount(1)
  await tab.screenshot({ path: testInfo.outputPath('intranet-draft.png') })
  // Opening a citation is a read: no turn, draft or job event is written.
  expect(await seq(request, sessionId)).toBe(before)
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete')
})

test('an analyst never gets a chip for the draft and the intranet hides it from them too', async ({
  page, context, request,
}, testInfo) => {
  const mobile = testInfo.project.name === 'mobile'
  await converse(page, request, 'analyst')
  await expect(page.getByTestId('citation-chip').first()).toBeVisible()
  await expect(page.locator('[data-testid="citation-chip"][data-document="sop-qc-001-v4"]')).toHaveCount(0)
  const effective = page.locator('[data-testid="citation-chip"][data-document="sop-qc-001-v3"]').first()
  const tab = await open(context, effective, mobile)
  await expect(tab).toHaveURL(/\/qms\/documents\/SOP-QC-001\/v3\?/)
  await expect(tab.getByText('Opened from your workbench session as Ilse Marrow')).toBeVisible()
  const hidden = await tab.goto(new URL('/qms/documents/SOP-QC-001/v4', tab.url()).href)
  expect(hidden?.status()).toBe(404)
  await expect(tab.getByRole('heading', { name: 'Page not found' })).toBeVisible()
})

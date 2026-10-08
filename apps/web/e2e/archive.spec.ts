import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'

async function createSession(request: APIRequestContext) {
  const response = await request.post('/api/sessions')
  expect(response.status()).toBe(201)
  return (await response.json()).id as string
}

async function activeIds(request: APIRequestContext) {
  return ((await (await request.get('/api/sessions')).json()) as { id: string }[]).map((item) => item.id)
}

async function openSessionList(page: Page) {
  const drawer = page.getByRole('button', { name: 'Open sessions' })
  if (await drawer.isVisible()) await drawer.click()
}

async function closeSessionList(page: Page) {
  const close = page.getByRole('button', { name: 'Close sessions' })
  if (await close.isVisible()) await close.click()
}

async function archiveFromMenu(page: Page, sessionId: string) {
  await openSessionList(page)
  await page.locator(`li[data-session-id="${sessionId}"]:visible`).getByRole('button', { name: /^Actions for / }).click()
  await page.getByRole('menuitem', { name: 'Archive' }).click()
}

test('archiving the open session opens the newest remaining one, and Undo brings it back', async ({ page, request }) => {
  const older = await createSession(request)
  const newer = await createSession(request)
  await page.goto(`/sessions/${newer}`)
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toBeEnabled()
  await archiveFromMenu(page, newer)
  await expect(page).toHaveURL(new RegExp(`/sessions/${older}`))
  await expect(page.getByRole('region', { name: 'Conversation' })).toHaveCount(1)
  expect(await activeIds(request)).not.toContain(newer)
  const toast = page.getByRole('status').filter({ hasText: 'Archived' })
  await toast.getByRole('button', { name: 'Undo' }).click()
  await expect(toast).toHaveCount(0)
  await expect(page).toHaveURL(new RegExp(`/sessions/${newer}`))
  await expect(page.getByRole('region', { name: 'Conversation' })).toHaveCount(1)
  expect((await activeIds(request))[0]).toBe(newer)
})

test('archived sessions are listed separately, read-only, and can be unarchived', async ({ page, request }) => {
  const session = await createSession(request)
  expect((await request.post(`/api/sessions/${session}/archive`, { data: {} })).status()).toBe(200)
  await page.goto(`/sessions/${session}`)
  await expect(page.getByText('This session is read-only. Unarchive it to continue the conversation.')).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toHaveCount(0)
  await openSessionList(page)
  await expect(page.locator(`li[data-session-id="${session}"]:visible`)).toHaveCount(0)
  await page.getByRole('button', { name: 'Archived', exact: true }).filter({ visible: true }).click()
  const row = page.locator(`li[data-session-id="${session}"]:visible`)
  await expect(row.getByRole('link')).toHaveAttribute('aria-current', 'page')
  await row.getByRole('button', { name: /^Unarchive / }).click()
  await expect(row).toHaveCount(0)
  await page.getByRole('button', { name: 'Back to sessions' }).filter({ visible: true }).click()
  await expect(page.locator(`li[data-session-id="${session}"]:visible`)).toBeVisible()
  await closeSessionList(page)
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toBeEnabled()
})

test('archiving while the agent responds asks first, then stops the response', async ({ page, request }) => {
  test.skip((process.env.ZAGENT_AGENT || 'llm') !== 'scripted', 'Needs the slow scripted agent to catch a running turn')
  const session = await createSession(request)
  await page.goto(`/sessions/${session}`)
  await page.getByRole('textbox', { name: 'Message', exact: true }).fill('Hello')
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  await expect(page.getByTestId('conversation-turn-status')).toHaveText(/Responding/)
  await archiveFromMenu(page, session)
  const dialog = page.getByRole('alertdialog')
  await expect(dialog).toContainText('The agent is still responding.')
  await dialog.getByRole('button', { name: 'Stop and archive' }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page).not.toHaveURL(new RegExp(`/sessions/${session}`))
  await expect(page.getByRole('status').filter({ hasText: 'Archived' })).toHaveCount(0)
  const turn = (await (await request.get(`/api/sessions/${session}/snapshot`)).json()).conversation_turn
  expect(turn.status).toBe('failed')
  expect(turn.error).toBe('Stopped because the session was archived.')
})

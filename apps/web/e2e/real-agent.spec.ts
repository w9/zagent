import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

test.skip(
  (process.env.ZAGENT_AGENT || 'llm') !== 'llm',
  'Real-agent cassettes require ZAGENT_AGENT=llm and replay mode',
)

async function send(page: Page, message: string) {
  const chat = page.getByRole('tab', { name: 'Conversation', exact: true })
  if (await chat.isVisible()) await chat.click()
  await page.getByRole('textbox', { name: 'Message', exact: true }).fill(message)
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
}

async function surface(page: Page) {
  const tab = page.getByRole('tab', { name: /Working surface/ })
  if (await tab.isVisible()) await tab.click()
}

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
  expect(await step.getAttribute('open')).toBeNull()
  await step.locator('summary').click()
  await expect(step).toContainText('query-0002')
  await expect(step).toContainText('Arguments')
  await expect(step).toContainText('Result')
  await surface(page)
  await expect(page.getByRole('cell', { name: 'SPC-northgate-001-1', exact: true })).toBeVisible()
  await expect(page.getByTestId('view-position')).toHaveText('View 1 of 1')
  await page.screenshot({ path: testInfo.outputPath('real-table.png'), animations: 'disabled' })
  await page.reload()
  await expect(page.getByRole('cell', { name: 'SPC-northgate-001-1', exact: true })).toBeVisible()
  await send(page, 'What libraries belong to those specimens?')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete')
  await surface(page)
  await expect(page.getByRole('cell', { name: 'LIB-northgate-001-1', exact: true })).toBeVisible()
  await send(page, 'Show a coverage chart for those libraries.')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete')
  await surface(page)
  await expect(page.getByTestId('view-position')).toHaveText('View 3 of 3')
  await expect(page.locator('.chart-canvas svg')).toBeVisible()
  await expect(page.locator('.chart-canvas .mark-rect.role-mark path')).toHaveCount(3)
  await page.reload()
  await expect(page.locator('.chart-canvas .mark-rect.role-mark path')).toHaveCount(3)

  const viewports = testInfo.project.name === 'mobile'
    ? [{ width: 390, height: 844 }, { width: 320, height: 568 }]
    : [{ width: 1440, height: 960 }]
  for (const viewport of viewports) {
    await page.setViewportSize(viewport)
    await expect.poll(() => page.evaluate(() => {
      const chart = document.querySelector('.chart-canvas svg')!.getBoundingClientRect()
      const panel = document.querySelector('.surface-content')!.getBoundingClientRect()
      return chart.width > 100 && chart.height > 200 && chart.left >= panel.left
        && chart.right <= panel.right + 1 && document.documentElement.scrollWidth <= innerWidth
    })).toBe(true)
    const visiblePixels = await page.evaluate(async () => {
      const svg = document.querySelector('.chart-canvas svg')!
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
  await page.getByRole('button', { name: 'Previous view', exact: true }).click()
  await expect(page.getByRole('cell', { name: 'LIB-northgate-001-1', exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test('an unrecorded question fails visibly without an empty view', async ({ page, request }) => {
  const session = await (await request.post('/api/sessions')).json()
  await page.goto(`/sessions/${session.id}`)
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Ready')
  await send(page, 'This question deliberately has no provider cassette.')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Failed')
  await expect(page.getByRole('alert')).toContainText('Cassette miss:')
  await expect(page.getByRole('alert')).toContainText('ZAGENT_LLM_MODE=record')
  await expect(page.getByTestId('step-marker')).toHaveCount(0)
  await surface(page)
  await expect(page.getByText('No views yet')).toBeVisible()
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
  await surface(page)
  await expect(page.getByRole('cell', { name: 'LIB-northgate-001-1', exact: true })).toBeVisible()
})
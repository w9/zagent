import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { once } from 'node:events'
import { createServer, request as proxyRequest } from 'node:http'
import type { ServerResponse } from 'node:http'
import type { AddressInfo } from 'node:net'

test.skip(
  (process.env.ZAGENT_AGENT || 'llm') !== 'scripted',
  'Legacy stream fixtures require ZAGENT_AGENT=scripted',
)

const expected =
  'Message received.\n\nFor this synthetic genomics workspace, the review order is specimen intake, analysis status, then unresolved quality checks.\n\nNo records have been queried and no analysis has been started. This response is a fixed script, independent of your message.'

async function createSession(request: APIRequestContext) {
  const response = await request.post('/api/sessions')
  expect(response.status()).toBe(201)
  return (await response.json()).id as string
}

async function openSession(page: Page, sessionId: string, origin = '') {
  await page.goto(`${origin}/sessions/${sessionId}`)
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeEnabled()
  await expect(page.getByTestId('conversation-turn-status')).not.toHaveText(
    /Connecting|Reconnecting/,
  )
}

async function send(page: Page, text: string) {
  await page.getByRole('textbox', { name: 'Message', exact: true }).fill(text)
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
}

function answer(page: Page) {
  return page
    .getByTestId('assistant-message')
    .last()
    .getByTestId('message-text')
}

async function assertAnswer(page: Page, request: APIRequestContext) {
  await expect(answer(page).locator('p')).toHaveText(expected.split('\n\n'))
  const path = new URL(page.url()).pathname
  const snapshot = await (await request.get(`/api${path}/snapshot?representation=model`)).json()
  const assistant = snapshot.messages.filter((message: { role: string }) => message.role === 'assistant')
  expect(assistant.at(-1).text).toBe(expected)
}

async function interruptibleProxy(target: string) {
  const streams = new Set<ServerResponse>()
  const resumeCursors: string[] = []
  const server = createServer((incoming, outgoing) => {
    const destination = new URL(incoming.url || '/', target)
    const upstream = proxyRequest(
      destination,
      {
        method: incoming.method,
        headers: { ...incoming.headers, host: destination.host },
      },
      (response) => {
        outgoing.writeHead(response.statusCode || 502, response.headers)
        response.pipe(outgoing)
      },
    )
    upstream.on('error', () => outgoing.destroy())
    if (destination.pathname.endsWith('/events')) {
      streams.add(outgoing)
      const cursor = incoming.headers['last-event-id']
      if (typeof cursor === 'string') resumeCursors.push(cursor)
    }
    outgoing.on('close', () => {
      streams.delete(outgoing)
      upstream.destroy()
    })
    incoming.pipe(upstream)
  })
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  return {
    origin: `http://127.0.0.1:${(server.address() as AddressInfo).port}`,
    resumeCursors,
    disconnect: () => {
      for (const stream of streams) stream.destroy()
    },
    close: () =>
      new Promise<void>((resolve) => {
        server.close(() => resolve())
        server.closeAllConnections()
      }),
  }
}

async function assertLayout(page: Page) {
  const result = await page.evaluate(() => {
    const composer = document
      .querySelector('[data-testid="composer"]')!
      .getBoundingClientRect()
    const header = document
      .querySelector('#conversation-panel > header')!
      .getBoundingClientRect()
    const footer = document
      .querySelector('[data-testid="composer-footer"]')!
      .getBoundingClientRect()
    return {
      overflow: document.documentElement.scrollWidth > window.innerWidth,
      composerVisible:
        composer.left >= 0 && composer.right <= window.innerWidth,
      noOverlap: composer.top >= header.bottom && composer.bottom <= footer.top,
      footerVisible: footer.bottom <= window.innerHeight,
      fontsLoaded: document.fonts.check('14px "DM Sans Variable"'),
    }
  })
  expect(result).toEqual({
    overflow: false,
    composerVisible: true,
    noOverlap: true,
    footerVisible: true,
    fontsLoaded: true,
  })
}

test('refresh, two tabs, socket reconnect, and a second conversation turn agree', async ({
  page,
  context,
  request,
  baseURL,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop')
  const proxy = await interruptibleProxy(baseURL!)
  try {
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    const sessionId = await createSession(request)
    await openSession(page, sessionId, proxy.origin)
    const second = await context.newPage()
    await openSession(second, sessionId, proxy.origin)
    await send(page, 'Hello')
    await expect(answer(page)).toContainText('Message received.')
    const partial = await answer(page).textContent()
    expect(partial!.length).toBeLessThan(expected.length)
    await expect(page.getByTestId('conversation-turn-status')).toHaveText(
      'Responding',
    )
    await page.screenshot({
      path: testInfo.outputPath('desktop-streaming.png'),
    })
    await page.reload()
    await expect(answer(page)).toContainText(partial!)
    await expect(answer(second)).toContainText(partial!)
    proxy.disconnect()
    await expect(second.getByTestId('conversation-turn-status')).toHaveText(
      'Reconnecting',
    )
    await expect(page.getByTestId('conversation-turn-status')).toHaveText(
      'Complete',
    )
    await expect(second.getByTestId('conversation-turn-status')).toHaveText(
      'Complete',
    )
    await assertAnswer(page, request)
    await assertAnswer(second, request)
    expect(proxy.resumeCursors.length).toBeGreaterThan(0)
    await send(page, 'Again')
    await expect(page.getByTestId('assistant-message')).toHaveCount(2)
    await expect(page.getByTestId('conversation-turn-status')).toHaveText(
      'Complete',
    )
    await expect(second.getByTestId('assistant-message')).toHaveCount(2)
    await expect(second.getByTestId('conversation-turn-status')).toHaveText(
      'Complete',
    )
    await assertAnswer(second, request)
    await expect(page.getByTestId('view-position')).toHaveText('View 4 of 4')
    await expect(second.getByTestId('view-position')).toHaveText('View 4 of 4')
    expect(
      await page.getByTestId('active-view').getAttribute('data-view-id'),
    ).toBe(await second.getByTestId('active-view').getAttribute('data-view-id'))
    await assertLayout(page)
    await page.screenshot({ path: testInfo.outputPath('desktop-complete.png') })
    expect(errors).toEqual([])
  } finally {
    await proxy.close()
  }
})

test('closing the only tab does not cancel a conversation turn', async ({
  page,
  context,
  request,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop')
  const sessionId = await createSession(request)
  await openSession(page, sessionId)
  await send(page, 'Hello')
  await expect(answer(page)).toContainText('Message received.')
  await page.close()
  await expect
    .poll(async () => {
      const snapshot = await request.get(`/api/sessions/${sessionId}/snapshot`)
      return (await snapshot.json()).conversation_turn?.status
    })
    .toBe('finished')
  const reopened = await context.newPage()
  await reopened.goto('/')
  await expect(reopened).toHaveURL(new RegExp(`/sessions/${sessionId}$`))
  await expect(reopened.getByTestId('conversation-turn-status')).toHaveText(
    'Complete',
  )
  await assertAnswer(reopened, request)
})

test('failed conversation turns are visible and accept a new message', async ({
  page,
  request,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop')
  const sessionId = await createSession(request)
  await openSession(page, sessionId)
  await send(page, '/fail')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText(
    'Failed',
  )
  await expect(page.getByRole('alert')).toContainText('Scripted failure')
  await expect(answer(page)).toHaveText(
    'Message received. The scripted conversation turn encountered an error.',
  )
  await page.reload()
  await expect(page.getByTestId('conversation-turn-status')).toHaveText(
    'Failed',
  )
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Try again')
  await expect(
    page.getByRole('button', { name: 'Send message', exact: true }),
  ).toBeEnabled()
  await page.screenshot({ path: testInfo.outputPath('desktop-failed.png') })
})

test('an answer can be copied and the latest turn retried in place', async ({
  page,
  context,
  request,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop')
  test.setTimeout(90_000)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const sessionId = await createSession(request)
  await openSession(page, sessionId)
  await send(page, 'Hello')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete', { timeout: 30_000 })
  const reply = page.getByTestId('assistant-message').last()
  await reply.getByRole('button', { name: 'Copy', exact: true }).click()
  await expect(reply.getByRole('button', { name: 'Copied', exact: true })).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(expected)
  const before = await (await request.get(`/api/sessions/${sessionId}/snapshot`)).json()
  // The scripted turn ends with views, so Retry sits under the turn rather than the answer.
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Responding')
  await expect(page.getByRole('button', { name: 'Retry', exact: true })).toHaveCount(0)
  await expect(page.getByTestId('conversation-turn-status')).toHaveText('Complete', { timeout: 30_000 })
  await expect(page.getByTestId('user-message')).toHaveCount(1)
  await expect(page.getByTestId('assistant-message')).toHaveCount(1)
  await assertAnswer(page, request)
  const after = await (await request.get(`/api/sessions/${sessionId}/snapshot`)).json()
  expect(after.conversation_turn.id).not.toBe(before.conversation_turn.id)
  expect(after.messages[1].id).not.toBe(before.messages[1].id)
  await expect(page.getByRole('button', { name: 'Retry', exact: true })).toBeEnabled()
  await page.screenshot({ path: testInfo.outputPath('desktop-retried.png') })
})

test('mobile sessions, streaming, refresh, and compact viewports', async ({
  page,
  request,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile')
  const sessionId = await createSession(request)
  await openSession(page, sessionId)
  await page.getByRole('button', { name: 'Open sessions' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: 'New session', exact: true }).click()
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(page).not.toHaveURL(new RegExp(sessionId))
  await page.screenshot({ path: testInfo.outputPath('mobile-empty.png') })
  await send(page, 'Hello')
  await expect(answer(page)).toContainText('Message received.')
  await page.reload()
  await expect(page.getByTestId('conversation-turn-status')).toHaveText(
    'Complete',
  )
  await assertAnswer(page, request)
  await assertLayout(page)
  await page.screenshot({ path: testInfo.outputPath('mobile-complete.png') })
  await page.setViewportSize({ width: 320, height: 568 })
  await assertLayout(page)
  await page.screenshot({ path: testInfo.outputPath('mobile-small.png') })
})

test('view history survives refresh, pauses following, and rejects invalid specs', async ({
  page,
  request,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop')
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const sessionId = await createSession(request)
  await openSession(page, sessionId)
  await send(page, 'Show intake')
  await expect(page.getByTestId('view-position')).toHaveText('View 2 of 2')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText(
    'Complete',
  )
  await expect(
    page.getByRole('heading', { name: 'Intake quality checks', exact: true }),
  ).toBeVisible()
  await expect(page.getByTestId('step-marker')).toHaveCount(2)
  await expect(page.getByTestId('step-marker').first()).toHaveAttribute('data-open', 'false')
  await page.getByTestId('step-marker').first().getByRole('button', { name: 'Step details' }).click()
  await expect(
    page.getByText('14 synthetic specimens; 6 displayed in this snapshot.'),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Previous view', exact: true }).click()
  await expect(page.getByTestId('view-position')).toHaveText('View 1 of 2')
  const pinned = await page
    .getByTestId('active-view')
    .getAttribute('data-view-id')
  expect(new URL(page.url()).searchParams.get('view')).toBe(pinned)
  await expect(page.getByText('6 of 14 rows shown')).toBeVisible()
  await page.reload()
  await expect(page.getByTestId('view-position')).toHaveText('View 1 of 2')
  await expect(page.getByTestId('active-view')).toHaveAttribute(
    'data-view-id',
    pinned!,
  )
  await send(page, 'Continue')
  await expect(page.getByTestId('view-position')).toHaveText('View 1 of 3')
  await expect(page.getByTestId('active-view')).toHaveAttribute(
    'data-view-id',
    pinned!,
  )
  await page.getByRole('button', { name: 'Latest view', exact: true }).click()
  await expect(page.getByTestId('view-position')).toHaveText('View 3 of 3')
  expect(new URL(page.url()).searchParams.has('view')).toBe(false)
  await expect(page.getByTestId('view-position')).toHaveText('View 4 of 4')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText(
    'Complete',
  )
  await expect(
    page.getByRole('button', { name: 'Next view', exact: true }),
  ).toBeDisabled()
  const snapshot = await (
    await request.get(`/api/sessions/${sessionId}/snapshot`)
  ).json()
  expect(
    await page
      .getByLabel('View history')
      .locator('option')
      .evaluateAll((options) =>
        options.map((option) => (option as HTMLOptionElement).value),
      ),
  ).toEqual(snapshot.views.map((view: { id: string }) => view.id))
  await page.getByLabel('View history').selectOption(snapshot.views[1].id)
  await expect(page.getByTestId('view-position')).toHaveText('View 2 of 4')
  await page.getByRole('button', { name: 'Next view', exact: true }).click()
  await expect(page.getByTestId('view-position')).toHaveText('View 3 of 4')
  await page.getByRole('button', { name: 'Latest view', exact: true }).click()
  const previous = await page.getByTestId('active-view').innerText()
  await page.screenshot({
    path: testInfo.outputPath('desktop-working-surface.png'),
      animations: 'disabled',
  })
  await send(page, '/invalid-view')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText(
    'Failed',
  )
  await expect(page.getByRole('alert')).toContainText('View schema error')
  await expect(page.getByTestId('view-position')).toHaveText('View 4 of 4')
  expect(await page.getByTestId('active-view').innerText()).toBe(previous)
  await expect(page.getByTestId('step-marker').last()).toContainText('Failed')
  expect(errors).toEqual([])
})

test('mobile working surface retains selection and both panels remain accessible', async ({
  page,
  request,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile')
  const sessionId = await createSession(request)
  await openSession(page, sessionId)
  await send(page, 'Show intake')
  await expect(page.getByTestId('conversation-turn-status')).toHaveText(
    'Complete',
  )
  await page.getByRole('tab', { name: /Working surface/ }).click()
  await expect(
    page.getByRole('heading', { name: 'Intake quality checks', exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Previous view', exact: true }).click()
  await expect(page.getByTestId('view-position')).toHaveText('View 1 of 2')
  await page.reload()
  await expect(
    page.getByRole('tab', { name: /Working surface/ }),
  ).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByTestId('view-position')).toHaveText('View 1 of 2')
  await expect(page.getByText('6 of 14 rows shown')).toBeVisible()
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 320, height: 568 },
  ]) {
    await page.setViewportSize(viewport)
    const layout = await page.evaluate(() => {
      const content = document
        .querySelector('[data-testid="active-view"]')!
        .getBoundingClientRect()
      const navigation = document
        .querySelector('nav[aria-label="View navigation"]')!
        .getBoundingClientRect()
      const scroll = document.querySelector('[data-testid="table-scroll"]')!
      return {
        noPageOverflow: document.documentElement.scrollWidth <= innerWidth,
        noOverlap: content.top >= navigation.bottom,
        bounded:
          content.left >= 0 &&
          content.right <= innerWidth &&
          content.bottom <= innerHeight,
        tableScrollable: scroll.scrollWidth > scroll.clientWidth,
      }
    })
    expect(layout).toEqual({
      noPageOverflow: true,
      noOverlap: true,
      bounded: true,
      tableScrollable: true,
    })
    await page.screenshot({
      path: testInfo.outputPath(`mobile-surface-${viewport.width}.png`),
        animations: 'disabled',
    })
  }
  await page.getByRole('tab', { name: 'Conversation', exact: true }).click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeVisible()
  await assertLayout(page)
  await page.getByRole('tab', { name: /Working surface/ }).click()
  await expect(page.getByTestId('view-position')).toHaveText('View 1 of 2')
})

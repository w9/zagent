import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { once } from 'node:events'
import { createServer, request as proxyRequest } from 'node:http'
import type { ServerResponse } from 'node:http'
import type { AddressInfo } from 'node:net'

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
      .querySelector('.composer')!
      .getBoundingClientRect()
    const header = document
      .querySelector('.chat-heading')!
      .getBoundingClientRect()
    const footer = document
      .querySelector('.composer-footer')!
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
    expect(await answer(page).textContent()).toBe(expected)
    expect(await answer(second).textContent()).toBe(expected)
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
    expect(await answer(second).textContent()).toBe(expected)
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
  expect(await answer(reopened).textContent()).toBe(expected)
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
  expect(await answer(page).textContent()).toBe(expected)
  await assertLayout(page)
  await page.screenshot({ path: testInfo.outputPath('mobile-complete.png') })
  await page.setViewportSize({ width: 320, height: 568 })
  await assertLayout(page)
  await page.screenshot({ path: testInfo.outputPath('mobile-small.png') })
})

// Visual checks for docs/DESIGN.md: every story at every viewport, in both themes.
// Run with `npm run test:design`; filter with `-- -g <story id>`.
/// <reference lib="dom" />
import { readFileSync } from 'node:fs'
import { AxeBuilder } from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { axeTags, themes, viewports } from '../../src/design/matrix.ts'

type Entry = { id: string; type: 'story' | 'docs' }
const index: { entries: Record<string, Entry> } = JSON.parse(
  readFileSync(new URL('../../storybook-static/index.json', import.meta.url), 'utf8'),
)
const stories = Object.values(index.entries).filter((entry) => entry.type === 'story')

/** LAYOUT-03, LAYOUT-04, A11Y-02 and MOTION-02, measured in the rendered page. */
function layoutProblems(page: Page, minTarget: number): Promise<string[]> {
  return page.evaluate((minTarget) => {
    const problems: string[] = []
    const describe = (element: Element) => {
      const text = (element.textContent ?? '').trim().replace(/\s+/g, ' ').slice(0, 40)
      return `<${element.tagName.toLowerCase()}>${text ? ` "${text}"` : ''}`
    }
    const root = document.documentElement
    if (root.scrollWidth > root.clientWidth + 1) {
      const wide = [...document.body.querySelectorAll('*')]
        .filter((element) => element.getBoundingClientRect().right > root.clientWidth + 1)
        .slice(0, 3)
      problems.push(`LAYOUT-03 page is ${root.scrollWidth}px wide in ${root.clientWidth}px: ${wide.map(describe).join(', ')}`)
    }
    for (const element of document.body.querySelectorAll('*')) {
      const style = getComputedStyle(element)
      const box = element.getBoundingClientRect()
      if (box.width <= 1 || box.height <= 1 || !(element.textContent ?? '').trim()) continue
      const clips = (overflow: string) => overflow === 'hidden' || overflow === 'clip'
      const clipped =
        (clips(style.overflowX) && element.scrollWidth > element.clientWidth + 1) ||
        (clips(style.overflowY) && element.scrollHeight > element.clientHeight + 1)
      if (clipped && !element.closest('[title]')) problems.push(`LAYOUT-04 ${describe(element)} clips its text`)
    }
    const interactive =
      'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab], ' +
      '[role=checkbox], [role=switch], [role=menuitem], [tabindex]:not([tabindex="-1"])'
    for (const element of document.body.querySelectorAll(interactive)) {
      const box = element.getBoundingClientRect()
      const style = getComputedStyle(element)
      if (box.width === 0 || style.visibility === 'hidden') continue
      // WCAG 2.5.8 exempts targets inside a sentence, and boxes whose label is the target.
      const inText = style.display.startsWith('inline') &&
        (element.parentElement?.textContent ?? '').trim().length > (element.textContent ?? '').trim().length
      if (inText || (element.matches('[type=checkbox], [type=radio]') && element.closest('label'))) {
        continue
      }
      if (box.width < minTarget || box.height < minTarget) {
        problems.push(`A11Y-02 ${describe(element)} is ${Math.round(box.width)}×${Math.round(box.height)}px, below ${minTarget}px`)
      }
    }
    const running = document.getAnimations().filter((animation) => animation.playState === 'running')
    if (running.length) problems.push(`MOTION-02 ${running.length} animations run with reduced motion`)
    return problems
  }, minTarget)
}

/** STATE-02: tabs through the story and checks each focused element for the focus ring. */
async function focusProblems(page: Page): Promise<string[]> {
  const problems: string[] = []
  const seen = new Set<string>()
  for (let step = 0; step < 40; step++) {
    await page.keyboard.press('Tab')
    const focused = await page.evaluate(() => {
      const element = document.activeElement
      // Focus inside an embedded app is that app's concern.
      if (!element || element === document.body || element.tagName === 'IFRAME') return null
      const style = getComputedStyle(element)
      return {
        key: element.outerHTML.slice(0, 120),
        name: `<${element.tagName.toLowerCase()}> "${(element.textContent ?? '').trim().slice(0, 30)}"`,
        ring: style.outlineStyle !== 'none' && Number.parseFloat(style.outlineWidth) >= 2,
      }
    })
    if (!focused || seen.has(focused.key)) break
    seen.add(focused.key)
    if (!focused.ring) problems.push(`STATE-02 no focus ring on ${focused.name}`)
  }
  return problems
}

async function axeProblems(page: Page): Promise<string[]> {
  const { violations } = await new AxeBuilder({ page }).include('#storybook-root').withTags(axeTags).analyze()
  return violations.map(
    (violation) => `A11Y-01 ${violation.id}: ${violation.help} (${violation.nodes.length}× e.g. ${violation.nodes[0].target})`,
  )
}

for (const viewport of viewports) {
  test.describe(viewport.name, () => {
    test.use({
      viewport: { width: viewport.width, height: viewport.height },
      hasTouch: viewport.touch,
      isMobile: viewport.touch,
    })

    for (const story of stories) {
      for (const theme of themes) {
        test(`${story.id} ${theme}`, async ({ page }) => {
          // a11y.manual stops the Storybook addon's own axe run, which would collide with ours.
          await page.goto(`/iframe.html?id=${story.id}&viewMode=story&globals=theme:${theme};a11y.manual:!true`)
          await page.locator('#storybook-root > *').first().waitFor()
          await page.evaluate(() => document.fonts.ready)
          await expect(page.locator('body.sb-show-errordisplay')).toHaveCount(0)
          await expect(page.locator('html')).toHaveAttribute('data-theme', theme)

          const coarse = await page.evaluate(() => matchMedia('(pointer: coarse)').matches)
          expect.soft(await layoutProblems(page, coarse ? 36 : 24)).toEqual([])
          expect.soft(await axeProblems(page)).toEqual([])
          // Screenshot unfocused, and before tabbing, which scrolls focused elements into view.
          await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
          await expect.soft(page).toHaveScreenshot([story.id, `${viewport.name}-${theme}.png`], { fullPage: true })
          if (viewport.name === 'desktop-1440') expect.soft(await focusProblems(page)).toEqual([])
        })
      }
    }
  })
}

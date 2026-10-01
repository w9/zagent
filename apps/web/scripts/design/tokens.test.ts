// @vitest-environment node
import { readFileSync } from 'node:fs'
import { beforeAll, describe, expect, test } from 'vitest'
import { contrast, inGamut, parseOklch } from './color.ts'
import type { Rgb } from './color.ts'
import { designDocPath, loadTailwind, readTokens, resolve, roles } from './tokens.ts'
import type { Theme } from './tokens.ts'

const tokens = readTokens()
const themes: Theme[] = ['light', 'dark']
const namespaces = ['background-color', 'text-color', 'border-color', 'outline-color'] as const

function color(name: string, theme: Theme): Rgb {
  const parsed = parseOklch(resolve(tokens, name, theme))
  if (!parsed) throw new Error(`${name} is not an oklch() color in ${theme}`)
  return parsed.rgb
}

// COLOR-05: which foregrounds may sit on which backgrounds. Keep in step with DESIGN.md 2.1.
const neutralBackgrounds = ['surface', 'subtle', 'muted', 'hover', 'selected', 'accent-subtle']
const statuses = ['danger', 'warning', 'info', 'success']
const statusBackgrounds = statuses.map((status) => `${status}-subtle`)
const textPairs: [string, string[]][] = [
  ['strong', [...neutralBackgrounds, ...statusBackgrounds, 'privacy-selected']],
  ['default', [...neutralBackgrounds, ...statusBackgrounds, 'privacy-selected']],
  ['muted', neutralBackgrounds],
  ['accent', neutralBackgrounds],
  ...statuses.map((status): [string, string[]] => [status, ['surface', 'subtle', `${status}-subtle`]]),
  ['on-accent', ['accent', 'accent-hover']],
  ['inverse', ['inverse']],
  ['privacy', ['privacy']],
]
const nonTextPairs: [string, string[]][] = [
  ['--border-color-control', ['surface', 'subtle']],
  ['--border-color-accent', ['surface', 'subtle']],
  ['--outline-color-focus', ['surface', 'subtle', 'muted']],
]
const exemptBackground = ['overlay']

describe('primitives', () => {
  test('every palette color is inside sRGB', () => {
    const outside = [...tokens.primitives].filter(([, value]) => {
      const parsed = parseOklch(value)
      return parsed && !inGamut(parsed.rgb)
    })
    expect(outside.map(([name]) => name)).toEqual([])
  })

  test('each ramp gets darker as its step number grows', () => {
    const ramps = new Map<string, [number, number][]>()
    for (const [name, value] of tokens.primitives) {
      const match = name.match(/^--([a-z]+)-(\d+)$/)
      const lightness = Number(value.match(/^oklch\(([\d.]+)/)?.[1])
      if (match && match[1] !== 'chart' && !Number.isNaN(lightness)) {
        ramps.set(match[1], [...(ramps.get(match[1]) ?? []), [Number(match[2]), lightness]])
      }
    }
    for (const [ramp, steps] of ramps) {
      const ordered = steps.toSorted((a, b) => a[0] - b[0]).map(([, lightness]) => lightness)
      expect(ordered, ramp).toEqual(ordered.toSorted((a, b) => b - a))
      expect(new Set(ordered).size, `${ramp} has duplicate lightness`).toBe(ordered.length)
    }
  })
})

describe('semantic colors', () => {
  test.each(themes)('every role resolves to a color in %s', (theme) => {
    for (const namespace of namespaces) {
      for (const role of roles(tokens, namespace)) {
        expect(parseOklch(resolve(tokens, `--${namespace}-${role}`, theme)), `${namespace}-${role}`).not.toBeNull()
      }
    }
  })

  test('the dark theme overrides every color role, and nothing else in @theme', () => {
    const colorRoles = [...tokens.theme.keys()].filter((name) => namespaces.some((n) => name.startsWith(`--${n}-`)))
    const darkRoles = [...tokens.dark.keys()].filter((name) => tokens.theme.has(name))
    expect(darkRoles.toSorted()).toEqual(colorRoles.toSorted())
  })

  test.each(themes)('COLOR-05 contrast in %s', (theme) => {
    const failures: string[] = []
    for (const [text, backgrounds] of textPairs) {
      for (const background of backgrounds) {
        const ratio = contrast(color(`--text-color-${text}`, theme), color(`--background-color-${background}`, theme))
        if (ratio < 4.5) failures.push(`text-${text} on bg-${background}: ${ratio.toFixed(2)} < 4.5`)
      }
    }
    for (const [name, backgrounds] of nonTextPairs) {
      for (const background of backgrounds) {
        const ratio = contrast(color(name, theme), color(`--background-color-${background}`, theme))
        if (ratio < 3) failures.push(`${name} on bg-${background}: ${ratio.toFixed(2)} < 3`)
      }
    }
    expect(failures).toEqual([])
  })

  test('the contrast policy covers every text and background role', () => {
    const coveredText = new Set(textPairs.map(([text]) => text))
    const coveredBackground = new Set(textPairs.flatMap(([, backgrounds]) => backgrounds))
    expect(roles(tokens, 'text-color').filter((role) => !coveredText.has(role))).toEqual([])
    expect(
      roles(tokens, 'background-color').filter((role) => !coveredBackground.has(role) && !exemptBackground.includes(role)),
    ).toEqual([])
  })
})

describe('scales', () => {
  test('type sizes grow, carry a line height and stay at 11px or above', () => {
    const sizes = [...tokens.theme].filter(([name]) => /^--text-[\w]+$/.test(name))
    const pixels = sizes.map(([, value]) => Number.parseFloat(value))
    expect(pixels).toEqual(pixels.toSorted((a, b) => a - b))
    expect(Math.min(...pixels)).toBeGreaterThanOrEqual(11)
    for (const [name, value] of sizes) {
      const lineHeight = Number.parseFloat(tokens.theme.get(`${name}--line-height`) ?? '0')
      expect(lineHeight, `${name}--line-height`).toBeGreaterThanOrEqual(Number.parseFloat(value) * 1.2)
    }
  })

  test('spacing step N is N × 4px', () => {
    const steps = [...tokens.theme].filter(([name]) => name.startsWith('--spacing-'))
    for (const [name, value] of steps) {
      expect(value, name).toBe(`${Number(name.slice('--spacing-'.length)) * 4}px`)
    }
  })
})

describe('Tailwind theme', () => {
  let toCss: (classes: string[]) => (string | null)[]
  beforeAll(async () => {
    const system = await loadTailwind()
    toCss = (classes) => system.candidatesToCss(classes)
  })

  const present = [
    'bg-surface', 'text-muted', 'border-control', 'outline-focus', 'divide-subtle', 'text-base', 'font-semibold',
    'font-mono', 'tracking-caps', 'p-0.5', 'gap-1.5', 'h-control', 'size-icon', 'w-sidebar', 'max-w-prose',
    'rounded-md', 'shadow-md', 'animate-enter', 'tablet:flex', 'ultra:grid', '@medium:grid-cols-2',
  ]
  const absent = [
    'text-gray-500', 'bg-white', 'text-surface', 'bg-strong', 'border-surface', 'p-7', 'gap-2.5', 'text-10',
    'text-sm/6', 'font-bold', 'font-light', 'rounded', 'rounded-xl', 'shadow-xl', 'animate-bounce', 'sm:flex',
    'lg:grid', 'max-w-md', 'leading-7', 'tracking-wide',
  ]

  test('token utilities exist', () => {
    const css = toCss(present)
    expect(present.filter((_, index) => !css[index])).toEqual([])
  })

  test('utilities outside the system do not exist', () => {
    const css = toCss(absent)
    expect(absent.filter((_, index) => css[index])).toEqual([])
  })
})

describe('DESIGN.md', () => {
  const doc = readFileSync(designDocPath, 'utf8')
  const section = (start: string, end: string) => doc.slice(doc.indexOf(start), doc.indexOf(end, doc.indexOf(start)))

  test.each([
    ['background-color', '| Background', '| Text'],
    ['text-color', '| Text', '| Border'],
    ['border-color', '| Border', '### 2.2'],
  ])('documents every %s role', (namespace, start, end) => {
    const table = section(start, end)
    expect(roles(tokens, namespace).filter((role) => !table.includes(`\`${role}\``))).toEqual([])
  })

  test('documents every type size', () => {
    const table = section('### 2.2', '### 2.3')
    const sizes = [...tokens.theme.keys()].filter((name) => /^--text-[\w]+$/.test(name))
    expect(sizes.filter((name) => !table.includes(`\`text-${name.slice('--text-'.length)}\``))).toEqual([])
  })
})

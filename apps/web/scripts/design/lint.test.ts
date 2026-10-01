// @vitest-environment node
import { readFileSync } from 'node:fs'
import { beforeAll, expect, test } from 'vitest'
import { lint } from './lint.ts'
import type { ClassChecker } from './lint.ts'
import { designDocPath, loadTailwind } from './tokens.ts'

let checkClasses: ClassChecker
beforeAll(async () => {
  const system = await loadTailwind()
  checkClasses = (classes) => system.candidatesToCss(classes)
})

const component = 'src/components/example.tsx'
const icon = "import { X } from 'lucide-react'\n"

// [description, file, source, expected rule IDs]
const cases: [string, string, string, string[]][] = [
  ['token utilities pass', component, '<div className="flex gap-2 bg-surface p-4 text-muted" />', []],
  ['raw color string', component, "const ink = '#2f6149'", ['TOKEN-01']],
  ['raw color function', component, "const ink = 'oklch(0.5 0.1 165)'", ['TOKEN-01']],
  ['raw length string', component, "const width = '280px'", ['TOKEN-01']],
  ['inline style number', component, '<div style={{ width: 280 }} />', ['TOKEN-01']],
  ['inline style token', component, "<div style={{ background: 'var(--chart-1)' }} />", []],
  ['raw value in design CSS', 'src/design/base.css', 'html { color: #fff; }', ['TOKEN-01']],
  ['raw value in tokens.css', 'src/design/tokens.css', ':root { --x: #fff; }', []],
  ['unknown class', component, '<div className="text-gray-500" />', ['TOKEN-02']],
  ['group marker', component, '<div className="group" />', []],
  ['arbitrary value', component, '<div className="p-[13px]" />', ['TOKEN-03']],
  ['important modifier', component, '<div className="!p-2" />', ['TOKEN-03']],
  ['grid template with fr', 'src/components/shell/app-shell.tsx', '<div className="grid-cols-[minmax(0,5fr)_minmax(0,7fr)]" />', []],
  ['grid template with px', 'src/components/shell/app-shell.tsx', '<div className="grid-cols-[200px_1fr]" />', ['TOKEN-03']],
  ['arbitrary breakpoint', component, '<div className="min-[900px]:flex" />', ['TOKEN-03']],
  ['data attribute variant', component, '<div className="data-[state=open]:bg-selected" />', []],
  ['interpolated class', component, '<div className={`bg-${tone}`} />', ['TOKEN-04']],
  ['concatenated class', component, "<div className={'bg-' + tone} />", ['TOKEN-04']],
  ['conditional literal', component, "<div className={`p-2 ${active ? 'bg-selected' : 'bg-surface'}`} />", []],
  ['opacity modifier', component, '<div className="bg-accent/10" />', ['COLOR-02']],
  ['fraction width', component, '<div className="w-1/2" />', []],
  ['serif in a component', component, '<h2 className="font-serif" />', ['TYPE-01']],
  ['serif in the wordmark', 'src/components/shell/wordmark.tsx', '<h1 className="font-serif" />', []],
  ['viewport variant in a component', component, '<div className="tablet:flex" />', ['LAYOUT-02']],
  ['viewport variant in the shell', 'src/components/shell/app-shell.tsx', '<div className="tablet:flex" />', []],
  ['container query', component, '<div className="@medium:flex" />', []],
  ['unlisted stacking level', component, '<div className="z-20" />', ['LAYOUT-05']],
  ['listed stacking level', component, '<div className="z-50" />', []],
  ['duration', component, '<div className="duration-300" />', ['MOTION-01']],
  ['easing', component, '<div className="ease-out" />', ['MOTION-01']],
  ['opacity', component, '<div className="opacity-40" />', ['STATE-03']],
  ['disabled opacity', component, '<button className="disabled:opacity-50">Go</button>', []],
  ['dark variant', component, '<div className="dark:bg-surface" />', ['THEME-02']],
  ['data-theme outside the theme module', component, '<div data-theme="dark" />', ['THEME-02']],
  ['media query outside the theme module', 'src/lib/x.ts', "matchMedia('(prefers-color-scheme: dark)')", ['THEME-02']],
  ['media query in the theme module', 'src/lib/theme.ts', "matchMedia('(prefers-color-scheme: dark)')", []],
  ['component CSS file', 'src/components/example.css', '.x { display: flex; }', ['COMP-04']],
  ['icon-only button', component, `${icon}<button aria-label="Close"><X /></button>`, ['A11Y-03']],
  ['icon and text button', component, `${icon}<button><X />Close</button>`, []],
  ['icon-only button in IconButton', 'src/components/ui/icon-button.tsx', `${icon}<button><X /></button>`, []],
  ['icon size prop', component, `${icon}<X size={16} />`, ['ICON-01']],
  ['other icon package', component, "import { FaX } from 'react-icons/fa'", ['ICON-01']],
  ['three dots in text', component, '<p>Loading...</p>', ['CONTENT-01']],
  ['three dots in an attribute', component, '<input placeholder="Search..." />', ['CONTENT-01']],
  ['ellipsis character', component, '<p>Loading…</p>', []],
  [
    'cva classes but not variant names',
    component,
    "cva('px-3', { variants: { tone: { bad: 'text-gray-500' } }, compoundVariants: [{ tone: 'bad', class: 'bg-white' }], defaultVariants: { tone: 'bad' } })",
    ['TOKEN-02', 'TOKEN-02'],
  ],
  ['cn object keys', component, "cn({ 'bg-white': active })", ['TOKEN-02']],
  ['className property in data', component, "const rows = [{ className: 'bg-white' }]", ['TOKEN-02']],
  ['user-facing text is not a class', component, "const label = 'Sticky header row'", []],
]

test.each(cases)('%s', (_, file, text, expected) => {
  const rules = lint([{ file, text }], checkClasses).map((finding) => finding.rule)
  expect(rules.toSorted()).toEqual(expected.toSorted())
})

test('findings point at the offending class', () => {
  const [finding] = lint([{ file: component, text: '\n  <div className="flex text-gray-500" />' }], checkClasses)
  expect([finding.line, finding.column]).toEqual([2, 24])
})

test('the [lint] rules in DESIGN.md are exactly the rules the linter reports and the cases cover', () => {
  const doc = readFileSync(designDocPath, 'utf8')
  const documented = [...doc.matchAll(/^- \*\*([A-Z0-9]+-\d{2})\*\*[\s\S]*?(?=^- \*\*|^#|^$)/gm)]
    .filter(([bullet]) => bullet.includes('`[lint]`'))
    .map(([, id]) => id)
    .toSorted()
  const source = readFileSync(new URL('./lint.ts', import.meta.url), 'utf8')
  const implemented = [...new Set([...source.matchAll(/'([A-Z0-9]+-\d{2})'/g)].map(([, id]) => id))].toSorted()
  const covered = [...new Set(cases.flatMap(([, , , expected]) => expected))].toSorted()
  expect(implemented).toEqual(documented)
  expect(covered).toEqual(documented)
})

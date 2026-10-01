import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { __unstable__loadDesignSystem } from 'tailwindcss'

export const webRoot = fileURLToPath(new URL('../../', import.meta.url))
export const tokensPath = path.join(webRoot, 'src/design/tokens.css')
export const stylesPath = path.join(webRoot, 'src/design/styles.css')
export const designDocPath = path.join(webRoot, '../../docs/DESIGN.md')

export type Theme = 'light' | 'dark'
export type Tokens = {
  primitives: Map<string, string>
  theme: Map<string, string>
  dark: Map<string, string>
}

function block(css: string, header: string): string {
  const start = css.indexOf(header)
  if (start < 0) throw new Error(`tokens.css has no "${header}" block`)
  let depth = 0
  for (let index = css.indexOf('{', start); index < css.length; index++) {
    if (css[index] === '{') depth++
    else if (css[index] === '}' && --depth === 0) return css.slice(css.indexOf('{', start) + 1, index)
  }
  throw new Error(`Unclosed "${header}" block`)
}

function declarations(body: string): Map<string, string> {
  const flat = body.replace(/@keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}/g, '')
  const entries = [...flat.matchAll(/(--[\w\\.-]+)\s*:\s*([^;]+);/g)]
  return new Map(entries.map(([, name, value]) => [name.replaceAll('\\', ''), value.trim()]))
}

export function readTokens(css = readFileSync(tokensPath, 'utf8')): Tokens {
  const source = css.replace(/\/\*[\s\S]*?\*\//g, '')
  return {
    primitives: declarations(block(source, ':root {')),
    theme: declarations(block(source, '@theme static {')),
    dark: declarations(block(source, "[data-theme='dark'] {")),
  }
}

/** Follows var() references to the literal value a property has in the given theme. */
export function resolve(tokens: Tokens, name: string, theme: Theme): string {
  const value =
    (theme === 'dark' ? tokens.dark.get(name) : undefined) ?? tokens.theme.get(name) ?? tokens.primitives.get(name)
  if (value === undefined) throw new Error(`${name} is not defined`)
  const reference = value.match(/^var\((--[\w-]+)\)$/)
  return reference ? resolve(tokens, reference[1], theme) : value
}

/** Names of the semantic roles in one color namespace, e.g. "text-color" gives strong, default, … */
export function roles(tokens: Tokens, namespace: string): string[] {
  const prefix = `--${namespace}-`
  return [...tokens.theme.keys()].filter((name) => name.startsWith(prefix)).map((name) => name.slice(prefix.length))
}

/** Tailwind compiled with the app stylesheet: the authority on which classes exist. */
export async function loadTailwind() {
  const tailwindRoot = path.join(webRoot, 'node_modules/tailwindcss')
  return __unstable__loadDesignSystem(readFileSync(stylesPath, 'utf8'), {
    base: path.dirname(stylesPath),
    async loadStylesheet(id, base) {
      const file =
        id === 'tailwindcss'
          ? path.join(tailwindRoot, 'index.css')
          : id.startsWith('tailwindcss/')
            ? path.join(tailwindRoot, id.slice('tailwindcss/'.length))
            : path.resolve(base, id)
      return { path: file, base: path.dirname(file), content: readFileSync(file, 'utf8') }
    },
  })
}

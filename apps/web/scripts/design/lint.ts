// Lexical checks for docs/DESIGN.md. Usage: node scripts/design/lint.ts [--summary] [paths…]
import { readFileSync, readdirSync, statSync } from 'node:fs'
import path from 'node:path'
import ts from 'typescript'
import { loadTailwind, webRoot } from './tokens.ts'

export type Finding = { file: string; line: number; column: number; rule: string; message: string }
export type SourceFile = { file: string; text: string }
export type ClassChecker = (classes: string[]) => (string | null)[]
type Reporter = (line: number, column: number, rule: string, message: string) => void

// Files allowed to break one rule, relative to apps/web. A trailing slash allows a directory.
const allow = {
  serif: ['src/components/shell/wordmark.tsx', 'src/components/ui/empty-state.tsx', 'src/design/specimen.tsx'],
  viewport: ['src/components/shell/'],
  theme: ['src/lib/theme.ts', '.storybook/'],
  iconOnly: ['src/components/ui/icon-button.tsx'],
}
const isAllowed = (list: string[], file: string) =>
  list.some((entry) => (entry.endsWith('/') ? file.startsWith(entry) : file === entry))

const classFunctions = new Set(['cn', 'clsx', 'cx'])
const classProperty = /^(class|className|\w+ClassNames?)$/
const iconPackages = /^(react-icons|@heroicons\/|@radix-ui\/react-icons|@tabler\/|@phosphor-icons\/|@fortawesome\/)/
const rawColor = /(^|[^\w&])#(?:[\da-f]{3,4}|[\da-f]{6}|[\da-f]{8})(?![\w-])|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color-mix)\(/i
const rawLength = /(^|[^\w.$-])-?(?:\d+\.?\d*|\.\d+)(?:px|rem|em|vh|vw|dvh|svh|lvh|ms|pt)\b/
const ellipsis = /[A-Za-z]\.\.\.(?![.\w])/
const gridTemplate = /^grid-(cols|rows)-\[(.+)\]$/
const opacityModifier =
  /^-?(bg|text|border(-[xytrblse])?|outline|ring|divide(-[xy])?|fill|stroke|decoration|placeholder|caret|accent|shadow|inset-shadow|inset-ring|drop-shadow|from|via|to)-.+\/[^/]+$/
const viewportVariant = /^(max-|min-)?(tablet|desktop|wide|ultra)$/
const stackingLevels = new Set(['z-0', 'z-10', 'z-30', 'z-40', 'z-50', 'z-auto'])

type ClassLiteral = { text: string; start: number }

/** Splits "hover:tablet:bg-[x]" into variants and utility, ignoring colons inside brackets. */
function splitVariants(token: string): string[] {
  const parts: string[] = []
  let depth = 0
  let current = ''
  for (const char of token) {
    if (char === '[' || char === '(') depth++
    if (char === ']' || char === ')') depth--
    if (char === ':' && depth === 0) {
      parts.push(current)
      current = ''
    } else current += char
  }
  return [...parts, current]
}

function gridTemplateAllowed(utility: string): boolean {
  const match = utility.match(gridTemplate)
  if (!match) return false
  const rest = match[2]
    .replace(/var\(--[\w-]+\)/g, '')
    .replace(/minmax|repeat|auto|min-content|max-content|\d+(\.\d+)?fr/g, '')
    .replace(/\b0\b/g, '')
  return /^[_,()]*$/.test(rest)
}

/** Rules that apply to one class token, apart from whether Tailwind knows it. */
function classRules(token: string, file: string): [string, string][] {
  const problems: [string, string][] = []
  const important = token.startsWith('!') || token.endsWith('!')
  const parts = splitVariants(token.replace(/^!|!$/g, ''))
  const utility = parts.at(-1)!
  const variants = parts.slice(0, -1)
  const name = utility.replace(/^-/, '')
  if (important) problems.push(['TOKEN-03', `"${token}" uses the important modifier`])
  if (/[[(]/.test(utility) && !gridTemplateAllowed(utility)) {
    problems.push(['TOKEN-03', `"${token}" is an arbitrary value; use a token utility`])
  }
  if (variants.some((variant) => /^@?(min|max)-[[(]/.test(variant))) {
    problems.push(['TOKEN-03', `"${token}" uses an arbitrary breakpoint`])
  }
  if (opacityModifier.test(utility)) problems.push(['COLOR-02', `"${token}" changes a token's opacity`])
  if (name === 'font-serif' && !isAllowed(allow.serif, file)) {
    problems.push(['TYPE-01', 'font-serif is only for the wordmark and empty-state headlines'])
  }
  if (variants.some((variant) => viewportVariant.test(variant)) && !isAllowed(allow.viewport, file)) {
    problems.push(['LAYOUT-02', `"${token}" uses a viewport variant; use a container query`])
  }
  if (/^z-/.test(name) && !stackingLevels.has(utility)) {
    problems.push(['LAYOUT-05', `"${token}" is not an allowed stacking level`])
  }
  if (/^(duration|delay|ease)-/.test(name)) problems.push(['MOTION-01', `"${token}" sets timing; use the motion tokens`])
  if (/^opacity-/.test(name)) {
    const disabled = utility === 'opacity-50' && variants.some((variant) => variant.includes('disabled'))
    if (!['opacity-0', 'opacity-100'].includes(utility) && !disabled) {
      problems.push(['STATE-03', `"${token}" is not allowed; opacity is only for disabled (disabled:opacity-50)`])
    }
  }
  if (variants.includes('dark')) problems.push(['THEME-02', `"${token}" branches on theme; tokens handle dark mode`])
  return problems
}

function propertyName(node: ts.ObjectLiteralElementLike): string | undefined {
  return node.name && (ts.isIdentifier(node.name) || ts.isStringLiteral(node.name)) ? node.name.text : undefined
}

function lintScript(source: SourceFile, reportAt: Reporter) {
  const { file, text } = source
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const report = (position: number, rule: string, message: string) => {
    const { line, character } = sf.getLineAndCharacterOfPosition(position)
    reportAt(line + 1, character + 1, rule, message)
  }
  const literals = new Map<number, ClassLiteral>()
  const icons = new Set<string>()
  const add = (
    node: ts.StringLiteral | ts.NoSubstitutionTemplateLiteral | ts.TemplateLiteralLikeNode,
    gluedStart = false,
    gluedEnd = false,
  ) => {
    const start = node.getStart(sf) + 1
    // A fragment glued to ${} is reported as TOKEN-04, not as an unknown class.
    const text = node.text.replace(gluedStart ? /^\S+/ : /^$/, (fragment) => ' '.repeat(fragment.length))
    literals.set(start, { text: gluedEnd ? text.replace(/\S+$/, '') : text, start })
  }

  // Collects class strings from an expression in a class context.
  const collect = (node: ts.Node | undefined): void => {
    if (!node) return
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) add(node)
    else if (ts.isTemplateExpression(node)) {
      const glued = node.templateSpans.map((span, index) => {
        const before = index === 0 ? node.head.text : node.templateSpans[index - 1].literal.text
        return /\S$/.test(before) || /^\S/.test(span.literal.text)
      })
      add(node.head, false, glued[0])
      node.templateSpans.forEach((span, index) => {
        add(span.literal, glued[index], glued[index + 1] ?? false)
        if (glued[index]) {
          report(span.expression.getStart(sf), 'TOKEN-04', 'Class name built with ${}; write complete class strings')
        }
        collect(span.expression)
      })
    } else if (ts.isParenthesizedExpression(node) || ts.isJsxExpression(node)) collect(node.expression)
    else if (ts.isArrowFunction(node) && !ts.isBlock(node.body)) collect(node.body)
    else if (ts.isConditionalExpression(node)) {
      collect(node.whenTrue)
      collect(node.whenFalse)
    } else if (ts.isBinaryExpression(node)) {
      if (node.operatorToken.kind === ts.SyntaxKind.PlusToken) {
        report(node.getStart(sf), 'TOKEN-04', 'Class name built with +; write complete class strings')
        return
      }
      if (node.operatorToken.kind !== ts.SyntaxKind.AmpersandAmpersandToken) collect(node.left)
      collect(node.right)
    } else if (ts.isArrayLiteralExpression(node)) node.elements.forEach(collect)
    else if (ts.isObjectLiteralExpression(node)) {
      for (const property of node.properties) {
        if (ts.isPropertyAssignment(property) && ts.isStringLiteral(property.name)) add(property.name)
      }
    }
  }

  // A `…ClassNames` map holds classes in its values; anything else named like a class is a class list.
  const collectNamed = (node: ts.Expression): void => {
    if (!ts.isObjectLiteralExpression(node)) return collect(node)
    for (const property of node.properties) {
      if (ts.isPropertyAssignment(property)) collectNamed(property.initializer)
    }
  }

  const collectCva = (call: ts.CallExpression) => {
    const [base, config] = call.arguments
    collect(base)
    if (!config || !ts.isObjectLiteralExpression(config)) return
    for (const property of config.properties) {
      if (!ts.isPropertyAssignment(property)) continue
      const key = propertyName(property)
      if (key === 'variants' && ts.isObjectLiteralExpression(property.initializer)) {
        for (const group of property.initializer.properties) {
          if (ts.isPropertyAssignment(group) && ts.isObjectLiteralExpression(group.initializer)) {
            for (const option of group.initializer.properties) {
              if (ts.isPropertyAssignment(option)) collect(option.initializer)
            }
          }
        }
      }
      if (key === 'compoundVariants' && ts.isArrayLiteralExpression(property.initializer)) {
        for (const element of property.initializer.elements) {
          if (!ts.isObjectLiteralExpression(element)) continue
          for (const option of element.properties) {
            if (ts.isPropertyAssignment(option) && ['class', 'className'].includes(propertyName(option) ?? '')) {
              collect(option.initializer)
            }
          }
        }
      }
    }
  }

  const tagName = (node: ts.JsxOpeningLikeElement) => node.tagName.getText(sf)

  // Pass 1: class contexts and icon imports. The raw-value check in pass 2 skips class strings.
  const visitClassContexts = (node: ts.Node): void => {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      const bindings = node.importClause?.namedBindings
      if (node.moduleSpecifier.text === 'lucide-react' && bindings && ts.isNamedImports(bindings)) {
        bindings.elements.forEach((element) => icons.add(element.name.text))
      }
    }
    if (ts.isJsxAttribute(node) && classProperty.test(node.name.getText(sf))) collect(node.initializer)
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression)) {
      if (node.expression.text === 'cva') collectCva(node)
      else if (classFunctions.has(node.expression.text)) node.arguments.forEach(collect)
    }
    if ((ts.isPropertyAssignment(node) || ts.isVariableDeclaration(node)) && node.initializer) {
      const name = ts.isPropertyAssignment(node) ? propertyName(node) : node.name.getText(sf)
      if (name && classProperty.test(name)) collectNamed(node.initializer)
    }
    ts.forEachChild(node, visitClassContexts)
  }

  // Pass 2: everything else.
  const visit = (node: ts.Node): void => {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      const module = node.moduleSpecifier.text
      if (iconPackages.test(module)) report(node.getStart(sf), 'ICON-01', `Icons come from lucide-react, not ${module}`)
      return
    }
    if (ts.isJsxAttribute(node)) {
      const name = node.name.getText(sf)
      if (name === 'data-theme' && !isAllowed(allow.theme, file)) {
        report(node.getStart(sf), 'THEME-02', 'Only the theme module sets data-theme')
      }
      if (name === 'style' && node.initializer && ts.isJsxExpression(node.initializer)) {
        const style = node.initializer.expression
        if (style && ts.isObjectLiteralExpression(style)) {
          for (const property of style.properties) {
            if (!ts.isPropertyAssignment(property)) continue
            const value = property.initializer
            const raw =
              (ts.isNumericLiteral(value) && value.text !== '0') ||
              (ts.isStringLiteral(value) && !value.text.startsWith('var(--'))
            if (raw) report(value.getStart(sf), 'TOKEN-01', 'Inline style with a raw value; use a token')
          }
        }
      }
    }
    if (ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) {
      if (icons.has(tagName(node))) {
        for (const attribute of node.attributes.properties) {
          const name = ts.isJsxAttribute(attribute) ? attribute.name.getText(sf) : ''
          if (['size', 'strokeWidth', 'absoluteStrokeWidth', 'color'].includes(name)) {
            report(attribute.getStart(sf), 'ICON-01', `Icon "${name}" prop; size with size-icon* and color with text-*`)
          }
        }
      }
    }
    if (ts.isJsxElement(node) && ['button', 'Button'].includes(tagName(node.openingElement))) {
      const children = node.children.filter((child) => !(ts.isJsxText(child) && !child.text.trim()))
      const iconOnly =
        children.length > 0 &&
        children.every(
          (child) => (ts.isJsxSelfClosingElement(child) || ts.isJsxElement(child)) &&
            icons.has(tagName(ts.isJsxElement(child) ? child.openingElement : child)),
        )
      if (iconOnly && !isAllowed(allow.iconOnly, file)) {
        report(node.getStart(sf), 'A11Y-03', 'Icon-only button; use IconButton, which adds the label and tooltip')
      }
    }
    if (ts.isJsxText(node) && ellipsis.test(node.text)) {
      report(node.getStart(sf), 'CONTENT-01', 'Use the ellipsis character "…"')
    }
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isTemplateLiteralToken(node)) {
      const value = node.text
      const position = node.getStart(sf) + 1
      if (ellipsis.test(value)) report(position, 'CONTENT-01', 'Use the ellipsis character "…"')
      if (value.includes('prefers-color-scheme') && !isAllowed(allow.theme, file)) {
        report(position, 'THEME-02', 'Only the theme module reads prefers-color-scheme')
      }
      if (!literals.has(position) && (rawColor.test(value) || rawLength.test(value))) {
        report(position, 'TOKEN-01', `Raw design value in "${value.slice(0, 40)}"; use a token`)
      }
    }
    ts.forEachChild(node, visit)
  }

  visitClassContexts(sf)
  visit(sf)
  return { sf, literals: [...literals.values()] }
}

function lintStyles(source: SourceFile, report: Reporter) {
  const { file, text } = source
  if (!file.startsWith('src/design/')) {
    report(1, 1, 'COMP-04', 'Component CSS file; style with utilities (only src/design/*.css may exist)')
    return
  }
  if (file === 'src/design/tokens.css') return
  const lines = text.replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, ' ')).split('\n')
  lines.forEach((line, index) => {
    if (rawColor.test(line) || rawLength.test(line)) {
      report(index + 1, 1, 'TOKEN-01', `Raw design value in "${line.trim().slice(0, 60)}"; use a token`)
    }
  })
}

export function lint(sources: SourceFile[], checkClasses: ClassChecker): Finding[] {
  const findings: Finding[] = []
  const pending: { file: string; sf: ts.SourceFile; token: string; position: number }[] = []
  for (const source of sources) {
    const reportAt: Reporter = (line, column, rule, message) =>
      findings.push({ file: source.file, line, column, rule, message })
    if (source.file.endsWith('.css')) {
      lintStyles(source, reportAt)
      continue
    }
    const { sf, literals } = lintScript(source, reportAt)
    for (const literal of literals) {
      for (const match of literal.text.matchAll(/\S+/g)) {
        const position = literal.start + match.index
        pending.push({ file: source.file, sf, token: match[0], position })
        const { line, character } = sf.getLineAndCharacterOfPosition(position)
        for (const [rule, message] of classRules(match[0], source.file)) reportAt(line + 1, character + 1, rule, message)
      }
    }
  }
  const checkable = pending.filter(({ token }) => {
    const utility = splitVariants(token.replace(/^!|!$/g, '')).at(-1)!
    return !/^(group|peer)(\/[\w-]+)?$/.test(token) && !(/[[(]/.test(utility) && !gridTemplateAllowed(utility))
  })
  const unique = [...new Set(checkable.map(({ token }) => token))]
  const compiled = new Map(checkClasses(unique).map((css, index) => [unique[index], css]))
  for (const { file, sf, token, position } of checkable) {
    if (compiled.get(token)) continue
    const { line, character } = sf.getLineAndCharacterOfPosition(position)
    findings.push({ file, line: line + 1, column: character + 1, rule: 'TOKEN-02', message: `Unknown class "${token}"` })
  }
  return findings.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line || a.column - b.column)
}

function sourceFiles(target: string): string[] {
  const absolute = path.resolve(webRoot, target)
  if (statSync(absolute).isFile()) return [absolute]
  return readdirSync(absolute, { recursive: true, encoding: 'utf8' })
    .map((entry) => path.join(absolute, entry))
    .filter((entry) => /\.(tsx?|css)$/.test(entry) && !/\.(test\.tsx?|d\.ts)$/.test(entry) && statSync(entry).isFile())
}

if (import.meta.main) {
  const args = process.argv.slice(2)
  const summary = args.includes('--summary')
  const targets = args.filter((arg) => !arg.startsWith('--'))
  const files = (targets.length ? targets : ['src']).flatMap(sourceFiles)
  const sources = files.map((file) => ({ file: path.relative(webRoot, file), text: readFileSync(file, 'utf8') }))
  const system = await loadTailwind()
  const findings = lint(sources, (classes) => system.candidatesToCss(classes))
  if (!summary) {
    for (const { file, line, column, rule, message } of findings) console.log(`${file}:${line}:${column} ${rule} ${message}`)
  }
  const count = (key: (finding: Finding) => string) => {
    const counts = new Map<string, number>()
    for (const finding of findings) counts.set(key(finding), (counts.get(key(finding)) ?? 0) + 1)
    return [...counts].map(([name, total]) => `  ${name}: ${total}`).sort().join('\n')
  }
  if (summary && findings.length) console.log(`By rule:\n${count((f) => f.rule)}\nBy file:\n${count((f) => f.file)}`)
  console.log(findings.length ? `\n${findings.length} design problems in ${sources.length} files` : `Design lint: ${sources.length} files clean`)
  process.exitCode = findings.length ? 1 : 0
}

# Zagent design system

The rulebook for `apps/web` and the embedded MCP apps. It is written for people and coding agents
alike: every rule has an ID, and a tag that says how it is checked.

| Artifact | Owns | File |
|---|---|---|
| Tokens | Every raw value: colors, sizes, spacing, radii, shadows, motion, breakpoints | [tokens.css](../apps/web/src/design/tokens.css) |
| Rulebook | How tokens and components may be used | This file |
| Stories | What each component looks like in every variant, state and theme | `apps/web/src/**/*.stories.tsx` |

Values live only in `tokens.css`; this file names tokens but never repeats their values.

**Tags.** `[lint]` lexical check over source files. `[test]` unit test over tokens or behavior.
`[visual]` Playwright run over every story, viewport and theme. `[review]` judgment; written as a
concrete checklist item. Commands are in [Verification](#9-verification).

---

## 1. Principles

1. **Content first, chrome quiet.** Clinical data and the conversation carry the color and weight.
   Panels, borders and navigation recede.
2. **Color means something.** Accent marks action, selection and focus. Status colors mark status.
   Nothing is colored for decoration.
3. **Dense, not cramped.** Small type and tight rows are fine when alignment, rhythm and contrast
   are exact.
4. **Every state is designed.** Loading, empty, error, streaming, disabled, long content and narrow
   containers are part of the component, not afterthoughts.
5. **Consistent by construction.** If a value is not a token, it cannot be written.

---

## 2. Tokens

The theme is reset (`--*: initial`), so Tailwind's default palette, sizes and spacing do not exist.
Only the utilities below compile.

### 2.1 Color roles

Color namespaces are role-scoped: `bg-surface` exists, `text-surface` does not.

| Background `bg-*` | Use for |
|---|---|
| `surface` | Main panels, cards, inputs, popovers |
| `subtle` | Recessed areas: sidebar, working surface, table headers |
| `muted` | Inline code, neutral badges, tracks |
| `hover` | Hover on any neutral item or row |
| `selected` | The current item in a list (session, tab, row) |
| `inverse` | Tooltips |
| `overlay` | Scrim behind drawers and dialogs |
| `accent`, `accent-hover` | Primary action buttons only |
| `accent-subtle` | Quiet accent fill (active filter, highlighted row) |
| `danger-subtle`, `warning-subtle`, `info-subtle`, `success-subtle` | Status containers |
| `privacy`, `privacy-selected` | Privacy tokens only |

| Text `text-*` | Use for |
|---|---|
| `strong` | Headings, selected labels, values that must stand out |
| `default` | Body text and UI labels |
| `muted` | Secondary text, metadata, placeholders, inactive icons |
| `inverse` | Text on `bg-inverse` |
| `on-accent` | Text and icons on `bg-accent` |
| `accent` | Links, active navigation |
| `danger`, `warning`, `info`, `success` | Status text and icons |
| `privacy` | Text inside a privacy token |

| Border `border-*`, `divide-*` | Use for |
|---|---|
| `subtle` | Panel dividers, table row lines (the default border color) |
| `default` | Cards, secondary buttons, containers |
| `strong` | Hover on bordered containers |
| `control` | Form control boundaries: inputs, selects, checkboxes |
| `accent` | Selected and active indicators |
| `danger`, `warning`, `info`, `success`, `privacy` | Matching status containers |

`outline-focus` is the focus ring color. Charts read `--chart-1` … `--chart-6` at runtime.

### 2.2 Typography

| Utility | Use for |
|---|---|
| `text-xs` | Mono metadata, eyebrow labels, badges, table headers, timestamps |
| `text-sm` | Secondary text, table cells, form labels, sidebar items |
| `text-base` | Default UI text, buttons, inputs |
| `text-md` | Conversation prose (messages, Markdown) |
| `text-lg` | Section and panel titles |
| `text-xl` | View titles on the working surface |
| `text-2xl` | Serif display: wordmark and empty-state headlines |

Each size carries its line height. Weights: `font-normal`, `font-medium`, `font-semibold`.
Families: `font-sans` (default), `font-mono`, `font-serif`.

### 2.3 Spacing and dimensions

Spacing is a closed 4px scale: `0`, `0.5`, `1`, `1.5`, `2`, `3`, `4`, `5`, `6`, `8`, `10`, `12`,
`16`, `24`, and for large sizes and limits `32`, `48`, `64`, `96`. Rhythm:

| Steps | Between |
|---|---|
| `0.5`–`2` | Parts of one component (icon and label: `1.5`) |
| `3`–`4` | Related items: fields in a form, rows of metadata |
| `6`–`8` | Groups and sections; messages in the transcript |
| `12`+ | Page-level whitespace and empty states |

Named dimensions: `h-bar` (top bar and panel headers), `h-control-sm|control|control-lg` and
`size-control-*` (controls; larger on touch screens), `size-icon-sm|icon|icon-lg`, `w-sidebar`,
`w-sidebar-wide`, `w-drawer`, `h-chart`, `max-w-prose`.

### 2.4 Shape, elevation, motion

- Radii: `rounded-sm` (inputs, badges, inline code, privacy tokens), `rounded-md` (buttons, cards,
  code blocks, tables), `rounded-lg` (composer, drawers, dialogs, popovers), `rounded-full`
  (dots, avatars).
- Shadows: `shadow-sm` (floating buttons), `shadow-md` (tooltips, popovers, menus), `shadow-lg`
  (drawers, dialogs).
- Motion: `transition-colors` (default duration and easing), `animate-enter` (new content),
  `animate-fade` (surface swaps), `animate-pulse` (live indicators), `animate-spin` (spinners),
  `shimmer` (the title of running work).

### 2.5 Breakpoints

Viewport variants (`tablet:`, `desktop:`, `wide:`, `ultra:`) are for the app shell. Components
adapt to their container with `@container` and `@narrow:`, `@medium:`, `@wide:`.

---

## 3. Rules

### Tokens

- **TOKEN-01** Raw values (colors, lengths, durations, shadows, font names) appear only in
  `src/design/tokens.css`. `[lint]`
- **TOKEN-02** Every class must resolve to a utility. Unknown classes such as `text-gray-500` are
  errors, not silent no-ops. `[lint]`
- **TOKEN-03** No arbitrary values (`p-[13px]`, `bg-[#fff]`, `text-(--x)`). Exception:
  `grid-cols-[…]` and `grid-rows-[…]` in shell layout, using only `fr`, `minmax`, `auto` and tokens.
  `[lint]`
- **TOKEN-04** Class names are complete string literals, never built with `${}` or `+`, so Tailwind
  can see them. Pick between literals instead. Class strings live only in `className` attributes,
  `cn()`, `clsx()` and `cva()` calls, or properties, variables and arrow functions named
  `className` or `…ClassName`; a `…ClassNames` object maps keys to class strings. Those are what
  the checks read. `[lint]`
- **TOKEN-05** Every color role and type size has a row in section 2 saying what it is for.
  `[test]`

### Color

- **COLOR-01** Use the role that matches the purpose in section 2.1, not the one with the right
  look. `[review]`
- **COLOR-02** No opacity modifiers on color utilities (`bg-accent/10`): they create untested
  colors. `[lint]`
- **COLOR-03** At most one `bg-accent` button per panel region. Other actions are secondary or
  ghost. `[review]`
- **COLOR-04** Status color always comes with an icon or text that says the same thing. `[review]`
- **COLOR-05** Contrast, both themes: text roles ≥ 4.5:1 on every background they are allowed on;
  `border-control`, `border-accent` and the focus ring ≥ 3:1 on surfaces. `[test]`

### Typography

- **TYPE-01** `font-serif` only in the wordmark and empty-state headlines. `[lint]`
- **TYPE-02** `font-mono` for identifiers, codes, counts, timestamps and the `text-xs` eyebrow;
  numbers in columns also use `tabular-nums`. `[review]`
- **TYPE-03** Sentence case everywhere. Uppercase only for `text-xs` mono eyebrows, with
  `tracking-caps`. `[review]`
- **TYPE-04** Prose is capped at `max-w-prose`. `[visual]`

### Spacing and layout

- **SPACE-01** Spacing follows the rhythm table in 2.3; siblings of the same kind use the same gap.
  `[review]`
- **SPACE-02** Panel content insets: `px-4`, and `px-6` once the panel is `@medium` wide. Every
  panel is an `@container`. Headers, lists and content in one panel share the same left edge.
  `[visual]`
- **LAYOUT-01** The app shell follows the contract in section 4 at every breakpoint. `[visual]`
- **LAYOUT-02** Only the app shell (`src/components/shell/`) uses viewport variants; other
  components adapt with container queries. `[lint]`
- **LAYOUT-03** No horizontal page overflow at any viewport. Only designated regions scroll:
  session list, transcript, working-surface content, table and code blocks (both axes), X-ray
  panes. `[visual]`
- **LAYOUT-04** Long unbroken strings (IDs, paths, variant names) wrap with `wrap-anywhere`, or
  truncate with the full value in a tooltip. Nothing is clipped without a way to read it.
  `[visual]`
- **LAYOUT-05** Allowed stacking: `z-10` sticky headers, `z-30` overlays, `z-40` drawers,
  `z-50` tooltips and popovers. `[lint]`

### Shape, elevation, motion

- **SHAPE-01** Radii follow 2.4; nested corners use a smaller radius than their container.
  `[review]`
- **ELEV-01** Panels are separated by borders, never shadows. Shadows only on floating layers.
  `[review]`
- **MOTION-01** Only the transitions and animations in 2.4. No `duration-*`, `ease-*` or custom
  keyframes in components. `[lint]`
- **MOTION-02** With reduced motion, nothing moves; live state stays visible without animation.
  `[visual]`

### States

- **STATE-01** Interactive components define hover, active, focus-visible and disabled. Data
  components define loading, empty and error. Each one is a story. `[visual]`
- **STATE-02** Focus is the global ring from `base.css`. Never remove it; if a component clips it,
  move the ring inward with `outline-offset`. `[visual]`
- **STATE-03** Disabled is `disabled:opacity-50` with no pointer events, the only allowed
  `opacity-*` besides `opacity-0` for hidden-but-measured content. `[lint]`
- **STATE-04** Loading shows a status line or skeleton in the space the content will take, with
  `role="status"`. Errors use `role="alert"`, say what failed and offer the next step. `[review]`

### Accessibility

- **A11Y-01** Automated accessibility checks pass on every story in both themes. `[visual]`
- **A11Y-02** Targets are at least 24×24px, and 36×36px on touch screens, where the control tokens
  grow automatically. Links inside text and checkboxes inside their label are exempt. `[visual]`
- **A11Y-03** Icon-only buttons have an accessible name and a tooltip with the same text.
  `[lint]`
- **A11Y-04** Color is never the only signal (see COLOR-04). `[review]`

### Icons

- **ICON-01** Icons come from `lucide-react` only, sized `size-icon-sm` (next to `text-xs`/`text-sm`),
  `size-icon` (default) or `size-icon-lg` (empty states). Stroke width is set globally. `[lint]`
- **ICON-02** Icons inherit text color; decorative icons have `aria-hidden`. `[review]`

### Content

- **CONTENT-01** Labels are short and in sentence case, with no trailing period. Progress text uses
  the ellipsis character: `Loading data…`. `[lint]`
- **CONTENT-02** Numbers use thousands separators; durations read `3m 12s`; timestamps are
  absolute in mono, `2026-10-01 14:03`. `[review]`
- **CONTENT-03** Empty states say what is missing and what to do next. Errors never show stack
  traces or blame the user. `[review]`

### Domain

- **DOMAIN-01** Privacy values always render through `PrivacyText` with the `privacy` roles, the
  same in chat, X-ray and tables. `[review]`
- **DOMAIN-02** Refusals use `info`, never `danger`: refusing is correct behavior, not a failure.
  `[review]`
- **DOMAIN-03** Status mapping. Conversation turn: idle neutral, responding `accent` with pulse,
  connecting or reconnecting `warning`, failed `danger`. Job: queued neutral, running `accent`,
  retrying `warning`, completed `success`, failed `danger`. `[review]`

### Themes

- **THEME-01** `<html data-theme>` is always `light` or `dark`. The saved preference (`light`,
  `dark`, `system`; default `system`) is resolved before first paint, and `system` follows the OS
  live. `[test]`
- **THEME-02** Components never branch on theme: no `dark:` variant, no theme checks in render
  code. Only the theme module (`src/lib/theme.ts`) sets `data-theme` or reads the OS preference.
  Charts and MCP apps read tokens at runtime and re-read on theme change. `[lint]`
- **THEME-03** Every story is verified in both themes. `[visual]`

### Components

- **COMP-01** Use the components in section 5 before writing markup. Call sites may add layout
  classes (margin, width, grid placement) but not color, type or padding. `[review]`
- **COMP-02** Variants are `cva` variants on the component, not class overrides at call sites.
  `[review]`
- **COMP-03** A new component needs a story covering its states, stress content (long text, empty,
  many items) and a row in section 5. `[review]`
- **COMP-04** No component CSS files. Styles are utilities; `src/design/*.css` is the only CSS.
  `[lint]`

---

## 4. App shell contract

| Viewport | Width | Sidebar | Chat and working surface | X-ray |
|---|---|---|---|---|
| Phone | < 768 | Drawer from a menu button | One at a time, switched by tabs | Panes switched by tabs |
| Tablet | 768–1279 | Persistent, `w-sidebar` | One at a time, switched by tabs | Panes switched by tabs |
| Desktop | 1280–1919 | Persistent, `w-sidebar` | Side by side, chat narrower than surface | Side by side |
| Wide | 1920–2559 | Persistent, `w-sidebar-wide` | Side by side | Side by side |
| Ultra | ≥ 2560 | Persistent, `w-sidebar-wide` | Chat capped near `max-w-prose`; surface takes the rest | Side by side |

- The top bar and every panel header are `h-bar` tall.
- The page never scrolls; panels do (LAYOUT-03).
- The theme control (Light, Dark, System) sits in the top bar.

---

## 5. Component inventory

Each component has a story file next to it. Story data lives in `src/components/fixtures.ts`.

| Folder | Component | Variants | States and stress cases in stories |
|---|---|---|---|
| `ui/` | Button | primary, secondary, ghost, danger × sm, md, lg | disabled, loading, long label in a narrow box |
| `ui/` | IconButton | ghost, secondary, primary × sm, md; pressed | disabled; tooltip |
| `ui/` | Tooltip | — | open, long text |
| `ui/` | Field, Input, Select, Textarea, Checkbox | — | hint, error, disabled, two columns from `@medium` |
| `ui/` | Badge | neutral, accent, danger, warning, info, success | icon, long text in a narrow box |
| `ui/` | StatusDot | same tones; live | reduced motion |
| `ui/` | Notice | danger, warning, info, success | title, action, long text in a narrow box |
| `ui/` | Tabs | underline, with icon and count | many tabs overflowing |
| `ui/` | Drawer | — | open with the session list |
| `ui/` | EmptyState | display (serif), quiet | action, narrow box |
| `ui/` | PanelHeader, Eyebrow, Spinner | — | long subtitle (truncated with its full value) |
| `shell/` | AppShell, TopBar, Wordmark, ThemeToggle | — | every viewport in section 4; X-ray on; drawer open; error |
| `shell/` | SessionLayout | chat or surface tab | every viewport in section 4 |
| `shell/` | SessionList | — | empty, many, creating, very long title; persona chooser with a long hint, no personas |
| `chat/` | ChatPanel | — | opening, new, conversation, responding, failed, reconnecting; persona badge, no persona |
| `chat/` | TranscriptText, PrivacyText | user, assistant; md, sm | streaming, Markdown with code, tables and links |
| `chat/` | StepMarker | running, complete, failed | expanded, with a view link |
| `chat/` | RefusalChip, ViewReference, TurnStatus, Composer | — | in the chat panel stories |
| `surface/` | WorkingSurface, ViewHeader | — | no views, unavailable view, chart, table |
| `surface/views/` | TableView | inline, from a handle | loading, empty, error, nulls, booleans |
| `surface/views/` | ChartView | each mark type | loading, error |
| `surface/views/` | DraftEditor | — | editing, needs review, submitted |
| `surface/` | McpAppFrame, McpAppView | — | running job, no jobs, both themes |
| `xray/` | XrayContent, XrayPanel | — | requests with privacy values, nothing recorded |

---

## 6. Themes and embedded apps

- `src/lib/theme.ts` owns the theme: `startTheme()` applies the saved preference and follows the
  OS; the theme control calls `setPreference()`; `useTheme()` reports the current theme to code
  that reads tokens at runtime. An inline script in `index.html` repeats the resolution before
  paint.
- Embedded MCP apps (`services/agent/zagent/job_ui/`) style themselves only with the standard MCP
  Apps host variables, with light fallbacks. `McpAppFrame` sends `theme` and these variables in the
  host context, and again whenever the theme changes:

| MCP Apps variable | Zagent token |
|---|---|
| `--color-background-primary` / `secondary` / `tertiary` / `inverse` | `bg-surface` / `subtle` / `muted` / `inverse` |
| `--color-background-{info,danger,success,warning}` | `bg-*-subtle` |
| `--color-text-primary` / `secondary` / `tertiary` / `inverse` / `disabled` | `text-default` / `muted` / `muted` / `inverse` / `muted` |
| `--color-text-{info,danger,success,warning}` | matching `text-*` |
| `--color-border-primary` / `secondary` / `tertiary` | `border-default` / `subtle` / `subtle` |
| `--color-border-{info,danger,success,warning}` | matching `border-*` |
| `--color-ring-primary` | `outline-focus` |
| `--font-sans`, `--font-mono`, `--font-weight-*` | same names |
| `--font-text-{xs,sm,md,lg}-size` and `-line-height` | `text-xs`, `text-sm`, `text-base`, `text-md` |
| `--font-heading-{sm,md,lg}-size` and `-line-height` | `text-base`, `text-lg`, `text-xl` |
| `--border-radius-{xs,sm,md,lg,full}` | `rounded-sm`, `sm`, `md`, `lg`, `full` |
| `--shadow-{sm,md,lg}` | same names |

---

## 7. Data visualization

- Series colors come from `--chart-1` … `--chart-6`, in order; more than six series need grouping,
  not new colors.
- Axis labels use `text-muted`, titles `text-default`, gridlines `border-subtle`, all read from
  tokens at runtime.

---

## 8. Changing the system

1. Change `tokens.css` or this file first, in the same commit as the code that needs it.
2. Keep both themes in step: a new semantic role gets a light and a dark value.
3. Run the checks below; review the `Design system/Tokens` story in both themes.

---

## 9. Verification

| Check | Command | Covers |
|---|---|---|
| Lexical | `npm --prefix apps/web run lint:design [paths…]` (part of `make lint`) | `[lint]` rules |
| Unit | `npm --prefix apps/web test` | `[test]` rules; the lint's own fixtures |
| Visual | `npm --prefix apps/web run test:design` | `[visual]` rules over every story |

The checks live in `apps/web/scripts/design/`. Tailwind's compiler, loaded with the app
stylesheet (`src/design/styles.css`), decides whether a class exists. The unit tests also fail
when a `[lint]` rule in this file has no implementation or fixture, or when a color role or type
size is missing from section 2.

Storybook (`npm --prefix apps/web run storybook`, port 6006) has a theme switch and the viewport
presets below. The visual check builds Storybook, then renders every story at each viewport in
[matrix.ts](../apps/web/src/design/matrix.ts), in light and dark, with reduced motion:

| Viewport | Size | Touch |
|---|---|---|
| `phone-360` | 360×780 | yes |
| `tablet-768` | 768×1024 | yes |
| `desktop-1280` | 1280×800 | no |
| `desktop-1440` | 1440×900 | no |
| `wide-1920` | 1920×1080 | no |
| `ultra-2560` | 2560×1440 | no |

Each width is the narrowest of its breakpoint range, where layouts are most cramped. Every render
is checked for LAYOUT-03, LAYOUT-04, A11Y-01, A11Y-02 and MOTION-02; STATE-02 is checked by
tabbing through each story at `desktop-1440`. Then the page is compared with its baseline in
`apps/web/.design-baselines/<story>/<viewport>-<theme>.png`, which is untracked until the design
is stable. Any changed pixel fails; only anti-aliasing noise is tolerated.

- Filter: `npm --prefix apps/web run test:design -- -g "phone-360 design-system-tokens"`.
- A new story's first run records its baselines and reports them as missing; the next run
  compares.
- Accept an intended change: `npm --prefix apps/web run test:design -- --update-snapshots=changed`.
- Failures, with actual and diff images, are in `apps/web/test-results/design/`.

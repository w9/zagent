// Shared by Storybook and the visual check (docs/DESIGN.md section 9).
// Each width is the narrowest of its breakpoint range, where layouts are most cramped.
export const viewports = [
  { name: 'phone-360', width: 360, height: 780, touch: true },
  { name: 'tablet-768', width: 768, height: 1024, touch: true },
  { name: 'desktop-1280', width: 1280, height: 800, touch: false },
  { name: 'desktop-1440', width: 1440, height: 900, touch: false },
  { name: 'wide-1920', width: 1920, height: 1080, touch: false },
  { name: 'ultra-2560', width: 2560, height: 1440, touch: false },
] as const

export const themes = ['light', 'dark'] as const

export const axeTags = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

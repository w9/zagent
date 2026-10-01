import { clsx } from 'clsx'
import type { ClassValue } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

// Teaches tailwind-merge the token names from src/design/tokens.css, so conflicts resolve correctly.
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      text: ['base', 'md', '2xl'],
      spacing: [
        'control', 'control-sm', 'control-lg', 'icon', 'icon-sm', 'icon-lg',
        'bar', 'chart', 'sidebar', 'sidebar-wide', 'drawer', 'prose',
      ],
      breakpoint: ['tablet', 'desktop', 'wide', 'ultra'],
      container: ['narrow', 'medium', 'wide'],
      animate: ['enter', 'fade', 'pulse', 'spin', 'shimmer'],
      tracking: ['caps'],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

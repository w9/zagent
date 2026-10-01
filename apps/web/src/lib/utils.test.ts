import { describe, expect, it } from 'vitest'
import { cn } from './utils'

describe('cn', () => {
  it.each([
    ['text-md text-muted', 'text-md text-muted'],
    ['text-sm text-base', 'text-base'],
    ['text-muted text-strong', 'text-strong'],
    ['bg-surface bg-subtle', 'bg-subtle'],
    ['h-control h-control-sm', 'h-control-sm'],
    ['size-control size-icon', 'size-icon'],
    ['w-sidebar w-full', 'w-full'],
    ['flex hidden desktop:flex', 'hidden desktop:flex'],
    ['rounded-md rounded-lg', 'rounded-lg'],
    ['shadow-sm shadow-md', 'shadow-md'],
    ['animate-spin animate-shimmer', 'animate-shimmer'],
    ['justify-center justify-start', 'justify-start'],
  ])('merges "%s" to "%s"', (input, expected) => {
    expect(cn(input)).toBe(expected)
  })
})

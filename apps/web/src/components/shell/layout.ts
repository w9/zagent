import { useCallback, useSyncExternalStore } from 'react'

/** A token's computed value from tokens.css, such as "240px"; panel size props accept it as is. */
export function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

/** Whether the viewport is at least as wide as a breakpoint from tokens.css; follows resizes. */
export function useBreakpoint(name: 'tablet' | 'desktop' | 'wide' | 'ultra'): boolean {
  const query = `(min-width: ${token(`--breakpoint-${name}`)})`
  const subscribe = useCallback(
    (onChange: () => void) => {
      const media = matchMedia(query)
      media.addEventListener('change', onChange)
      return () => media.removeEventListener('change', onChange)
    },
    [query],
  )
  return useSyncExternalStore(subscribe, () => matchMedia(query).matches)
}

export function loadSize(key: string): number | undefined {
  try {
    const size = Number(localStorage.getItem(key))
    return size > 0 ? size : undefined
  } catch {
    return undefined
  }
}

export function saveSize(key: string, size: number) {
  try {
    localStorage.setItem(key, String(size))
  } catch {
    // Remembering panel sizes is a convenience.
  }
}
